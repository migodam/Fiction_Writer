"""W7 — Metadata Ingestion Workflow.

Ingests a reference file (novel, script, news, essay, draft) into:
  - Per-chunk style/vocabulary/structure/knowledge extraction (via LLM)
  - ChromaDB vector store for RAG retrieval by W3 and W5
  - {project_path}/metadata/index.json for file registry

Graph:
  acquire_lock → detect_file_type → copy_to_metadata_folder → chunk_source_file
      → extract_per_chunk (serial all 4 extractors per chunk)
      → build_profiles → embed_and_store_chunks → update_metadata_index → release_lock → END
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from sidecar.models.state import MetadataIngestionState, StyleProfile, KnowledgeProfile
from sidecar.shared import s3_chunk_manager
from sidecar.utils.lock import acquire_lock, release_lock, WorkflowBusyError
from sidecar.prompts.w7_prompts import (
    W7_EXTRACT_STYLE,
    W7_EXTRACT_VOCABULARY,
    W7_EXTRACT_STRUCTURE,
    W7_EXTRACT_KNOWLEDGE,
)
from sidecar.tools.rag import embed_chunks


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_model(state: dict) -> ChatOpenAI:
    ctx = state.get("context", {})
    api_key = ctx.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    model = ctx.get("model", "deepseek-chat")
    base_url = ctx.get("endpoint", "https://api.deepseek.com/v1")
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, max_tokens=4096)


def _parse_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return {}


def _collection_name(project_path: str) -> str:
    project_id = Path(project_path).name
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id)[:40]
    return f"narrative_{safe_id}_metadata"


_EXT_TO_TYPE: dict[str, str] = {
    ".txt": "novel", ".md": "novel", ".epub": "novel",
    ".fountain": "script", ".fdx": "script",
    ".html": "news", ".htm": "news",
}


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def node_acquire_lock(state: dict) -> dict:
    try:
        await acquire_lock(state["project_path"], "W7")
    except WorkflowBusyError as e:
        return {"status": "error", "errors": [str(e)]}
    return {}


async def node_detect_file_type(state: dict) -> dict:
    source = Path(state["source_file_path"])
    ext = source.suffix.lower()
    file_type = state.get("file_type") or _EXT_TO_TYPE.get(ext, "other")
    try:
        sample = source.read_text(encoding="utf-8", errors="ignore")[:500]
        if re.search(r"^(INT\.|EXT\.|FADE IN:)", sample, re.MULTILINE):
            file_type = "script"
    except Exception:
        pass
    return {"file_type": file_type}


async def node_copy_to_metadata_folder(state: dict) -> dict:
    source = Path(state["source_file_path"])
    dest_dir = Path(state["project_path"]) / "metadata" / state["file_id"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"original{source.suffix}"
    shutil.copy2(source, dest)
    return {"progress": 0.05}


async def node_chunk_source_file(state: dict) -> dict:
    source = Path(state["source_file_path"])
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "error", "errors": [str(e)]}

    chunks = s3_chunk_manager.chunk_text(
        text,
        s3_chunk_manager.ChunkConfig(strategy="fixed", chunk_size=500_000, overlap=50_000),
    )
    return {"chunks": chunks, "progress": 0.1}


async def node_extract_per_chunk(state: dict) -> dict:
    """Run all four extractors serially on each chunk."""
    model = _get_model(state)
    file_type = state.get("file_type", "other")
    chunks = state.get("chunks", [])
    total = max(len(chunks), 1)

    per_chunk_styles: list[dict] = []
    per_chunk_vocab: list[dict] = []
    per_chunk_structures: list[dict] = []
    per_chunk_knowledge: list[dict] = []

    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        if not content.strip():
            continue
        excerpt = content[:8000]

        for prompt_tpl, bucket in [
            (W7_EXTRACT_STYLE, per_chunk_styles),
            (W7_EXTRACT_VOCABULARY, per_chunk_vocab),
            (W7_EXTRACT_STRUCTURE, per_chunk_structures),
            (W7_EXTRACT_KNOWLEDGE, per_chunk_knowledge),
        ]:
            try:
                resp = await model.ainvoke([HumanMessage(content=prompt_tpl.format(
                    chunk_content=excerpt, file_type=file_type))])
                bucket.append(_parse_json(resp.content))
            except Exception:
                pass

    return {
        "_per_chunk_styles": per_chunk_styles,
        "_per_chunk_vocab": per_chunk_vocab,
        "_per_chunk_structures": per_chunk_structures,
        "_per_chunk_knowledge": per_chunk_knowledge,
        "progress": 0.7,
    }


async def node_build_profiles(state: dict) -> dict:
    styles = state.get("_per_chunk_styles", [])
    vocabs = state.get("_per_chunk_vocab", [])
    knowledge_chunks = state.get("_per_chunk_knowledge", [])

    valid_style = [s for s in styles if "avg_sentence_length" in s]
    avg_sent_len = (sum(s.get("avg_sentence_length", 0) for s in valid_style) / len(valid_style)) if valid_style else 0.0
    avg_dialogue = (sum(s.get("dialogue_ratio", 0) for s in valid_style) / len(valid_style)) if valid_style else 0.0
    pov_style = styles[0].get("pov_style", "unknown") if styles else "unknown"
    pacing = styles[0].get("pacing_descriptor", "moderate") if styles else "moderate"

    vocab_notes: list[str] = []
    for v in vocabs:
        vocab_notes.extend(v.get("distinctive_words", [])[:3])
        vocab_notes.extend(v.get("phrase_patterns", [])[:2])
    vocab_notes = list(dict.fromkeys(vocab_notes))[:10]

    style_profile: StyleProfile = {
        "avg_sentence_length": round(avg_sent_len, 1),
        "dialogue_ratio": round(avg_dialogue, 3),
        "pov_style": pov_style,
        "pacing_descriptor": pacing,
        "vocabulary_notes": vocab_notes,
    }

    all_facts: list[str] = []
    all_entities: list[str] = []
    all_tags: list[str] = []
    for kc in knowledge_chunks:
        all_facts.extend(kc.get("key_facts", []))
        all_entities.extend(kc.get("named_entities", []))
        all_tags.extend(kc.get("domain_tags", []))

    knowledge_profile: KnowledgeProfile = {
        "key_facts": list(dict.fromkeys(all_facts))[:20],
        "named_entities": list(dict.fromkeys(all_entities))[:30],
        "domain_tags": list(dict.fromkeys(all_tags))[:10],
    }

    return {"style_profile": style_profile, "knowledge_profile": knowledge_profile, "progress": 0.8}


async def node_embed_and_store_chunks(state: dict) -> dict:
    collection = _collection_name(state["project_path"])
    file_id = state["file_id"]
    file_type = state.get("file_type", "other")
    knowledge = state.get("knowledge_profile", {})
    domain_tags = knowledge.get("domain_tags", [])

    chunks = state.get("chunks", [])
    chunk_dicts = [{"content": c.get("content", ""), "chunk_id": c.get("chunk_id", 0)} for c in chunks]

    try:
        embed_chunks(
            chunk_dicts,
            collection,
            {"file_id": file_id, "file_type": file_type, "domain_tags": ",".join(domain_tags)},
        )
        return {"vector_store_updated": True, "progress": 0.9}
    except Exception as e:
        return {"vector_store_updated": False, "errors": [f"chromadb: {e}"], "progress": 0.9}


async def node_update_metadata_index(state: dict) -> dict:
    root = Path(state["project_path"])
    index_path = root / "metadata" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    index: dict = {"files": []}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    source = Path(state["source_file_path"])
    knowledge = state.get("knowledge_profile", {})
    style = state.get("style_profile", {})

    entry = {
        "id": state["file_id"],
        "filename": source.name,
        "type": state.get("file_type", "other"),
        "tags": knowledge.get("domain_tags", []),
        "importedAt": datetime.now(timezone.utc).isoformat(),
        "chunkCount": len(state.get("chunks", [])),
        "status": "ready",
        "style_profile": style,
    }

    files: list[dict] = index.get("files", [])
    files = [f for f in files if f.get("id") != state["file_id"]]
    files.append(entry)
    index["files"] = files

    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "done", "progress": 1.0}


async def node_release_lock(state: dict) -> dict:
    try:
        await release_lock(state["project_path"])
    except Exception:
        pass
    return {}


# ── Graph construction ────────────────────────────────────────────────────────

_graph = None


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(MetadataIngestionState)

    for name, fn in [
        ("acquire_lock", node_acquire_lock),
        ("detect_file_type", node_detect_file_type),
        ("copy_to_metadata_folder", node_copy_to_metadata_folder),
        ("chunk_source_file", node_chunk_source_file),
        ("extract_per_chunk", node_extract_per_chunk),
        ("build_profiles", node_build_profiles),
        ("embed_and_store_chunks", node_embed_and_store_chunks),
        ("update_metadata_index", node_update_metadata_index),
        ("release_lock", node_release_lock),
    ]:
        builder.add_node(name, fn)

    builder.set_entry_point("acquire_lock")
    for a, b in [
        ("acquire_lock", "detect_file_type"),
        ("detect_file_type", "copy_to_metadata_folder"),
        ("copy_to_metadata_folder", "chunk_source_file"),
        ("chunk_source_file", "extract_per_chunk"),
        ("extract_per_chunk", "build_profiles"),
        ("build_profiles", "embed_and_store_chunks"),
        ("embed_and_store_chunks", "update_metadata_index"),
        ("update_metadata_index", "release_lock"),
    ]:
        builder.add_edge(a, b)
    builder.add_edge("release_lock", END)

    memory = MemorySaver()
    _graph = builder.compile(checkpointer=memory)
    return _graph


async def run(project_path: str, config: dict) -> dict:
    file_id = config.get("file_id") or f"meta_{uuid.uuid4().hex[:8]}"
    initial_state: dict = {
        "project_path": project_path,
        "workflow_id": "W7",
        "source_file_path": config.get("source_file_path", ""),
        "file_type": config.get("file_type", "other"),
        "file_id": file_id,
        "chunks": [],
        "style_profile": {
            "avg_sentence_length": 0.0,
            "dialogue_ratio": 0.0,
            "pov_style": "",
            "pacing_descriptor": "",
            "vocabulary_notes": [],
        },
        "knowledge_profile": {"key_facts": [], "named_entities": [], "domain_tags": []},
        "vector_store_updated": False,
        "progress": 0.0,
        "errors": [],
        "status": "running",
        "context": config.get("context", {}),
    }
    thread_id = config.get("thread_id", f"w7-{uuid.uuid4().hex[:8]}")
    graph = get_graph()
    result = await graph.ainvoke(initial_state, {"configurable": {"thread_id": thread_id}})
    return dict(result)
