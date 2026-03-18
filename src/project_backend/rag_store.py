from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .contracts import EntityReference, RetrievalRequest, RetrievalResult, RetrievalResultItem
from .project_repository import migrate_project


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def load_rag_state(root_path: str | Path) -> Dict:
    root = Path(root_path)
    migrate_project(root)
    rag_dir = root / "system" / "rag"
    docs_dir = rag_dir / "documents"
    chunks_dir = rag_dir / "chunks"
    manifest = json.loads((rag_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(docs_dir.glob("*.json"))]
    chunks = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(chunks_dir.glob("*.json"))]
    return {"manifest": manifest, "documents": documents, "chunks": chunks}


def query_rag(root_path: str | Path, request: RetrievalRequest | Dict) -> Dict:
    state = load_rag_state(root_path)
    request_payload = request if isinstance(request, dict) else request.__dict__
    query_tokens = _tokens(request_payload["query"])
    query_counter = Counter(query_tokens)
    scope_kinds = set(request_payload.get("scope", {}).get("entityKinds", []))
    scoped_ids = set(request_payload.get("scope", {}).get("sourceIds", []))
    filter_ids = set(request_payload.get("filters", {}).get("ids", []))

    docs_by_id = {document["id"]: document for document in state["documents"]}
    scored_items: List[RetrievalResultItem] = []
    for chunk in state["chunks"]:
        document = docs_by_id.get(chunk["documentId"])
        if not document:
            continue
        if scope_kinds and document.get("sourceType") not in scope_kinds:
            continue
        if scoped_ids and document.get("sourceId") not in scoped_ids:
            continue
        if filter_ids and document.get("sourceId") not in filter_ids and chunk["id"] not in filter_ids:
            continue
        keyword_counter = Counter([keyword.lower() for keyword in chunk.get("keywords", [])] + _tokens(chunk.get("text", "")))
        score = 0.0
        for token, weight in query_counter.items():
            score += keyword_counter[token] * weight
        if any(token in _tokens(document.get("title", "")) for token in query_tokens):
            score += 2.0
        if chunk.get("entityRefs"):
            score += 0.5
        if score <= 0:
            continue
        entity_refs = [EntityReference(**ref) for ref in chunk.get("entityRefs", [])]
        scored_items.append(
            RetrievalResultItem(
                chunkId=chunk["id"],
                documentId=chunk["documentId"],
                excerpt=chunk["text"][:240],
                score=round(score, 3),
                entityRefs=entity_refs,
                sourcePath=chunk.get("sourcePath"),
            )
        )

    scored_items.sort(key=lambda item: item.score, reverse=True)
    top_k = int(request_payload.get("topK", 5))
    result = RetrievalResult(
        requestId=request_payload["id"],
        backend=state["manifest"].get("activeBackend", "keyword"),
        items=scored_items[:top_k],
    )
    return {
        "requestId": result.requestId,
        "backend": result.backend,
        "items": [
            {
                "chunkId": item.chunkId,
                "documentId": item.documentId,
                "excerpt": item.excerpt,
                "score": item.score,
                "entityRefs": [ref.__dict__ for ref in item.entityRefs],
                "sourcePath": item.sourcePath,
            }
            for item in result.items
        ],
    }
