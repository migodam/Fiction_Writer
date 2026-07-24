"""Durable per-chunk truth contracts for W1 imports.

Keeping manuscript text is useful after a failed extraction, but it must never
be confused with a complete semantic extraction.  This module is deliberately
storage-agnostic so both W1 execution paths and checkpoint recovery share the
same definition of completion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict


ChunkTruth = Literal["semantic_complete", "manuscript_only", "failed", "unknown_outcome"]
DomainStatus = Literal["complete", "failed", "unknown", "not_applicable"]

SEMANTIC_DOMAINS = ("characters", "events", "world", "relationships", "scenes")


class ChunkTruthReceipt(TypedDict):
    chunk_id: int
    truth: ChunkTruth
    domain_receipts: dict[str, DomainStatus]
    failure_codes: list[str]


def domain_receipts(
    *,
    complete_domains: tuple[str, ...] | list[str] = SEMANTIC_DOMAINS,
    failed_domains: tuple[str, ...] | list[str] = (),
    unknown_domains: tuple[str, ...] | list[str] = (),
) -> dict[str, DomainStatus]:
    """Produce a total domain receipt, including domains not run by legacy W1."""
    complete = set(complete_domains)
    failed = set(failed_domains)
    unknown = set(unknown_domains)
    return {
        domain: "unknown" if domain in unknown else "failed" if domain in failed else "complete" if domain in complete else "not_applicable"
        for domain in SEMANTIC_DOMAINS
    }


def attach_truth(
    extraction: dict[str, Any],
    *,
    truth: ChunkTruth,
    receipts: dict[str, DomainStatus],
    failure_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Return an extraction with an explicit, validated truth receipt."""
    result = dict(extraction)
    result["chunk_truth"] = truth
    result["domain_receipts"] = dict(receipts)
    result["failure_codes"] = list(failure_codes or [])
    return result


def semantic_complete(extraction: dict[str, Any], *, complete_domains: tuple[str, ...] | list[str] = SEMANTIC_DOMAINS) -> dict[str, Any]:
    return attach_truth(
        extraction,
        truth="semantic_complete",
        receipts=domain_receipts(complete_domains=complete_domains),
    )


def manuscript_only(extraction: dict[str, Any], *, failure_codes: list[str] | None = None) -> dict[str, Any]:
    return attach_truth(
        extraction,
        truth="manuscript_only",
        receipts=domain_receipts(),
        failure_codes=failure_codes,
    )


def failed_extraction(
    chunk: dict[str, Any],
    *,
    error: str,
    failure_code: str = "extraction_failed",
    legacy: bool = False,
) -> dict[str, Any]:
    """Preserve source text while making the semantic failure non-resumable."""
    raw = chunk.get("manuscript_content", chunk.get("raw_content", chunk.get("content", "")))
    return attach_truth(
        {
            "chunk_id": int(chunk.get("chunk_id", 0) or 0),
            "new_characters": [],
            "updated_aliases": [],
            "events": [],
            "world_mentions": [],
            "world_mentions_detailed": [],
            "raw_relationships": [],
            "scenes": [],
            "chapter_hint": chunk.get("chapter_hint"),
            "manuscript_content": raw,
            "notes": [f"Extraction failed: {error}"],
        },
        truth="failed",
        receipts=domain_receipts(
            complete_domains=(),
            failed_domains=("characters", "events", "world") if legacy else SEMANTIC_DOMAINS,
        ),
        failure_codes=[failure_code],
    )


def truth_receipt(extraction: dict[str, Any]) -> ChunkTruthReceipt:
    """Validate and normalize a receipt stored on an extraction record."""
    chunk_id = extraction.get("chunk_id")
    truth = extraction.get("chunk_truth")
    receipts = extraction.get("domain_receipts")
    if not isinstance(chunk_id, int):
        raise ValueError("Chunk truth receipt requires an integer chunk_id")
    if truth not in {"semantic_complete", "manuscript_only", "failed", "unknown_outcome"}:
        raise ValueError(f"Chunk {chunk_id} is missing a valid chunk_truth")
    if not isinstance(receipts, dict) or set(receipts) != set(SEMANTIC_DOMAINS):
        raise ValueError(f"Chunk {chunk_id} is missing complete domain receipts")
    if any(status not in {"complete", "failed", "unknown", "not_applicable"} for status in receipts.values()):
        raise ValueError(f"Chunk {chunk_id} has an invalid domain receipt")
    if truth == "semantic_complete" and any(status not in {"complete", "not_applicable"} for status in receipts.values()):
        raise ValueError(f"Chunk {chunk_id} cannot be semantic_complete with failed or unknown domains")
    return {
        "chunk_id": chunk_id,
        "truth": truth,
        "domain_receipts": dict(receipts),
        "failure_codes": [str(code) for code in extraction.get("failure_codes", []) if str(code)],
    }


def committed_chunk_ids(extractions: list[dict[str, Any]]) -> list[int]:
    """Return the contiguous semantic-complete prefix eligible for recovery."""
    by_id: dict[int, dict[str, Any]] = {}
    for extraction in extractions:
        receipt = truth_receipt(extraction)
        if receipt["chunk_id"] in by_id:
            raise ValueError(f"Duplicate chunk truth receipt for chunk {receipt['chunk_id']}")
        by_id[receipt["chunk_id"]] = extraction
    committed: list[int] = []
    while True:
        chunk_id = len(committed)
        extraction = by_id.get(chunk_id)
        if extraction is None or extraction.get("chunk_truth") != "semantic_complete":
            return committed
        committed.append(chunk_id)


def durable_failures(attempt_dir: str | Path, checkpoint_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read failure facts from durable artifacts, never from process-local logs."""
    root = Path(attempt_dir)
    findings: list[dict[str, Any]] = []
    for path in sorted((root / "chunks").glob("chunk_*_failures.json")) if (root / "chunks").exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            findings.append({"chunk_id": None, "errors": [f"Unreadable durable failure artifact: {path.name}"], "source": "failure_artifact"})
            continue
        failures = payload.get("failures", []) if isinstance(payload, dict) else []
        if failures:
            findings.append({
                "chunk_id": payload.get("chunk_id"),
                "errors": [str(item.get("error") or item) for item in failures],
                "source": "failure_artifact",
            })
    payload = checkpoint_payload
    if payload is None:
        checkpoint_path = root / "checkpoint.json"
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            payload = {}
    for receipt in payload.get("chunk_truth_receipts", []) if isinstance(payload, dict) else []:
        if isinstance(receipt, dict) and receipt.get("truth") in {"failed", "unknown_outcome"}:
            findings.append({
                "chunk_id": receipt.get("chunk_id"),
                "errors": list(receipt.get("failure_codes") or [str(receipt.get("truth"))]),
                "source": "checkpoint",
            })
    unique: dict[tuple[Any, tuple[str, ...], str], dict[str, Any]] = {}
    for finding in findings:
        key = (finding.get("chunk_id"), tuple(finding.get("errors", [])), str(finding.get("source", "")))
        unique[key] = finding
    return list(unique.values())
