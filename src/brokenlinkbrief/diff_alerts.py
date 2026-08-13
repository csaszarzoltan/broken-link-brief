"""Diff alert notification system for BrokenLinkBrief.

Provides templates and a coordinator for sending diff-specific
alerts via email/Slack when link state changes are detected.
"""

from __future__ import annotations

from typing import Any

from brokenlinkbrief.diff_detector import DiffReport
from brokenlinkbrief.notifications import (
    EmailNotifier,
    NotifierConfig,
    RateLimiter,
    SlackNotifier,
)


def _make_delivery_outcome(
    channel: str,
    sent: bool,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a standard delivery outcome dict."""
    outcome: dict[str, Any] = {"sent": sent}
    if error:
        outcome["error"] = error
    return outcome


class DiffNotificationTemplates:
    """Template renderers for diff-specific notifications."""

    @staticmethod
    def render_diff_alert(report: DiffReport) -> str:
        """Render a human-readable diff alert for new broken links."""
        lines = [
            "Link Diff Alert",
            f"Target: {report.target_url}",
            f"Project: {report.project_id}",
            f"Time: {report.timestamp}",
            "",
        ]

        if report.new_broken:
            lines.append(f"NEW BROKEN LINKS ({len(report.new_broken)}):")
            for entry in report.new_broken:
                url = entry.get("url", "unknown")
                status = entry.get("status", "N/A")
                reason = entry.get("reason", "")
                lines.append(f"  - {url} (status={status}) {reason}")

        if report.status_changes:
            lines.append(f"STATUS CHANGES ({len(report.status_changes)}):")
            for change in report.status_changes:
                url = change.get("url", "unknown")
                prev_s = change.get("previous_status", "N/A")
                curr_s = change.get("current_status", "N/A")
                lines.append(f"  - {url}: {prev_s} -> {curr_s}")

        return "\n".join(lines)

    @staticmethod
    def render_diff_resolution(report: DiffReport) -> str:
        """Render a human-readable resolution notification."""
        lines = [
            "Link Resolution Report",
            f"Target: {report.target_url}",
            f"Project: {report.project_id}",
            f"Time: {report.timestamp}",
            "",
        ]

        if report.resolved:
            lines.append(f"RESOLVED LINKS ({len(report.resolved)}):")
            for entry in report.resolved:
                url = entry.get("url", "unknown")
                prev_s = entry.get("previous_status", "N/A")
                curr_s = entry.get("current_status", "N/A")
                lines.append(f"  - {url}: {prev_s} -> {curr_s}")

        return "\n".join(lines)


def diff_notify_all(
    config: NotifierConfig,
    report: DiffReport,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Send diff notifications based on report changes.

    Checks report.has_changes before sending, rate-limits per target_url,
    and dispatches through existing email/Slack channels.

    Args:
        config: Notification configuration.
        report: DiffReport from DiffDetector.compare().
        rate_limiter: Optional rate limiter for delivery throttling.

    Returns:
        Delivery outcome dict like notify_all().
    """
    outcome: dict[str, Any] = {}

    # Short-circuit: no changes → no notifications
    if not report.has_changes:
        outcome["email"] = _make_delivery_outcome("email", False, "no changes")
        outcome["slack"] = _make_delivery_outcome("slack", False, "no changes")
        return outcome

    # Rate-limit check
    if rate_limiter is not None and not rate_limiter.allow(report.target_url):
        outcome["email"] = _make_delivery_outcome("email", False, "rate-limited")
        outcome["slack"] = _make_delivery_outcome("slack", False, "rate-limited")
        return outcome

    # Render notification texts
    alert_text = DiffNotificationTemplates.render_diff_alert(report)
    resolution_text = DiffNotificationTemplates.render_diff_resolution(report)

    # Email notification
    if config.email_enabled:
        try:
            notifier = EmailNotifier(config)
            body_parts = [alert_text]
            if report.resolved:
                body_parts.append("")
                body_parts.append(resolution_text)
            body = "\n".join(body_parts)
            email_sent = notifier.send(
                to=config.smtp_from,
                subject=f"Link Diff Alert: {report.target_url}",
                body=body,
            )
            outcome["email"] = _make_delivery_outcome(
                "email",
                email_sent,
                None if email_sent else "send returned False",
            )
        except Exception as exc:
            outcome["email"] = _make_delivery_outcome("email", False, str(exc))
    else:
        outcome["email"] = _make_delivery_outcome(
            "email", False, "email not configured"
        )

    # Slack notification
    if config.slack_enabled:
        try:
            slack_notifier = SlackNotifier(config.slack_webhook_url)
            slack_sent = slack_notifier.send(message=alert_text)
            outcome["slack"] = _make_delivery_outcome(
                "slack",
                slack_sent,
                None if slack_sent else "send returned False",
            )
        except Exception as exc:
            outcome["slack"] = _make_delivery_outcome("slack", False, str(exc))
    else:
        outcome["slack"] = _make_delivery_outcome(
            "slack", False, "slack not configured"
        )

    return outcome
