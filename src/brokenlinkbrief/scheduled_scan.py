"""Scheduled scan executor for automated broken link detection.

This module provides the ScheduledScanExecutor class that orchestrates
scheduled scans of project targets, including retry logic, regression
detection, and result aggregation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokenlinkbrief.package import LinkResult, scan_batch


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
    raw_results: dict[str, list[LinkResult]] = field(default_factory=dict)
    regression_flags: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class ScheduledScanExecutor:
    """Execute scheduled scans with retry logic and regression detection.

    This class coordinates the scanning of project targets using the
    package-level scan_batch function, handles retries on transient failures,
    computes summary statistics, and detects regressions against prior scans.

    Args:
        max_retries: Maximum number of retry attempts for failed batch scans.
        retry_delay: Base delay (seconds) between retry attempts with exponential backoff.
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0) -> None:
        """Initialize the executor with retry configuration.

        Args:
            max_retries: Maximum retry attempts for scan failures (default: 3).
            retry_delay: Base delay in seconds between retries (default: 1.0).
        """
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_delay < 0:
            raise ValueError("retry_delay must be non-negative")

        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def execute_scan(self, project_config: dict[str, Any]) -> ScanResult:
        """Execute a full scheduled scan for a project.

        Args:
            project_config: Dictionary containing project configuration with keys:
                - project_id: str
                - project_name: str
                - targets: list[str] (URLs to scan)
                - timeout: float (optional, default 10.0)
                - max_workers: int (optional, default 5)
                - previous_results: dict[str, list[LinkResult]] (optional, for regression detection)

        Returns:
            ScanResult with aggregated results, regression flags, and timing info.

        Raises:
            ValueError: If project_config is missing required fields.
        """
        start_time = time.monotonic()
        scan_timestamp = datetime.now(timezone.utc).isoformat()
        scan_id = uuid.uuid4().hex

        # Validate required fields
        required_fields = ("project_id", "project_name", "targets")
        for field_name in required_fields:
            if field_name not in project_config:
                raise ValueError(f"project_config missing required field: {field_name}")

        project_id = project_config["project_id"]
        project_name = project_config["project_name"]
        targets = project_config["targets"]
        timeout = project_config.get("timeout", 10.0)
        max_workers = project_config.get("max_workers", 5)
        previous_results = project_config.get("previous_results")

        if not isinstance(targets, list) or not targets:
            raise ValueError("targets must be a non-empty list of URLs")

        errors: list[str] = []
        raw_results: dict[str, list[LinkResult]] = {}

        # Run scan with retry logic
        try:
            raw_results = self._run_batch_with_retry(targets, timeout, max_workers)
        except Exception as exc:
            errors.append(f"Batch scan failed after retries: {exc}")

        # Compute summary statistics
        urls_scanned, total_links, broken_count = self._compute_summary(raw_results)

        # Detect regressions against previous scan
        new_broken_count = 0
        regression_flags: list[str] = []
        if previous_results is not None:
            new_broken_count, regression_flags = self._detect_regressions(
                raw_results, previous_results
            )

        # Determine overall status
        if errors:
            status = "failed" if not raw_results else "partial"
        elif urls_scanned == 0:
            status = "failed"
        elif urls_scanned < len(targets):
            status = "partial"
        else:
            status = "completed"

        duration_seconds = time.monotonic() - start_time

        return ScanResult(
            scan_id=scan_id,
            project_id=project_id,
            project_name=project_name,
            scan_timestamp=scan_timestamp,
            urls_scanned=urls_scanned,
            total_links=total_links,
            broken_count=broken_count,
            new_broken_count=new_broken_count,
            status=status,
            raw_results=raw_results,
            regression_flags=regression_flags,
            duration_seconds=duration_seconds,
            errors=errors,
        )

    def _run_batch_with_retry(
        self, urls: list[str], timeout: float, max_workers: int
    ) -> dict[str, list[LinkResult]]:
        """Run scan_batch with exponential backoff retry logic.

        Args:
            urls: List of target URLs to scan.
            timeout: Per-request timeout in seconds.
            max_workers: Maximum concurrent workers.

        Returns:
            Dictionary mapping URL to list of LinkResult objects.

        Raises:
            Exception: Last exception if all retries exhausted.
        """
        last_exception: Exception | None = None
        delay = self._retry_delay

        for attempt in range(self._max_retries + 1):
            try:
                return scan_batch(urls, timeout=timeout, max_workers=max_workers)
            except Exception as exc:
                last_exception = exc
                if attempt < self._max_retries:
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    break

        raise last_exception or RuntimeError("Scan failed after retries")

    def _compute_summary(
        self, raw_results: dict[str, list[LinkResult]]
    ) -> tuple[int, int, int]:
        """Compute aggregate statistics from raw scan results.

        Args:
            raw_results: Dictionary mapping target URL to list of LinkResult.

        Returns:
            Tuple of (urls_scanned, total_links, broken_count).
        """
        urls_scanned = len(raw_results)
        total_links = 0
        broken_count = 0

        for link_results in raw_results.values():
            total_links += len(link_results)
            for result in link_results:
                if self._is_link_broken(result):
                    broken_count += 1

        return urls_scanned, total_links, broken_count

    def _detect_regressions(
        self,
        current_results: dict[str, list[LinkResult]],
        previous_results: dict[str, list[LinkResult]],
    ) -> tuple[int, list[str]]:
        """Detect regressions by comparing current results against previous scan.

        A regression is a link that was previously working (status < 400)
        but is now broken (status >= 400 or fetch error).

        Args:
            current_results: Current scan results keyed by target URL.
            previous_results: Previous scan results keyed by target URL.

        Returns:
            Tuple of (new_broken_count, regression_flags).
        """
        new_broken = 0
        flags: list[str] = []

        # Build a lookup of previously working links by URL
        previous_working: dict[str, LinkResult] = {}
        for link_results in previous_results.values():
            for result in link_results:
                if not self._is_link_broken(result):
                    previous_working[result.url] = result

        # Check current broken links against previous working ones
        for target_url, link_results in current_results.items():
            for result in link_results:
                if self._is_link_broken(result) and result.url in previous_working:
                    new_broken += 1
                    prev = previous_working[result.url]
                    flags.append(
                        f"REGRESSION: {result.url} was working (status={prev.status}) "
                        f"now broken (status={result.status}, reason={result.reason}) "
                        f"[target: {target_url}]"
                    )

        return new_broken, flags

    def _is_link_broken(self, result: LinkResult) -> bool:
        """Determine if a LinkResult represents a broken link.

        A link is considered broken if:
        - HTTP status code >= 400, or
        - Status is None and reason is set (timeout, fetch error, etc.)

        Args:
            result: The LinkResult to evaluate.

        Returns:
            True if the link is broken, False otherwise.
        """
        if result.status is not None:
            return result.status >= 400
        return result.reason is not None and result.reason != ""

    def _format_regression_flags(self, flags: list[str]) -> str:
        """Format regression flags into a single string for storage.

        Args:
            flags: List of regression flag strings.

        Returns:
            Semicolon-separated string, or empty string if no flags.
        """
        if not flags:
            return ""
        return "; ".join(flags)
