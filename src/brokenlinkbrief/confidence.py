"""Evidence-based link confidence classification."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeAttempt:
    """A single probe of a link."""

    method: str
    status: int | None
    error: str | None
    latency_seconds: float


@dataclass(frozen=True)
class ConfidenceAssessment:
    """Classification of a link based on collected probe evidence."""

    classification: str
    evidence_count: int
    reason: str


def classify_evidence(attempts: list[ProbeAttempt]) -> ConfidenceAssessment:
    """Classify link confidence from probe attempts.

    Returns one of: UNVERIFIED, BOT_BLOCKED, RECOVERED, CONFIRMED_BROKEN,
    TRANSIENT, INCONCLUSIVE.
    """
    if not attempts:
        return ConfidenceAssessment("UNVERIFIED", 0, "no evidence")
    statuses = {a.status for a in attempts}
    if 403 in statuses and any(
        s is not None and 200 <= s < 400 for s in statuses
    ):
        return ConfidenceAssessment(
            "BOT_BLOCKED",
            len(attempts),
            "restricted client and successful probe disagree",
        )
    if any(s is not None and 200 <= s < 400 for s in statuses):
        return ConfidenceAssessment(
            "RECOVERED", len(attempts), "at least one successful response"
        )
    stable = [s for s in statuses if s is not None and s in {404, 410}]
    if stable and len(attempts) >= 2:
        return ConfidenceAssessment(
            "CONFIRMED_BROKEN", len(attempts), "stable terminal status repeated"
        )
    if all(a.error for a in attempts):
        return ConfidenceAssessment(
            "TRANSIENT", len(attempts), "only transport failures observed"
        )
    return ConfidenceAssessment(
        "INCONCLUSIVE", len(attempts), "evidence is insufficient or contradictory"
    )
