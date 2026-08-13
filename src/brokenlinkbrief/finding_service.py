"""Application service for evidence-aware finding and verification workflows."""

from __future__ import annotations

from threading import Lock
from typing import Any

from brokenlinkbrief.confidence import ProbeAttempt, classify_evidence
from brokenlinkbrief.triage import extract_occurrences


class FindingService:
    """Coordinate classification, persistence, and targeted verification."""

    _active: set[str] = set()
    _lock = Lock()

    def __init__(self, store: Any) -> None:
        self.store = store

    def observe(
        self, project_id: str, occurrence: Any, attempts: list[ProbeAttempt]
    ) -> dict[str, Any] | None:
        assessment = classify_evidence(attempts)
        return self.store.upsert(project_id, occurrence, assessment, attempts)

    def verify(
        self,
        finding_id: str,
        version: int,
        target_attempts: list[ProbeAttempt],
        source_bodies: dict[str, str | None],
    ) -> dict[str, Any]:
        with self._lock:
            if finding_id in self._active:
                raise ValueError("FINDING_VERIFICATION_IN_PROGRESS")
            self._active.add(finding_id)
        try:
            detail = self.store.detail(finding_id)
            target = detail["target_url"]
            assessment = classify_evidence(target_attempts)
            checked = 0
            present_count = 0
            failures: list[dict[str, str]] = []
            for source, body in source_bodies.items():
                if body is None:
                    failures.append({"source_url": source, "error": "fetch-failed"})
                    continue
                checked += 1
                present = any(
                    occurrence.target_url == target
                    for occurrence in extract_occurrences(source, body)
                )
                present_count += int(present)
                self.store.reconcile_source(finding_id, source, present)
            if assessment.classification == "RECOVERED":
                outcome = "RECOVERED"
            elif checked and not present_count and not failures:
                outcome = "REMOVED_FROM_SOURCE"
            elif assessment.classification == "CONFIRMED_BROKEN" and present_count:
                outcome = "STILL_BROKEN"
            else:
                outcome = "INCONCLUSIVE"
            finding = self.store.record_verification(
                finding_id,
                version,
                outcome,
                checked,
                present_count,
                failures,
            )
            return {
                "outcome": outcome,
                "finding": finding,
                "target_assessment": assessment.__dict__,
                "sources_checked": checked,
                "sources_present": present_count,
                "source_failures": failures,
            }
        finally:
            with self._lock:
                self._active.discard(finding_id)
