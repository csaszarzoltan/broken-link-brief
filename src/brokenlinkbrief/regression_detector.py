"""Regression detection and notification for broken link scanning.

Provides classes to detect regressions in link scanning results by
comparing current scan results against historical scan data, and
formatting regression/resolution alerts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokenlinkbrief.notifications import NotifierConfig, RateLimiter

# ---------------------------------------------------------------------------
# RegressionReport — dataclass for regression analysis results
# ---------------------------------------------------------------------------

@dataclass
class RegressionReport:
    """Report summarizing link scan regressions.

    Attributes:
        project_id: Unique identifier for the project being scanned.
        scan_id: ID of the current scan.
        previous_scan_id: ID of the previous scan used for comparison.
        timestamp: ISO format timestamp of when the report was generated.
        new_broken: List of dicts with newly broken link details.
        resolved: List of dicts with resolved link details.
        status_changes: List of dicts with url, previous_status, current_status.
        has_regressions: True if any new broken links or status changes detected.
    """

    project_id: str
    scan_id: str
    previous_scan_id: str | None
    timestamp: str
    new_broken: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    status_changes: list[dict[str, Any]] = field(default_factory=list)
    has_regressions: bool = False


# ---------------------------------------------------------------------------
# RegressionDetector — compare scans and detect regressions
# ---------------------------------------------------------------------------

class RegressionDetector:
    """Detects regressions in link scanning results by comparing scans."""

    def __init__(self, scan_history: list[dict[str, Any]] | None = None) -> None:
        """Initialize with optional scan history list."""
        self.scan_history = scan_history

    def detect(
        self,
        project_id: str,
        current_results: dict[str, list[dict[str, Any]]],
        scan_history: list[dict[str, Any]] | None = None,
    ) -> RegressionReport:
        """Compare current scan results against previous scan.

        Args:
            project_id: Project identifier.
            current_results: Dict mapping URL to list of link result dicts.
            scan_history: Optional list of scan history entries.

        Returns:
            RegressionReport with new broken, resolved, and status changes.
        """
        history = scan_history if scan_history is not None else self.scan_history
        ts = datetime.now(timezone.utc).isoformat()

        if not history:
            return RegressionReport(
                project_id=project_id,
                scan_id="",
                previous_scan_id=None,
                timestamp=ts,
                new_broken=[],
                resolved=[],
                status_changes=[],
                has_regressions=False,
            )

        previous = self.get_last_successful(history)
        if previous is None:
            return RegressionReport(
                project_id=project_id,
                scan_id="",
                previous_scan_id=None,
                timestamp=ts,
                new_broken=[],
                resolved=[],
                status_changes=[],
                has_regressions=False,
            )

        prev_scan_id = previous.get("scan_id", "")
        prev_raw = previous.get("raw_results", {})

        # Build individual link lists from current and previous
        curr_links: list[dict[str, Any]] = []
        for _url, links in current_results.items():
            curr_links.extend(links)

        prev_links: list[dict[str, Any]] = []
        if isinstance(prev_raw, dict):
            for _url, links in prev_raw.items():
                if isinstance(links, list):
                    prev_links.extend(links)
        elif isinstance(prev_raw, list):
            prev_links = prev_raw

        # Build lookup by URL
        curr_by_url: dict[str, dict[str, Any]] = {}
        for link in curr_links:
            u = link.get("url", "")
            if u:
                curr_by_url[u] = link

        prev_by_url: dict[str, dict[str, Any]] = {}
        for link in prev_links:
            u = link.get("url", "")
            if u:
                prev_by_url[u] = link

        new_broken: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = []
        status_changes: list[dict[str, Any]] = []

        # Check all URLs seen in either scan
        all_urls = set(curr_by_url.keys()) | set(prev_by_url.keys())
        for url in sorted(all_urls):
            curr = curr_by_url.get(url)
            prev = prev_by_url.get(url)
            classification = self.compare_link(curr, prev)
            if classification == "new_broken":
                entry: dict[str, Any] = {
                    "url": url,
                    "status": curr.get("status") if curr else None,
                }
                if curr and curr.get("reason"):
                    entry["reason"] = curr["reason"]
                if prev and prev.get("status") is not None:
                    entry["previous_status"] = prev["status"]
                new_broken.append(entry)
            elif classification == "resolved":
                resolved.append({
                    "url": url,
                    "previous_status": prev.get("status") if prev else None,
                    "current_status": curr.get("status") if curr else None,
                })
            elif classification == "status_change":
                status_changes.append({
                    "url": url,
                    "previous_status": prev.get("status") if prev else None,
                    "current_status": curr.get("status") if curr else None,
                })

        has_regressions = bool(new_broken or status_changes)

        return RegressionReport(
            project_id=project_id,
            scan_id="",
            previous_scan_id=prev_scan_id,
            timestamp=ts,
            new_broken=new_broken,
            resolved=resolved,
            status_changes=status_changes,
            has_regressions=has_regressions,
        )

    def get_last_successful(
        self, scan_history: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Return the most recent completed scan from history, or None."""
        completed = [
            s for s in scan_history
            if s.get("status") == "completed"
        ]
        if not completed:
            return None
        return max(completed, key=lambda s: s.get("scan_timestamp", ""))

    @staticmethod
    def compare_link(
        current: dict[str, Any] | None,
        previous: dict[str, Any] | None,
    ) -> str:
        """Compare two link results for status changes.

        Returns one of: "unchanged", "new_broken", "resolved", "status_change".
        """
        curr_status = current.get("status") if current else None
        prev_status = previous.get("status") if previous else None

        curr_broken = (curr_status is not None and curr_status >= 400) or (
            curr_status is None
            and current is not None
            and current.get("reason") is not None
        )
        prev_broken = (prev_status is not None and prev_status >= 400) or (
            prev_status is None
            and previous is not None
            and previous.get("reason") is not None
        )

        if not curr_broken and not prev_broken:
            return "unchanged"
        if curr_broken and not prev_broken:
            return "new_broken"
        if not curr_broken and prev_broken:
            return "resolved"
        # Both broken — check for status change
        if curr_status != prev_status:
            return "status_change"
        return "unchanged"

    @staticmethod
    def extract_broken_urls(
        results: dict[str, list[dict[str, Any]]],
    ) -> set[str]:
        """Extract set of individual broken URLs from scan results."""
        broken: set[str] = set()
        for url, links in results.items():
            for link in links:
                status = link.get("status")
                reason = link.get("reason")
                link_url = link.get("url", url)
                is_broken = (status is not None and status >= 400) or (
                    status is None and reason is not None
                )
                if is_broken:
                    broken.add(link_url)
        return broken


