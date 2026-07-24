"""Bounded W1 planner proposal generation.

The default path is deterministic and makes no provider call.  An explicitly
approved live path accepts an injected callback only, so this module neither
reads provider configuration nor API keys.  Both paths emit the same typed
``PlannerProposal`` and deterministic validation remains authoritative.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping

from sidecar.models.state import (
    PlannerProposal,
    analyze_source_profile,
    select_granularity_profile,
)
from sidecar.supervisor.planner import validate_planner_proposal
from sidecar.supervisor.prompt_policy import normalize_prompt_policy_patch


_FENCED_JSON_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class PlannerLiveCallError(RuntimeError):
    """A concise, safe live-planner failure suitable for a durable record."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        self.retry_authorization: dict[str, Any] | None = None
        super().__init__(message)


class PlannerUnknownOutcomeError(PlannerLiveCallError):
    """The provider may have received a paid request but no result is usable."""

    def __init__(self) -> None:
        super().__init__(
            "unknown_outcome",
            "live planner outcome is unknown; explicit retry authorization is required",
        )


PlannerModelCallback = Callable[[dict[str, Any]], str | bytes | Mapping[str, Any]]
_RETRY_REQUIRED_ERROR_CODES = frozenset({
    "unknown_outcome",
    "provider_failed",
    "response_invalid",
    "provider_response_invalid",
})


