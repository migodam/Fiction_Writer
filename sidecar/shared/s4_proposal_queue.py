"""S4 — Proposal Queue

Thin wrapper around {project_path}/system/inbox.json for proposal routing.
Matches the path written by projectService.ts (line 465: system/inbox.json).

Cascade rules:
  - reject_proposal: marks all proposals whose dependsOn includes the rejected ID as "blocked"
  - apply_proposal:  checks all dependsOn IDs are accepted before applying;
                     after apply, unblocks proposals that were waiting on this one
"""

import json
import pathlib
import uuid
from datetime import datetime, timezone


def _inbox_path(project_path: str) -> pathlib.Path:
    return pathlib.Path(project_path) / "system" / "inbox.json"


def _history_path(project_path: str) -> pathlib.Path:
    return pathlib.Path(project_path) / "system" / "history.json"


def _read_inbox(project_path: str) -> list[dict]:
    p = _inbox_path(project_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_inbox(project_path: str, proposals: list[dict]) -> None:
    p = _inbox_path(project_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_history(project_path: str) -> list[dict]:
    p = _history_path(project_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_history(project_path: str, history: list[dict]) -> None:
    p = _history_path(project_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


async def push_to_inbox(proposal: dict, project_path: str) -> None:
    """Append a proposal to system/inbox.json."""
    proposals = _read_inbox(project_path)
    # Avoid duplicates by ID
    if not any(p.get("id") == proposal.get("id") for p in proposals):
        proposals.append(proposal)
    _write_inbox(project_path, proposals)


async def apply_proposal(proposal_id: str, project_path: str) -> dict:
    """Apply a proposal: check dependencies, write to project, move to history.

    Raises ValueError if any dependency is pending or rejected.
    """
    proposals = _read_inbox(project_path)
    proposal = next((p for p in proposals if p.get("id") == proposal_id), None)
    if proposal is None:
        raise ValueError(f"Proposal {proposal_id!r} not found in inbox")

    # Check dependencies
    depends_on = proposal.get("dependsOn") or proposal.get("depends_on") or []
    for dep_id in depends_on:
        dep = next((p for p in proposals if p.get("id") == dep_id), None)
        if dep is None:
            # Dep already applied (not in inbox) — OK
            history = _read_history(project_path)
            dep_hist = next((h for h in history if h.get("id") == dep_id), None)
            if dep_hist and dep_hist.get("status") != "accepted":
                raise ValueError(
                    f"Dependency {dep_id!r} was {dep_hist.get('status')}, cannot apply"
                )
        elif dep.get("status") not in ("accepted",):
            raise ValueError(
                f"Dependency {dep_id!r} is {dep.get('status')!r}, cannot apply yet"
            )

    # Mark accepted and move to history
    proposal["status"] = "accepted"
    proposal["resolvedAt"] = datetime.now(timezone.utc).isoformat()
    remaining = [p for p in proposals if p.get("id") != proposal_id]

    # Unblock proposals that were waiting on this one
    for p in remaining:
        if p.get("status") == "blocked":
            deps = p.get("dependsOn") or p.get("depends_on") or []
            if proposal_id in deps:
                # Check if all other deps are now resolved
                all_clear = all(
                    next(
                        (
                            other.get("status") in ("accepted",)
                            or other is None
                        ),
                        True,
                    )
                    for dep_id in deps
                    if dep_id != proposal_id
                    for other in [next((x for x in remaining if x.get("id") == dep_id), None)]
                )
                if all_clear:
                    p["status"] = "pending"

    _write_inbox(project_path, remaining)
    history = _read_history(project_path)
    history.append(proposal)
    _write_history(project_path, history)

    return proposal


async def reject_proposal(proposal_id: str, project_path: str) -> dict:
    """Reject a proposal and cascade-block all proposals that depend on it."""
    proposals = _read_inbox(project_path)
    proposal = next((p for p in proposals if p.get("id") == proposal_id), None)
    if proposal is None:
        raise ValueError(f"Proposal {proposal_id!r} not found in inbox")

    proposal["status"] = "rejected"
    proposal["resolvedAt"] = datetime.now(timezone.utc).isoformat()

    # Cascade: block all proposals whose dependsOn includes this id
    _cascade_block(proposal_id, proposals)

    # Move rejected proposal to history
    remaining = [p for p in proposals if p.get("id") != proposal_id]
    _write_inbox(project_path, remaining)
    history = _read_history(project_path)
    history.append(proposal)
    _write_history(project_path, history)

    return proposal


def _cascade_block(rejected_id: str, proposals: list[dict]) -> None:
    """Recursively mark all proposals that depend on rejected_id as blocked."""
    to_block = [
        p
        for p in proposals
        if p.get("id") != rejected_id
        and rejected_id in (p.get("dependsOn") or p.get("depends_on") or [])
        and p.get("status") not in ("rejected", "accepted", "blocked")
    ]
    for p in to_block:
        p["status"] = "blocked"
        # Recurse: block anything that depended on the newly blocked proposal
        _cascade_block(p["id"], proposals)


def get_proposal(proposal_id: str, project_path: str) -> dict | None:
    """Retrieve a proposal from the inbox by ID."""
    proposals = _read_inbox(project_path)
    return next((p for p in proposals if p.get("id") == proposal_id), None)


def list_proposals(project_path: str, status: str | None = None) -> list[dict]:
    """List proposals, optionally filtered by status."""
    proposals = _read_inbox(project_path)
    if status:
        return [p for p in proposals if p.get("status") == status]
    return proposals
