"""Safe LangGraph SQLite checkpointer construction for project runtimes."""

from __future__ import annotations

from pathlib import Path
import asyncio
import math
import sqlite3
import threading
from typing import Any

import aiosqlite
from langgraph.checkpoint.sqlite import SqliteSaver


class StrictMsgpackSerializer:
    """Msgpack serializer that accepts only plain, bounded data structures."""

    def __init__(self, *, max_bytes: int = 16 * 1024 * 1024):
        self.max_bytes = max_bytes

    def _validate(self, value: Any) -> None:
        if value is None or isinstance(value, (bool, int, str, bytes)):
            return
        if isinstance(value, float):
            if math.isfinite(value):
                return
            raise TypeError("unsafe msgpack value: non-finite float")
        if isinstance(value, list):
            for item in value:
                self._validate(item)
            return
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            for item in value.values():
                self._validate(item)
            return
        raise TypeError(f"unsafe msgpack value: {type(value).__name__}")

    def dumps_typed(self, value: Any) -> tuple[str, bytes]:
        self._validate(value)
        import msgpack

        payload = msgpack.packb(value, use_bin_type=True, strict_types=True)
        if len(payload) > self.max_bytes:
            raise ValueError("checkpoint payload exceeds size limit")
        return ("msgpack", payload)

    def loads_typed(self, value: tuple[str, bytes]) -> Any:
        kind, payload = value
        if kind != "msgpack" or len(payload) > self.max_bytes:
            raise ValueError("unsafe checkpoint payload")
        import msgpack

        decoded = msgpack.unpackb(payload, raw=False, strict_map_key=True, ext_hook=lambda *_: (_ for _ in ()).throw(ValueError("msgpack extensions are disabled")))
        self._validate(decoded)
        return decoded

    def dumps(self, value: Any) -> bytes:
        return self.dumps_typed(value)[1]

    def loads(self, payload: bytes) -> Any:
        return self.loads_typed(("msgpack", payload))


