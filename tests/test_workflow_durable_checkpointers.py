"""Durability boundaries for W0 and W2-W7 LangGraph workflows."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sqlite3
import threading
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from sidecar.runtime.agent_runtime import RuntimeStore

WORKFLOW_MODULES = (
    "sidecar.workflows.w0_orchestrator",
    "sidecar.workflows.w1_import",
    "sidecar.workflows.w2_manuscript_sync",
    "sidecar.workflows.w3_writing_assistant",
    "sidecar.workflows.w4_consistency_check",
    "sidecar.workflows.w5_simulation",
    "sidecar.workflows.w6_beta_reader",
    "sidecar.workflows.w7_metadata_ingestion",
)


class _CounterState(TypedDict):
    count: int


def _counter_graph(checkpointer):
    builder = StateGraph(_CounterState)
    builder.add_node("increment", lambda state: {"count": state["count"] + 1})
    builder.set_entry_point("increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=checkpointer)


def test_graph_builders_compile_when_an_explicit_test_saver_is_injected(tmp_path):
    for module_name in WORKFLOW_MODULES:
        module = importlib.import_module(module_name)
        graph = module.get_graph(tmp_path / module_name.rsplit(".", 1)[-1], checkpointer=MemorySaver())
        assert graph is not None


def test_graph_cache_is_scoped_by_canonical_project_and_checkpointer_identity(tmp_path):
    module = importlib.import_module("sidecar.workflows.w2_manuscript_sync")
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    saver = MemorySaver()

    graph_a = module.get_graph(project_a, checkpointer=saver)
    assert graph_a is module.get_graph(project_a / ".", checkpointer=saver)
    assert graph_a is not module.get_graph(project_b, checkpointer=saver)
    assert graph_a is not module.get_graph(project_a, checkpointer=MemorySaver())


def test_production_getters_create_project_scoped_durable_savers(tmp_path, monkeypatch):
    for module_name in WORKFLOW_MODULES:
        module = importlib.import_module(module_name)
        created_paths: list[Path] = []

        def make_saver(database_path):
            created_paths.append(Path(database_path))
            return MemorySaver()

        monkeypatch.setattr(module, "create_sqlite_checkpointer", make_saver)
        module.get_graph(tmp_path / "one")
        module.get_graph(tmp_path / "two")

        assert created_paths == [
            (tmp_path / "one" / "system" / "runtime" / "langgraph_checkpoints.db").resolve(),
            (tmp_path / "two" / "system" / "runtime" / "langgraph_checkpoints.db").resolve(),
        ]


def test_w0_w1_and_w3_run_reuse_the_supplied_thread_id(tmp_path, monkeypatch):
    for module_name, config in (
        ("sidecar.workflows.w0_orchestrator", {"goal": "continue", "thread_id": "w0-resume"}),
        ("sidecar.workflows.w1_import", {"source_file_path": "novel.txt", "thread_id": "w1-resume"}),
        ("sidecar.workflows.w3_writing_assistant", {"scene_id": "scene-1", "thread_id": "w3-resume"}),
    ):
        module = importlib.import_module(module_name)
        seen_configs: list[dict] = []

        class FakeGraph:
            async def ainvoke(self, state, graph_config):
                seen_configs.append(graph_config)
                return {"status": "done"}

        monkeypatch.setattr(module, "get_graph", lambda project_path: FakeGraph())
        assert asyncio.run(module.run(str(tmp_path), config))["status"] == "done"
        assert seen_configs == [{"configurable": {"thread_id": config["thread_id"]}}]


def test_w0_and_w3_run_resume_the_supplied_thread_id(tmp_path, monkeypatch):
    for module_name, config in (
        ("sidecar.workflows.w0_orchestrator", {"goal": "continue", "thread_id": "w0-resume", "resume": True}),
        ("sidecar.workflows.w3_writing_assistant", {"scene_id": "scene-1", "thread_id": "w3-resume", "resume": 1}),
    ):
        module = importlib.import_module(module_name)
        seen_configs: list[dict] = []

        class FakeGraph:
            async def ainvoke(self, state, graph_config):
                seen_configs.append(graph_config)
                return {"status": "done"}

        monkeypatch.setattr(module, "get_graph", lambda project_path: FakeGraph())
        assert asyncio.run(module.run(str(tmp_path), config))["status"] == "done"
        assert seen_configs == [{"configurable": {"thread_id": config["thread_id"]}}]


def test_w1_attempt_id_provides_a_stable_thread_and_canonical_project_path(tmp_path, monkeypatch):
    module = importlib.import_module("sidecar.workflows.w1_import")
    captured: dict = {}

    class FakeGraph:
        async def ainvoke(self, state, graph_config):
            captured["state"] = state
            captured["config"] = graph_config
            return {"status": "done"}

    monkeypatch.setattr(module, "get_graph", lambda project_path: FakeGraph())
    project_path = tmp_path / "project" / "."
    assert asyncio.run(module.run(str(project_path), {
        "attempt_id": "attempt-42",
        "lineage_id": "lineage-42",
    }))["status"] == "done"
    assert captured["state"]["project_path"] == str((tmp_path / "project").resolve())
    assert captured["state"]["runtime_lineage_id"] == "lineage-42"
    assert captured["state"]["context"]["runtime_lineage_id"] == "lineage-42"
    assert captured["config"] == {"configurable": {"thread_id": "w1-attempt-42"}}


def test_w1_streaming_carries_runtime_lineage_and_attempt(tmp_path, monkeypatch):
    module = importlib.import_module("sidecar.workflows.w1_import")
    captured: dict = {}

    class FakeGraph:
        async def astream(self, state, graph_config):
            captured["state"] = state
            captured["config"] = graph_config
            if False:
                yield {}

    monkeypatch.setattr(module, "get_graph", lambda project_path: FakeGraph())

    async def consume():
        return [update async for update in module.run_streaming(str(tmp_path), {
            "attempt_id": "attempt-stream",
            "lineage_id": "lineage-stream",
            "compatibility_mode": True,
        })]

    assert asyncio.run(consume()) == []
    assert captured["state"]["runtime_lineage_id"] == "lineage-stream"
    assert captured["state"]["context"]["runtime_lineage_id"] == "lineage-stream"
    assert captured["state"]["context"]["w1_attempt_id"] == "attempt-stream"
    assert captured["config"] == {"configurable": {"thread_id": "w1-attempt-stream"}}


def test_w1_streaming_records_safe_runtime_checkpoint_chain_across_resume(tmp_path, monkeypatch):
    module = importlib.import_module("sidecar.workflows.w1_import")
    store = RuntimeStore(tmp_path)
    attempt = store.create_attempt(store.create_run(workflow_id="W1")["run_id"])
    attempt_id = attempt["attempt_id"]
    emitted = [
        {
            "split_chunks": {
                "progress": 0.1,
                "chunks": [{"source_content": "private manuscript"}],
                "prompt": "sk-super-secret-value",
                "errors": [],
            }
        },
        {
            "process_chunks": {
                "progress": 0.8,
                "chunk_extractions": [{"content": "private result"}],
                "errors": [],
            }
        },
    ]

    class FakeGraph:
        async def astream(self, _state, _graph_config):
            for event in emitted:
                yield event

    monkeypatch.setattr(module, "get_graph", lambda _project_path: FakeGraph())

    async def consume():
        return [update async for update in module.run_streaming(str(tmp_path), {
            "attempt_id": attempt_id,
            "runtime_store": store,
            "thread_id": f"w1-{attempt_id}",
            "compatibility_mode": True,
        })]

    assert [item["current_node"] for item in asyncio.run(consume())] == [
        "split_chunks", "process_chunks",
    ]
    first_run = store.list_checkpoint_metadata(attempt_id)
    assert [item["sequence"] for item in first_run] == [1, 2]
    assert [item["node"] for item in first_run] == ["split_chunks", "process_chunks"]
    assert first_run[0]["parent_checkpoint_id"] is None
    assert first_run[1]["parent_checkpoint_id"] == first_run[0]["checkpoint_id"]
    assert first_run[0]["checkpoint_id"] == module._stable_runtime_checkpoint_id(
        attempt_id, 1, "split_chunks"
    )
    assert set(first_run[0]["metadata"]) == {
        "output_hash", "progress", "error_count", "completed_chunks", "total_chunks",
    }

    emitted[:] = [{"build_manuscript": {"progress": 0.9, "errors": []}}]
    assert [item["current_node"] for item in asyncio.run(consume())] == ["build_manuscript"]
    resumed = store.list_checkpoint_metadata(attempt_id)
    assert [item["sequence"] for item in resumed] == [1, 2, 3]
    assert resumed[2]["parent_checkpoint_id"] == resumed[1]["checkpoint_id"]
    assert resumed[2]["checkpoint_id"] == module._stable_runtime_checkpoint_id(
        attempt_id, 3, "build_manuscript"
    )

    with sqlite3.connect(store.database_path) as connection:
        persisted_metadata = "\n".join(
            row[0] for row in connection.execute(
                "SELECT metadata_json FROM checkpoint_metadata WHERE attempt_id = ?",
                (attempt_id,),
            )
        )
    assert "private manuscript" not in persisted_metadata
    assert "private result" not in persisted_metadata
    assert "sk-super-secret-value" not in persisted_metadata


def test_w1_durable_cache_is_project_scoped_and_can_be_closed(tmp_path, monkeypatch):
    module = importlib.import_module("sidecar.workflows.w1_import")
    created_paths: list[Path] = []

    def make_saver(database_path):
        created_paths.append(Path(database_path))
        return MemorySaver()

    monkeypatch.setattr(module, "create_sqlite_checkpointer", make_saver)
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    graph_a = module.get_graph(project_a)
    graph_b = module.get_graph(project_b)
    assert graph_a is not graph_b
    assert created_paths == [
        (project_a / "system" / "runtime" / "langgraph_checkpoints.db").resolve(),
        (project_b / "system" / "runtime" / "langgraph_checkpoints.db").resolve(),
    ]

    module.close_project_checkpointer(project_a)
    assert module.get_graph(project_a) is not graph_a
    assert created_paths[-1] == (project_a / "system" / "runtime" / "langgraph_checkpoints.db").resolve()


def test_workflow_modules_do_not_construct_memory_savers_on_production_paths():
    for module_name in WORKFLOW_MODULES:
        module = importlib.import_module(module_name)
        assert "MemorySaver" not in inspect.getsource(module)


def test_w0_w1_w3_async_shutdown_drains_inflight_and_reopens(tmp_path):
    baseline_threads = {thread.ident for thread in threading.enumerate()}

    async def exercise() -> None:
        for module_name in (
            "sidecar.workflows.w0_orchestrator",
            "sidecar.workflows.w1_import",
            "sidecar.workflows.w3_writing_assistant",
        ):
            module = importlib.import_module(module_name)
            project_path = tmp_path / module_name.rsplit(".", 1)[-1]

            for cycle in range(4):
                saver = module._project_checkpointer(project_path)
                graph = _counter_graph(saver)
                seed_config = {"configurable": {"thread_id": f"seed-{cycle}"}}
                assert (await graph.ainvoke({"count": 0}, seed_config))["count"] == 1

                operation_finished_sql = threading.Event()
                release_worker = threading.Event()
                original_get_tuple = saver._get_tuple

                def delayed_get_tuple(config):
                    result = original_get_tuple(config)
                    operation_finished_sql.set()
                    release_worker.wait(timeout=2)
                    return result

                saver._get_tuple = delayed_get_tuple
                race_config = {"configurable": {"thread_id": f"race-{cycle}"}}
                invoke_task = asyncio.create_task(graph.ainvoke({"count": 0}, race_config))
                assert await asyncio.to_thread(operation_finished_sql.wait, 2)

                close_task = asyncio.create_task(module.close_project_checkpointer_async(project_path))
                await asyncio.sleep(0.01)
                assert not close_task.done()
                release_worker.set()
                await asyncio.wait_for(asyncio.gather(invoke_task, return_exceptions=True), timeout=3)
                await asyncio.wait_for(close_task, timeout=3)

                reopened = module._project_checkpointer(project_path)
                reopened_graph = _counter_graph(reopened)
                assert (await reopened_graph.aget_state(seed_config)).values["count"] == 1
                assert (await reopened_graph.ainvoke(
                    {"count": 0},
                    {"configurable": {"thread_id": f"reopen-{cycle}"}},
                ))["count"] == 1
                await module.close_project_checkpointer_async(project_path)

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    leaked_workers = [
        thread for thread in threading.enumerate()
        if thread.ident not in baseline_threads and thread.name.startswith("asyncio_")
    ]
    assert leaked_workers == []
