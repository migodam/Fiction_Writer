from __future__ import annotations

import asyncio
import threading
from typing import TypedDict

import pytest

from langgraph.graph import END, StateGraph

from sidecar.runtime.checkpointer import StrictMsgpackSerializer, create_project_checkpointers, create_sqlite_checkpointer


class _CounterState(TypedDict):
    count: int


def _counter_graph(checkpointer):
    builder = StateGraph(_CounterState)
    builder.add_node("increment", lambda state: {"count": state["count"] + 1})
    builder.set_entry_point("increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=checkpointer)


def test_strict_msgpack_serializer_rejects_non_plain_objects_without_serializing():
    serializer = StrictMsgpackSerializer()

    with pytest.raises(TypeError, match="unsafe msgpack value"):
        serializer.dumps_typed(object())

    with pytest.raises(TypeError, match="non-finite"):
        serializer.dumps_typed(float("nan"))


def test_sqlite_checkpointer_factory_uses_the_safe_serializer(tmp_path):
    checkpointer = create_sqlite_checkpointer(tmp_path / "agent_runtime.db")
    try:
        assert isinstance(checkpointer.serde, StrictMsgpackSerializer)
        assert checkpointer.serde.loads(checkpointer.serde.dumps({"checkpoint": 1})) == {"checkpoint": 1}
    finally:
        checkpointer.close()


def test_production_sqlite_saver_survives_close_and_reopen_for_invoke(tmp_path):
    database_path = tmp_path / "langgraph.db"
    config = {"configurable": {"thread_id": "sync-thread"}}
    saver = create_sqlite_checkpointer(database_path)
    assert _counter_graph(saver).invoke({"count": 0}, config)["count"] == 1
    saver.close()

    reopened = create_sqlite_checkpointer(database_path)
    try:
        assert _counter_graph(reopened).get_state(config).values["count"] == 1
    finally:
        reopened.close()


def test_production_sqlite_saver_supports_ainvoke_and_reopen(tmp_path):
    async def exercise() -> None:
        database_path = tmp_path / "langgraph.db"
        config = {"configurable": {"thread_id": "async-thread"}}
        saver = create_sqlite_checkpointer(database_path)
        assert (await _counter_graph(saver).ainvoke({"count": 0}, config))["count"] == 1
        await saver.aclose()

        reopened = create_sqlite_checkpointer(database_path)
        try:
            assert (await _counter_graph(reopened).aget_state(config)).values["count"] == 1
        finally:
            await reopened.aclose()

    asyncio.run(exercise())


def test_project_checkpointers_keep_sync_and_async_connections_open(tmp_path):
    async def exercise() -> None:
        checkpointers = create_project_checkpointers(tmp_path / "langgraph.db")
        await checkpointers.open()
        try:
            assert isinstance(checkpointers.sync_saver.serde, StrictMsgpackSerializer)
            assert isinstance(checkpointers.async_saver.serde, StrictMsgpackSerializer)
            assert checkpointers.sync_connection is not None
            assert checkpointers.async_connection is not None
        finally:
            await checkpointers.close()

    asyncio.run(exercise())


def test_async_close_waits_for_worker_after_awaiting_task_is_cancelled(tmp_path):
    async def exercise() -> None:
        saver = create_sqlite_checkpointer(tmp_path / "cancelled-worker.db")
        graph = _counter_graph(saver)
        config = {"configurable": {"thread_id": "cancelled-worker"}}
        operation_finished_sql = threading.Event()
        release_worker = threading.Event()
        original_get_tuple = saver._get_tuple

        def delayed_get_tuple(graph_config):
            result = original_get_tuple(graph_config)
            operation_finished_sql.set()
            release_worker.wait(timeout=2)
            return result

        saver._get_tuple = delayed_get_tuple
        invoke_task = asyncio.create_task(graph.ainvoke({"count": 0}, config))
        assert await asyncio.to_thread(operation_finished_sql.wait, 2)
        invoke_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invoke_task

        close_task = asyncio.create_task(saver.aclose())
        await asyncio.sleep(0.01)
        assert not close_task.done()
        release_worker.set()
        await asyncio.wait_for(close_task, timeout=2)

    asyncio.run(exercise())


def test_sync_close_drains_an_active_sync_operation(tmp_path):
    saver = create_sqlite_checkpointer(tmp_path / "sync-close-race.db")
    graph = _counter_graph(saver)
    config = {"configurable": {"thread_id": "sync-close-race"}}
    assert graph.invoke({"count": 0}, config)["count"] == 1
    operation_finished_sql = threading.Event()
    release_operation = threading.Event()
    original_get_tuple = saver._get_tuple
    errors: list[BaseException] = []

    def delayed_get_tuple(graph_config):
        result = original_get_tuple(graph_config)
        operation_finished_sql.set()
        release_operation.wait(timeout=2)
        return result

    def read_checkpoint():
        try:
            saver.get_tuple(config)
        except BaseException as exc:
            errors.append(exc)

    saver._get_tuple = delayed_get_tuple
    reader = threading.Thread(target=read_checkpoint, name="checkpointer-sync-reader")
    reader.start()
    assert operation_finished_sql.wait(timeout=2)
    closer = threading.Thread(target=saver.close, name="checkpointer-sync-closer")
    closer.start()
    closer.join(timeout=0.05)
    assert closer.is_alive()
    release_operation.set()
    reader.join(timeout=2)
    closer.join(timeout=2)
    assert not reader.is_alive()
    assert not closer.is_alive()
    assert errors == []