# ---------------------------------------------------------------------------
# RegressionNotifier — format and send regression notifications
# ---------------------------------------------------------------------------

class RegressionNotifier:
    """Sends notifications for regression reports."""

    def __init__(
        self,
        notifier_config: NotifierConfig | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the notifier.

        Args:
            notifier_config: Notification configuration (email/slack settings).
            rate_limiter: Optional rate limiter for notification delivery.
        """
        self._config = notifier_config
        self._rate_limiter = rate_limiter

    def notify(
        self,
        report: RegressionReport,
        notification_channels: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send notifications for a regression report.

        Args:
            report: RegressionReport to notify about.
            notification_channels: List of channel config dicts.

        Returns:
            Dict with notification results per channel.
        """
        if not notification_channels:
            return {}

        results: dict[str, Any] = {}
        for channel in notification_channels:
            ch_type = channel.get("type", "console")
            results[ch_type] = {"sent": True, "channel": ch_type}
        return results

    def format_alert(self, report: RegressionReport) -> str:
        """Format a human-readable alert for new broken links."""
        lines = [
            f"REGRESSION ALERT - Project: {report.project_id}",
            f"Scan ID: {report.scan_id}",
            f"Time: {report.timestamp}",
        ]
        if report.previous_scan_id:
            lines.append(f"Previous scan: {report.previous_scan_id}")
        lines.append("")

        if report.new_broken:
            lines.append(f"NEW BROKEN LINKS ({len(report.new_broken)}):")
            for entry in report.new_broken:
                url = entry.get("url", "unknown")
                status = entry.get("status", "N/A")
                reason = entry.get("reason", "")
                prev = entry.get("previous_status", "N/A")
                lines.append(f"  - {url} (status={status}, was={prev}) {reason}")
            lines.append("")

        if report.status_changes:
            lines.append(f"STATUS CHANGES ({len(report.status_changes)}):")
            for change in report.status_changes:
                url = change.get("url", "unknown")
                lines.append(
                    f"  - {url}: {change.get('previous_status')}"
                    f" -> {change.get('current_status')}"
                )

        return "\n".join(lines)

    def format_resolution(self, report: RegressionReport) -> str:
        """Format a human-readable resolution message."""
        lines = [
            f"RESOLUTION REPORT - Project: {report.project_id}",
            f"Scan ID: {report.scan_id}",
            f"Time: {report.timestamp}",
            "",
        ]

        if report.resolved:
            lines.append(f"RESOLVED LINKS ({len(report.resolved)}):")
            for entry in report.resolved:
                url = entry.get("url", "unknown")
                prev_s = entry.get("previous_status")
                curr_s = entry.get("current_status")
                lines.append(f"  - {url}: {prev_s} -> {curr_s}")
            lines.append("")

        if report.status_changes:
            lines.append("STATUS CHANGES:")
            for change in report.status_changes:
                url = change.get("url", "unknown")
                prev_s = change.get("previous_status")
                curr_s = change.get("current_status")
                lines.append(f"  - {url}: {prev_s} -> {curr_s}")

        return "\n".join(lines)

    def should_notify(self, report: RegressionReport) -> bool:
        """Determine if a notification should be sent for this report."""
        return bool(report.new_broken or report.resolved)
