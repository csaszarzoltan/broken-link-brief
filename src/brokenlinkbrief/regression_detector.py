"""Regression detection and notification for broken link scanning.

This module provides classes to detect regressions in link scanning results
by comparing current scan results against historical scan data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RegressionReport:
    """Report summarizing link scan regressions.

    Attributes:
        project_id: Unique identifier for the project being scanned.
        scan_id: ID of the current scan.
        previous_scan_id: ID of the previous scan used for comparison.
        timestamp: ISO format timestamp of when the report was generated.
        new_broken: List of URLs that are newly broken.
        resolved: List of URLs that were previously broken but now work.
        status_changes: List of dicts with url, previous_status, current_status.
        has_regressions: True if any new broken links or status changes detected.
    """

    project_id: str
    scan_id: str
    previous_scan_id: str | None
    timestamp: str
    new_broken: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    status_changes: list[dict[str, Any]] = field(default_factory=list)
    has_regressions: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "project_id": self.project_id,
            "scan_id": self.scan_id,
            "previous_scan_id": self.previous_scan_id,
            "timestamp": self.timestamp,
            "new_broken": self.new_broken,
            "resolved": self.resolved,
            "status_changes": self.status_changes,
            "has_regressions": self.has_regressions,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


class RegressionDetector:
    """Detects regressions in link scanning results by comparing scans."""

    def __init__(self, scan_history: Any | None = None) -> None:
        """Initialize with optional scan history store."""
        self.scan_history = scan_history

    def detect(
        self,
        project_id: str,
        current_results: dict[str, list[dict[str, Any]]],
        scan_history: Any | None = None,
    ) -> RegressionReport:
        """Compare current scan results against previous scan.

        Args:
            project_id: Project identifier.
            current_results: Dict mapping URL to list of link results.
            scan_history: Optional scan history store (uses self.scan_history
                if not provided).

        Returns:
            RegressionReport with new broken links, resolved links, and status changes.
        """
        history = scan_history or self.scan_history
        if history is None:
            return RegressionReport(
                project_id=project_id,
                scan_id="",
                previous_scan_id=None,
                timestamp=datetime.now().isoformat(),
                new_broken=list(self.extract_broken_urls(current_results)),
                resolved=[],
                status_changes=[],
                has_regressions=bool(self.extract_broken_urls(current_results)),
            )

        previous_results = self.get_last_successful(project_id, history)
        if previous_results is None:
            return RegressionReport(
                project_id=project_id,
                scan_id="",
                previous_scan_id=None,
                timestamp=datetime.now().isoformat(),
                new_broken=list(self.extract_broken_urls(current_results)),
                resolved=[],
                status_changes=[],
                has_regressions=bool(self.extract_broken_urls(current_results)),
            )

        prev_broken = self.extract_broken_urls(previous_results)
        curr_broken = self.extract_broken_urls(current_results)

        new_broken = curr_broken - prev_broken
        resolved = prev_broken - curr_broken
        common = curr_broken & prev_broken

        status_changes = []
        for url in common:
            change = self.compare_link(
                self._find_result(current_results, url),
                self._find_result(previous_results, url),
            )
            if change:
                status_changes.append(change)

        has_regressions = bool(new_broken or status_changes)

        return RegressionReport(
            project_id=project_id,
            scan_id="",
            previous_scan_id="",
            timestamp=datetime.now().isoformat(),
            new_broken=list(new_broken),
            resolved=list(resolved),
            status_changes=status_changes,
            has_regressions=has_regressions,
        )

    def get_last_successful(
        self, project_id: str, scan_history: Any
    ) -> dict[str, list[dict[str, Any]]] | None:
        """Get the last successful scan results for a project.

        Args:
            project_id: Project identifier.
            scan_history: Scan history store with get_latest_scan method.

        Returns:
            Dict of URL to link results, or None if no previous scan.
        """
        if not hasattr(scan_history, "get_latest_scan"):
            return None

        latest = scan_history.get_latest_scan(project_id)
        if latest is None or latest.raw_results_json is None:
            return None

        try:
            return json.loads(latest.raw_results_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def compare_link(
        self, current: dict[str, Any] | None, previous: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Compare two link results for status changes.

        Args:
            current: Current link result dict.
            previous: Previous link result dict.

        Returns:
            Dict with url, previous_status, current_status if changed, else None.
        """
        if not current or not previous:
            return None

        curr_status = current.get("status_code", 0)
        prev_status = previous.get("status_code", 0)

        if curr_status != prev_status:
            return {
                "url": current.get("url", previous.get("url", "")),
                "previous_status": prev_status,
                "current_status": curr_status,
            }
        return None

    def extract_broken_urls(self, results: dict[str, list[dict[str, Any]]]) -> set[str]:
        """Extract set of broken URLs from scan results.

        Args:
            results: Dict mapping URL to list of link results.

        Returns:
            Set of URLs that have at least one broken link.
        """
        broken = set()
        for url, links in results.items():
            for link in links:
                if self._is_link_broken(link):
                    broken.add(url)
                    break
        return broken

    def _find_result(
        self, results: dict[str, list[dict[str, Any]]], url: str
    ) -> dict[str, Any] | None:
        """Find first result for a URL."""
        links = results.get(url, [])
        return links[0] if links else None

    def _is_link_broken(self, result: dict[str, Any]) -> bool:
        """Check if a link result indicates a broken link.

        Args:
            result: Link result dict with status_code, is_broken, or error fields.

        Returns:
            True if the link is broken.
        """
        if result.get("is_broken"):
            return True
        status = result.get("status_code")
        if status is not None and status >= 400:
            return True
        return bool(result.get("error"))


