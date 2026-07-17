from __future__ import annotations

from .models import OpenQuestion


class SelfAsk:
    """Produces only bounded evidence requests; it never tries to answer them."""

    def __init__(self, max_questions: int, max_rounds: int) -> None:
        self.max_questions = max_questions
        self.max_rounds = max_rounds
        self._round = 0

    def ask(self, candidates: tuple[str, ...], resolved: set[str]) -> tuple[OpenQuestion, ...]:
        if self._round >= self.max_rounds:
            return ()
        self._round += 1
        unresolved = [candidate for candidate in candidates if candidate and candidate not in resolved]
        return tuple(
            OpenQuestion(
                question_id=f"q-{self._round}-{index}",
                subject=subject,
                prompt=f"What evidence resolves: {subject}?",
                evidence_required="verifiable source or tool result",
                round_number=self._round,
            )
            for index, subject in enumerate(unresolved[: self.max_questions], start=1)
        )
