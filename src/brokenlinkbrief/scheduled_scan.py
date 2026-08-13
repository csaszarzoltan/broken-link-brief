"""Scheduled scan executor for automated broken link detection.

Provides ScheduledScanExecutor for orchestrating scheduled scans with
retry logic, regression detection, and result aggregation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokenlinkbrief.package import scan_batch

# ---------------------------------------------------------------------------
# ScanResult — result of a scheduled scan execution
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    """Result of a scheduled scan execution.

    Attributes:
        scan_id: Unique identifier for this scan execution.
        project_id: Identifier of the project that was scanned.
        project_name: Human-readable name of the project.
        scan_timestamp: ISO 8601 timestamp when the scan started (UTC).
        urls_scanned: Number of target URLs that were scanned.
        total_links: Total number of links discovered across all targets.
        broken_count: Number of broken links found in this scan.
        new_broken_count: Number of newly broken links (regressions).
        status: Overall scan status (e.g., "completed", "partial", "failed").
        raw_results: Raw scan results keyed by target URL.
        regression_flags: List of human-readable regression flag strings.
        duration_seconds: Wall-clock time taken to complete the scan.
        errors: List of error messages encountered during scanning.
    """

    scan_id: str
    project_id: str
    project_name: str
    scan_timestamp: str
    urls_scanned: int
    total_links: int
    broken_count: int
    new_broken_count: int
    status: str
    raw_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    regression_flags: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ScheduledScanExecutor — orchestrate scans with retries
# ---------------------------------------------------------------------------


class ScheduledScanExecutor:
    """Execute scheduled scans with retry logic and regression detection.

    Args:
        max_retries: Maximum number of retry attempts for failed batch scans.
        retry_delay: Base delay (seconds) between retry attempts.
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def execute_scan(self, project_config: dict[str, Any]) -> ScanResult:
        """Execute a full scheduled scan for a project.

        Args:
            project_config: Dict with keys: id, name, urls, options.

        Returns:
            ScanResult with aggregated results and timing info.
        """
        start_time = time.monotonic()
        scan_timestamp = datetime.now(timezone.utc).isoformat()
        scan_id = uuid.uuid4().hex

        project_id = project_config.get("id", project_config.get("project_id", ""))
        pname_key = "project_name"
        project_name = project_config.get("name", project_config.get(pname_key, ""))
        urls = project_config.get("urls", [])
        options = project_config.get("options", {})
        timeout = options.get("timeout", 10.0)
        max_workers = options.get("max_workers", 5)

        errors: list[str] = []
        raw_results: dict[str, list[dict[str, Any]]] = {}

        try:
            batch = self._run_batch_with_retry(urls, timeout, max_workers)
            # Convert LinkResult objects to dicts for JSON serialisation
            for url, results in batch.items():
                raw_results[url] = [
                    {
                        "url": getattr(r, "url", url),
                        "status": getattr(r, "status", None),
                        "reason": getattr(r, "reason", None),
                        "location": getattr(r, "location", None),
                    }
                    for r in results
                ]
        except Exception as exc:
            errors.append(f"Scan failed: {exc}")

        duration_seconds = time.monotonic() - start_time
        summary = self._compute_summary(
            raw_results, project_id, project_name, start_time
        )
        summary.scan_id = scan_id
        summary.scan_timestamp = scan_timestamp
        summary.duration_seconds = duration_seconds
        summary.errors = errors
        if errors:
            summary.status = "partial" if raw_results else "failed"

        return summary

    def _run_batch_with_retry(
        self,
        urls: list[str],
        timeout: float = 10.0,
        max_workers: int = 5,
    ) -> dict[str, Any]:
        """Run scan_batch with retry logic.

        Args:
            urls: List of target URLs to scan.
            timeout: Per-request timeout in seconds.
            max_workers: Maximum concurrent workers.

        Returns:
            Dictionary mapping URL to list of LinkResult objects.
        """
        if not urls:
            return {}

        last_exc: Exception | None = None
        delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            try:
                return scan_batch(urls, timeout=timeout, max_workers=max_workers)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2

        raise last_exc or RuntimeError("scan failed")

    def _detect_regressions(
        self,
        current_results: dict[str, list[dict[str, Any]]],
        previous_results: list[dict[str, Any]] | None,
    ) -> tuple[int, list[str]]:
        """Detect regressions by comparing current vs previous results.

        Args:
            current_results: Current scan results keyed by URL.
            previous_results: Previous scan results as flat list of dicts.

        Returns:
            Tuple of (new_broken_count, regression_flags).
        """
        if not previous_results:
            return 0, []

        # Build lookup of previously working links
        prev_working: dict[str, dict[str, Any]] = {}
        for link in previous_results:
            if not self._is_link_broken(link):
                prev_working[link.get("url", "")] = link

        new_broken = 0
        flags: list[str] = []

        for url, links in current_results.items():
            for link in links:
                if self._is_link_broken(link):
                    link_url = link.get("url", url)
                    if link_url in prev_working:
                        new_broken += 1
                        prev = prev_working[link_url]
                        flags.append(
                            f"new_broken:{link_url} "
                            f"(was {prev.get('status', 'N/A')}, "
                            f"now {link.get('status', 'N/A')})"
                        )

        return new_broken, flags

    def _is_link_broken(self, result: dict[str, Any]) -> bool:
        """Check if a link result dict represents a broken link."""
        status = result.get("status")
        reason = result.get("reason")
        if status is not None:
            return status >= 400
        return reason is not None

    def _format_regression_flags(
        self,
        new_broken_urls: list[str],
        status_changes: list[tuple[str, str, str]],
    ) -> list[str]:
        """Format regression information into flag strings.

        Args:
            new_broken_urls: List of newly broken URLs.
            status_changes: List of (url, old_status, new_status) tuples.

        Returns:
            List of human-readable flag strings.
        """
        flags: list[str] = []
        for url in new_broken_urls:
            flags.append(f"new_broken:{url}")
        for url, old, new in status_changes:
            flags.append(f"status_change:{url}:{old}->{new}")
        return flags

    def _compute_summary(
        self,
        scan_results: dict[str, list[dict[str, Any]]],
        project_id: str,
        project_name: str,
        start_time: float,
    ) -> ScanResult:
        """Compute summary statistics from scan results.

        Args:
            scan_results: Dict mapping URL to list of link result dicts.
            project_id: Project identifier.
            project_name: Project name.
            start_time: time.time() start for duration calculation.

        Returns:
            ScanResult with computed statistics.
        """
        scan_id = uuid.uuid4().hex
        scan_timestamp = datetime.now(timezone.utc).isoformat()

        total_links = 0
        broken_count = 0
        for links in scan_results.values():
            total_links += len(links)
            for link in links:
                if self._is_link_broken(link):
                    broken_count += 1

        duration = time.time() - start_time

        return ScanResult(
            scan_id=scan_id,
            project_id=project_id,
            project_name=project_name,
            scan_timestamp=scan_timestamp,
            urls_scanned=len(scan_results),
            total_links=total_links,
            broken_count=broken_count,
            new_broken_count=0,
            status="completed",
            raw_results=scan_results,
            regression_flags=[],
            duration_seconds=duration,
            errors=[],
        )