class AsyncCompatibleSqliteSaver(SqliteSaver):
    """Add LangGraph's async saver protocol to the installed sync SQLite saver.

    ``SqliteSaver`` deliberately rejects ``ainvoke`` in the installed package.
    The sidecar workflows are async, so their checkpoint operations are delegated
    to the synchronous production saver on a worker thread instead.
    """

    def __init__(self, connection: sqlite3.Connection, *, serde: Any):
        super().__init__(connection, serde=serde)
        self._lock = threading.RLock()
        self._lifecycle = threading.Condition()
        self._inflight_operations = 0
        self._closing = False
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closing or self._closed:
            raise RuntimeError("SQLite checkpointer is closing")

    def _begin_operation(self) -> None:
        with self._lifecycle:
            self._ensure_open()
            self._inflight_operations += 1

    def _finish_operation(self) -> None:
        with self._lifecycle:
            self._inflight_operations -= 1
            self._lifecycle.notify_all()

    def _run_sync(self, operation: Any) -> Any:
        self._begin_operation()
        try:
            return operation()
        finally:
            self._finish_operation()

    async def _run_async(self, operation: Any) -> Any:
        self._begin_operation()

        def run_in_worker() -> Any:
            try:
                return operation()
            finally:
                # The worker owns this count. An awaiting task can be cancelled
                # while ``to_thread`` continues executing the SQLite operation.
                self._finish_operation()

        return await asyncio.to_thread(run_in_worker)

    def _get_tuple(self, config: Any) -> Any:
        with self._lock:
            return super().get_tuple(config)

    def get_tuple(self, config: Any) -> Any:
        return self._run_sync(lambda: self._get_tuple(config))

    def _list(self, config: Any, *, filter: dict[str, Any] | None = None,
              before: Any = None, limit: int | None = None) -> list[Any]:
        with self._lock:
            return list(super().list(config, filter=filter, before=before, limit=limit))

    def list(self, config: Any, *, filter: dict[str, Any] | None = None,
             before: Any = None, limit: int | None = None):
        return iter(self._run_sync(
            lambda: self._list(config, filter=filter, before=before, limit=limit)
        ))

    def _put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        with self._lock:
            return super().put(config, checkpoint, metadata, new_versions)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return self._run_sync(lambda: self._put(config, checkpoint, metadata, new_versions))

    def _put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        self._run_sync(lambda: self._put_writes(config, writes, task_id, task_path))

    def _delete_thread(self, thread_id: str) -> None:
        with self._lock:
            super().delete_thread(thread_id)

    def delete_thread(self, thread_id: str) -> None:
        self._run_sync(lambda: self._delete_thread(thread_id))

    async def aget_tuple(self, config: Any) -> Any:
        return await self._run_async(lambda: self._get_tuple(config))

    async def alist(self, config: Any, *, filter: dict[str, Any] | None = None,
                    before: Any = None, limit: int | None = None):
        entries = await self._run_async(
            lambda: self._list(config, filter=filter, before=before, limit=limit)
        )
        for entry in entries:
            yield entry

    async def aput(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return await self._run_async(lambda: self._put(config, checkpoint, metadata, new_versions))

    async def aput_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        await self._run_async(lambda: self._put_writes(config, writes, task_id, task_path))

    async def adelete_thread(self, thread_id: str) -> None:
        await self._run_async(lambda: self._delete_thread(thread_id))

    def _close_connection(self) -> None:
        with self._lock:
            if not self._closed:
                self.conn.close()
                self._closed = True

    def close(self) -> None:
        """Close safely from synchronous lifespan code without racing workers."""
        with self._lifecycle:
            self._closing = True
        self._wait_for_async_drain_and_close()

    def _wait_for_async_drain_and_close(self) -> None:
        with self._lifecycle:
            while self._inflight_operations:
                self._lifecycle.wait()
        self._close_connection()

    async def aclose(self) -> None:
        """Reject new calls, drain async operations, and then close SQLite."""
        with self._lifecycle:
            self._closing = True
        await asyncio.to_thread(self._wait_for_async_drain_and_close)


def create_sqlite_checkpointer(database_path: str | Path) -> AsyncCompatibleSqliteSaver:
    """Create a durable saver that supports both ``invoke`` and ``ainvoke``."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    return AsyncCompatibleSqliteSaver(connection, serde=StrictMsgpackSerializer())


def close_checkpointer(checkpointer: Any) -> None:
    if checkpointer is None:
        return
    close = getattr(checkpointer, "close", None)
    if callable(close):
        close()
        return
    connection = getattr(checkpointer, "conn", None)
    if connection is not None:
        connection.close()


async def aclose_checkpointer(checkpointer: Any) -> None:
    if checkpointer is None:
        return
    aclose = getattr(checkpointer, "aclose", None)
    if callable(aclose):
        await aclose()
        return
    close_checkpointer(checkpointer)


class ProjectCheckpointers:
    """App-lifespan-owned sync and async LangGraph savers for one project."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.sync_connection: sqlite3.Connection | None = None
        self.async_connection: aiosqlite.Connection | None = None
        self.sync_saver: Any = None
        self.async_saver: Any = None

    async def open(self) -> "ProjectCheckpointers":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.sync_connection = sqlite3.connect(str(self.database_path), check_same_thread=False)
        self.sync_saver = AsyncCompatibleSqliteSaver(self.sync_connection, serde=StrictMsgpackSerializer())
        self.async_connection = await aiosqlite.connect(str(self.database_path))
        self.async_saver = AsyncSqliteSaver(self.async_connection, serde=StrictMsgpackSerializer())
        await self.async_saver.setup()
        return self

    async def close(self) -> None:
        if self.async_connection is not None:
            await self.async_connection.close()
            self.async_connection = None
        if self.sync_saver is not None:
            await self.sync_saver.aclose()
            self.sync_saver = None
        if self.sync_connection is not None:
            self.sync_connection = None


def create_project_checkpointers(database_path: str | Path) -> ProjectCheckpointers:
    """Return a lifecycle-managed project saver factory; call ``await open()``."""
    return ProjectCheckpointers(database_path)