class RegressionNotifier:
    """Sends notifications for regression reports."""

    def __init__(self, notification_config: dict[str, Any] | None = None) -> None:
        """Initialize the notifier with configuration.

        Args:
            notification_config: Configuration dict with optional keys:
                - 'channels': List of notification channels
                  ('email', 'slack', 'webhook', 'console')
                - 'notify_on_new_broken': Whether to notify on new broken links
                  (default True)
                - 'notify_on_resolved': Whether to notify on resolved links
                  (default True)
                - 'notify_on_status_change': Whether to notify on status changes
                  (default False)
                - 'min_severity': Minimum severity to notify
                  ('low', 'medium', 'high')
                - 'webhook_url': Webhook URL for webhook notifications
                - 'email_recipients': List of email addresses
        """
        self.config = notification_config or {}
        self.channels = self.config.get("channels", ["console"])

    def notify(self, report: RegressionReport) -> dict[str, Any]:
        """Send notifications for a regression report.

        Args:
            report: RegressionReport to notify about.

        Returns:
            Dict with notification results per channel.
        """
        if not self.should_notify(report):
            return {"skipped": True, "reason": "notification rules not met"}

        results = {}
        if "console" in self.channels:
            results["console"] = self._notify_console(report)
        if "email" in self.channels:
            results["email"] = self._notify_email(report)
        if "slack" in self.channels:
            results["slack"] = self._notify_slack(report)
        if "webhook" in self.channels:
            results["webhook"] = self._notify_webhook(report)

        return results

    def format_alert(self, report: RegressionReport) -> str:
        """Format a human-readable alert message for new broken links.

        Args:
            report: RegressionReport containing new broken links.

        Returns:
            Formatted alert string.
        """
        lines = [
            f"🚨 REGRESSION ALERT - Project: {report.project_id}",
            f"Time: {report.timestamp}",
            "",
        ]

        if report.new_broken:
            lines.append(f"🔴 NEW BROKEN LINKS ({len(report.new_broken)}):")
            for url in report.new_broken:
                lines.append(f"  - {url}")
            lines.append("")

        if report.status_changes:
            lines.append(f"⚠️  STATUS CHANGES ({len(report.status_changes)}):")
            for change in report.status_changes:
                lines.append(
                    f"  - {change['url']}: {change['previous_status']} \u2192 "
                    f"{change['current_status']}"
                )
            lines.append("")

        if report.resolved:
            lines.append(f"🟢 RESOLVED LINKS ({len(report.resolved)}):")
            for url in report.resolved:
                lines.append(f"  - {url}")

        return "\n".join(lines)

    def format_resolution(self, report: RegressionReport) -> str:
        """Format a human-readable resolution message.

        Args:
            report: RegressionReport containing resolved links.

        Returns:
            Formatted resolution string.
        """
        if not report.resolved and not report.status_changes:
            return "No resolutions to report."

        lines = [
            f"✅ RESOLUTION REPORT - Project: {report.project_id}",
            f"Time: {report.timestamp}",
            "",
        ]

        if report.resolved:
            lines.append(f"🟢 RESOLVED LINKS ({len(report.resolved)}):")
            for url in report.resolved:
                lines.append(f"  - {url}")
            lines.append("")

        if report.status_changes:
            lines.append("🔄 STATUS CHANGES:")
            for change in report.status_changes:
                lines.append(
                    f"  - {change['url']}: {change['previous_status']} \u2192 "
                    f"{change['current_status']}"
                )

        return "\n".join(lines)

    def should_notify(self, report: RegressionReport) -> bool:
        """Determine if a notification should be sent for this report.

        Args:
            report: RegressionReport to evaluate.

        Returns:
            True if notification should be sent.
        """
        if not report.has_regressions:
            return False

        notify_new = self.config.get("notify_on_new_broken", True)
        notify_resolved = self.config.get("notify_on_resolved", True)
        notify_status = self.config.get("notify_on_status_change", False)

        if report.new_broken and notify_new:
            return True
        if report.resolved and notify_resolved:
            return True
        return bool(report.status_changes and notify_status)

    def _notify_console(self, report: RegressionReport) -> dict[str, Any]:
        """Print notification to console."""
        if report.new_broken or report.status_changes:
            print(self.format_alert(report))
        elif report.resolved:
            print(self.format_resolution(report))
        return {"sent": True, "channel": "console"}

    def _notify_email(self, report: RegressionReport) -> dict[str, Any]:
        """Send email notification (stub implementation)."""
        recipients = self.config.get("email_recipients", [])
        if not recipients:
            return {"sent": False, "error": "No email recipients configured"}
        # In production, integrate with SMTP or email service
        return {"sent": True, "channel": "email", "recipients": recipients}

    def _notify_slack(self, report: RegressionReport) -> dict[str, Any]:
        """Send Slack notification (stub implementation)."""
        webhook_url = self.config.get("slack_webhook_url")
        if not webhook_url:
            return {"sent": False, "error": "No Slack webhook configured"}
        # In production, POST to Slack webhook
        return {"sent": True, "channel": "slack"}

    def _notify_webhook(self, report: RegressionReport) -> dict[str, Any]:
        """Send webhook notification (stub implementation)."""
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            return {"sent": False, "error": "No webhook URL configured"}
        # In production, POST report.to_dict() to webhook
        return {"sent": True, "channel": "webhook"}