def _approval_record(state: dict[str, Any]) -> dict[str, Any] | None:
    context = state.get("context")
    if not isinstance(context, dict):
        return None
    approval = context.get("planner_live_approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return None
    decision_id = approval.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id.strip():
        return None
    return {"decision_id": decision_id.strip()}


def _retry_authorization_record(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return one new retry authorization, or block a prior uncertain call.

    A retry is scoped to a durable decision record.  Reusing its authorization
    ID is deliberately inert, so reconstructing the same state after restart
    cannot fan out another potentially billable call.
    """
    prior = state.get("planner_decision_record")
    if not isinstance(prior, dict) or prior.get("error_code") not in _RETRY_REQUIRED_ERROR_CODES:
        return None

    context = state.get("context")
    authorization = context.get("planner_live_retry_authorization") if isinstance(context, dict) else None
    if not isinstance(authorization, dict) or authorization.get("approved") is not True:
        raise PlannerUnknownOutcomeError()
    decision_id = authorization.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id.strip():
        raise PlannerUnknownOutcomeError()
    retry_id = decision_id.strip()
    consumed_id = str(prior.get("retry_authorization_decision_id") or "")
    original_id = str(prior.get("approval_decision_id") or "")
    if retry_id == consumed_id or retry_id == original_id:
        raise PlannerUnknownOutcomeError()
    return {"decision_id": retry_id}


def _decision_record(
    *,
    mode: str,
    status: str,
    approval: dict[str, Any] | None = None,
    retry_authorization: dict[str, Any] | None = None,
    proposal: PlannerProposal | None = None,
    error: PlannerLiveCallError | None = None,
) -> dict[str, Any]:
    """Return audit-safe metadata; never retain prompts, secrets, or reasoning."""
    record: dict[str, Any] = {
        "schema": "planner-decision-record-v1",
        "mode": mode,
        "status": status,
    }
    if approval:
        record["approval_decision_id"] = approval["decision_id"]
    if retry_authorization:
        record["retry_authorization_decision_id"] = retry_authorization["decision_id"]
    if proposal is not None:
        canonical = json.dumps(proposal, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        record["proposal_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record["evidence_questions"] = list(proposal.get("evidence_questions") or [])
        record["proposed_actions"] = list(proposal.get("proposed_actions") or [])
        record["budget_adjustment"] = dict(proposal.get("budget_adjustment") or {})
    if error is not None:
        record["error_code"] = error.code
        record["error"] = error.safe_message
    return record


def _payload_from_provider_result(result: str | bytes | Mapping[str, Any]) -> str | bytes:
    if isinstance(result, (str, bytes)):
        return result
    if not isinstance(result, Mapping):
        raise PlannerLiveCallError("provider_response_invalid", "live planner returned an invalid response")
    if str(result.get("status") or "") == "unknown_outcome":
        raise PlannerUnknownOutcomeError()
    proposal = result.get("proposal")
    if isinstance(proposal, Mapping):
        return json.dumps(dict(proposal), ensure_ascii=False, sort_keys=True)
    content = result.get("content")
    if isinstance(content, (str, bytes)):
        return content
    raise PlannerLiveCallError("provider_response_invalid", "live planner did not return JSON content")


def _chapter_count(state: dict[str, Any]) -> int:
    chunks = state.get("chunks")
    if isinstance(chunks, list):
        return len(chunks)
    source_profile = state.get("source_profile")
    if isinstance(source_profile, dict):
        try:
            return max(int(source_profile.get("chapter_count", 0)), 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _source_profile(state: dict[str, Any]) -> dict[str, Any]:
    existing = state.get("source_profile")
    if isinstance(existing, dict) and existing:
        return dict(existing)
    return dict(
        analyze_source_profile(
            state.get("chunks", []) if isinstance(state.get("chunks"), list) else [],
            source_language=str(state.get("source_language", "en") or "en"),
            prompt_profile=str(state.get("prompt_profile", "balanced") or "balanced"),
        )
    )


def build_planner_proposal_prompt_context(state: dict[str, Any]) -> dict[str, Any]:
    """Build bounded, schema-oriented context for a future planner prompt."""
    source_language = str(state.get("source_language", "en") or "en")
    prompt_profile = str(state.get("prompt_profile", "balanced") or "balanced")
    chapter_count = _chapter_count(state)
    source_profile = _source_profile(state)
    granularity_profile = state.get("import_granularity_profile")
    if not isinstance(granularity_profile, dict) or not granularity_profile:
        granularity_profile = select_granularity_profile(
            chapter_count,
            source_language,
            prompt_profile,
        )

    return {
        "schema": "PlannerProposal",
        "source_language": source_language,
        "prompt_profile": prompt_profile,
        "chapter_count": chapter_count,
        "source_profile": source_profile,
        "recommended_granularity_profile": dict(granularity_profile),
        "tool_operating_spec": dict(state.get("tool_operating_spec") or {}),
        "allowed_prompt_policy_patch_keys": [
            "emphasize_existing_timeline_topology",
            "require_source_provenance",
            "prefer_canonical_events",
            "suppress_minor_npcs",
            "relationship_evidence_required",
            "world_boundary_strictness",
            "event_density_strategy",
            "topology_fidelity",
            "world_model_scope",
            "timeline_label_granularity",
            "reviewer_mode",
            "rerun_scope",
            "organizer_strictness",
        ],
        "proposal_limits": {
            "max_proposed_actions": 4,
            "allowed_action_kinds": ["tool", "rerun", "stop"],
            "allowed_action_scopes": ["current_import", "window"],
            "max_evidence_questions": 3,
            "max_additional_calls": 2,
            "max_additional_cost_usd": 0.25,
        },
        "safety_contract": {
            "llm_planner_can_propose_only": True,
            "raw_prompt_text_allowed": False,
            "dynamic_prompt_edits_allowed": False,
        },
    }


def parse_planner_proposal_json(payload: str | bytes) -> PlannerProposal:
    """Parse and validate a PlannerProposal JSON payload."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if not isinstance(payload, str):
        raise TypeError("payload must be str or bytes")

    match = _FENCED_JSON_RE.match(payload)
    raw = match.group(1) if match else payload
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("PlannerProposal payload must decode to an object")

    ok, errors = validate_planner_proposal(parsed)
    if not ok:
        raise ValueError(f"Invalid PlannerProposal: {errors}")
    if "prompt_policy_patch" in parsed:
        parsed["prompt_policy_patch"] = normalize_prompt_policy_patch(
            parsed.get("prompt_policy_patch")
        )
    return parsed  # type: ignore[return-value]


def generate_planner_proposal_stub(state: dict[str, Any]) -> PlannerProposal:
    """Generate a deterministic proposal shaped like the future LLM output."""
    context = build_planner_proposal_prompt_context(state)
    source_profile = dict(context["source_profile"])
    proposed_source_type = str(
        source_profile.get(
            "recommended_granularity_profile",
            source_profile.get("estimated_source_type", "balanced_novel"),
        )
    )
    granularity_profile = dict(context["recommended_granularity_profile"])
    granularity_profile["profile_name"] = proposed_source_type

    proposal: PlannerProposal = {
        "planner_kind": "llm_proposed",
        "source_profile": source_profile,  # type: ignore[typeddict-item]
        "proposed_source_type": proposed_source_type,  # type: ignore[typeddict-item]
        "proposed_granularity_profile": granularity_profile,  # type: ignore[typeddict-item]
        "rationale": "zero-cost deterministic stub for validator integration",
        "confidence": float(source_profile.get("confidence", 0.5) or 0.5),
        "safety_notes": [
            "stub performs no model call",
            "stub does not read API keys",
        ],
        "prompt_policy_patch": {},
    }
    ok, errors = validate_planner_proposal(proposal)
    if not ok:
        raise ValueError(f"Generated PlannerProposal stub failed validation: {errors}")
    return proposal


def generate_live_planner_proposal(
    state: dict[str, Any],
    *,
    model_callback: PlannerModelCallback | None,
) -> tuple[PlannerProposal, dict[str, Any]]:
    """Generate one validated proposal from an approved injected callback.

    This function intentionally has no retry loop.  In particular, an unknown
    provider outcome stays blocked until a higher-level durable human decision
    explicitly authorizes a retry.
    """
    approval = _approval_record(state)
    if approval is None:
        error = PlannerLiveCallError(
            "approval_required",
            "live planner requires explicit planner_live_approval with a decision_id; no model call was made",
        )
        raise error
    retry_authorization = _retry_authorization_record(state)
    if not callable(model_callback):
        raise PlannerLiveCallError(
            "provider_missing",
            "live planner requires an explicitly injected model callback",
        )

    request = build_planner_proposal_prompt_context(state)
    try:
        response = model_callback(request)
        proposal = parse_planner_proposal_json(_payload_from_provider_result(response))
    except PlannerUnknownOutcomeError as exc:
        exc.retry_authorization = retry_authorization
        raise
    except PlannerLiveCallError:
        # A response existed but cannot be trusted as a completed operation.
        # Treat it as uncertain rather than trying another paid call.
        error = PlannerUnknownOutcomeError()
        error.retry_authorization = retry_authorization
        raise error from None
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        error = PlannerUnknownOutcomeError()
        error.retry_authorization = retry_authorization
        raise error from None
    except Exception:
        # The callback may have dispatched a paid request before it raised.
        # Do not expose provider details or retry without a new decision.
        error = PlannerUnknownOutcomeError()
        error.retry_authorization = retry_authorization
        raise error from None

    return proposal, _decision_record(
        mode="live",
        status="accepted",
        approval=approval,
        retry_authorization=retry_authorization,
        proposal=proposal,
    )


def build_live_planner_failure_record(
    state: dict[str, Any], error: PlannerLiveCallError,
    *, retry_authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the safe decision record used by the policy gate on failure."""
    return _decision_record(
        mode="live",
        status="blocked",
        approval=_approval_record(state),
        retry_authorization=retry_authorization,
        error=error,
    )
