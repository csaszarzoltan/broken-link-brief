"""Regression detection between scan results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LinkResult:
    """Result for a single link check."""
    url: str
    status: int | None = None
    reason: str | None = None


def is_broken(result: LinkResult) -> bool:
    """Check if a link result indicates a broken link.

    A link is broken if:
    - status >= 400, or
    - status is None and reason is set (timeout/fetch error).
    """
    raise NotImplementedError("is_broken not yet implemented")


def detect_regressions(
    current_results: list[LinkResult],
    previous_results: list[LinkResult] | None,
) -> tuple[int, list[str]]:
    """Compare current scan against previous scan for regressions.

    Returns:
        (new_broken_count, regression_flags)
    """
    raise NotImplementedError("detect_regressions not yet implemented")


def compute_results_hash(results: list[LinkResult]) -> str:
    """Compute SHA-256 hash of link results for change detection.

    The hash is based on (url, status) pairs only, ignoring timestamps.
    Returns a 64-character hex string.
    """
    raise NotImplementedError("compute_results_hash not yet implemented")
