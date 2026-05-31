"""Abstract base class for W1 quality reviewers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Literal

from sidecar.supervisor.reviewers.schemas import (
    OrchestratorRequest,
    RepairAction,
    ReviewFinding,
    ReviewReport,
    ZeroCostLedger,
)


class BaseReviewer(ABC):
    @property
    @abstractmethod
    def reviewer_name(self) -> Literal["quality", "fact", "consistency"]: ...

    @abstractmethod
    def review(self, state: dict) -> ReviewReport: ...

    def _zero_ledger(self, windows: int = 0) -> ZeroCostLedger:
        return ZeroCostLedger(
            live_model_calls=False,
            full50_run=False,
            model_used=None,
            estimated_api_calls=0,
            estimated_prompt_windows=windows,
        )

    def _finding(
        self,
        check_name: str,
        description: str,
        severity: Literal["low", "medium", "high"],
        entity_refs: List[str] | None = None,
        evidence_refs: List[str] | None = None,
        entity_id: str = "0",
    ) -> ReviewFinding:
        return ReviewFinding(
            finding_id=f"{check_name}_{entity_id}",
            check_name=check_name,
            description=description,
            severity=severity,
            entity_refs=entity_refs or [],
            evidence_refs=evidence_refs or [],
        )

    def _repair(
        self,
        action_type: str,
        target_ids: List[str],
        description: str,
        deterministic: bool = True,
    ) -> RepairAction:
        return RepairAction(
            action_type=action_type,
            target_entity_ids=target_ids,
            description=description,
            deterministic=deterministic,
        )

    def _orch_req(
        self,
        request_type: Literal["rerun_window", "reclassify_entity", "merge_entity"],
        theme: str,
        windows: List[str],
        repair: str,
        priority: Literal["low", "medium", "high"] = "medium",
    ) -> OrchestratorRequest:
        return OrchestratorRequest(
            request_type=request_type,
            theme=theme,
            target_windows=windows,
            expected_repair=repair,
            priority=priority,
        )

    def _build_report(
        self,
        findings: List[ReviewFinding],
        repairs: List[RepairAction],
        orch_reqs: List[OrchestratorRequest],
        windows: int = 0,
    ) -> ReviewReport:
        if not findings:
            verdict: Literal["pass", "warn", "needs_repair", "needs_orchestrator_rerun"] = "pass"
            severity: Literal["low", "medium", "high"] = "low"
        else:
            severities = [f["severity"] for f in findings]
            has_high = "high" in severities
            max_severity: Literal["low", "medium", "high"] = (
                "high" if has_high else ("medium" if "medium" in severities else "low")
            )
            if not has_high:
                verdict = "warn"
                severity = max_severity
            elif orch_reqs:
                verdict = "needs_orchestrator_rerun"
                severity = "high"
            else:
                verdict = "needs_repair"
                severity = "high"

        return ReviewReport(
            reviewer=self.reviewer_name,
            verdict=verdict,
            severity=severity,
            findings=findings,
            local_repair_actions=repairs,
            orchestrator_requests=orch_reqs,
            token_cost_ledger=self._zero_ledger(windows),
        )
