"""Email/Slack notification system for BrokenLinkBrief.

Provides rate-limited, configurable notification delivery via
SMTP email and Slack Incoming Webhooks.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "RateLimiter",
    "NotifierConfig",
    "EmailNotifier",
    "SlackNotifier",
    "NotificationTemplates",
    "notify_all",
    "SEVERITY_CRITICAL",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
]

# ---------------------------------------------------------------------------
# Severity labels
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "critical"  # 5xx
SEVERITY_WARNING = "warning"  # 4xx
SEVERITY_INFO = "info"  # redirect (3xx) / success (2xx)


# ---------------------------------------------------------------------------
# RateLimiter — token-bucket rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter with per-key buckets.

    Capacity and fill rate are set at construction time.
    """

    def __init__(self, capacity: int, fill_rate: float) -> None:
        """Initialise a token-bucket rate limiter.

        Args:
            capacity: Maximum number of tokens per bucket (burst size).
            fill_rate:  Tokens added per second.
        """
        self._capacity = capacity
        self._fill_rate = fill_rate
        self._buckets: dict[str, dict[str, float]] = {}

    def allow(self, key: str) -> bool:
        """Return True if *key* may proceed, consuming one token.

        When the bucket is empty the call is denied.
        """
        now = time.monotonic()
        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": float(self._capacity),
                "last_refill": now,
            }

        bucket = self._buckets[key]
        # Refill tokens based on elapsed time
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(
            float(self._capacity),
            bucket["tokens"] + elapsed * self._fill_rate,
        )
        bucket["last_refill"] = now

        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True
        return False

    def reset(self, key: str) -> None:
        """Reset (empty / re-fill) the bucket for *key*."""
        self._buckets.pop(key, None)


# ---------------------------------------------------------------------------
# NotifierConfig — environment-variable-based configuration
# ---------------------------------------------------------------------------


@dataclass
class NotifierConfig:
    """Notification configuration loaded from environment variables.

    SMTP
        BROKENLINKBRIEF_SMTP_HOST
        BROKENLINKBRIEF_SMTP_PORT      (default ``587``)
        BROKENLINKBRIEF_SMTP_USER
        BROKENLINKBRIEF_SMTP_PASSWORD
        BROKENLINKBRIEF_SMTP_FROM

    Slack
        BROKENLINKBRIEF_SLACK_WEBHOOK_URL

    Notification behaviour
        BROKENLINKBRIEF_NOTIFY_ON      (default ``critical,warning,info``)
        BROKENLINKBRIEF_NOTIFY_RATE_LIMIT      (default ``10``)
        BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL   (default ``60``)
    """

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    slack_webhook_url: str = ""

    notify_on: list[str] = field(
        default_factory=lambda: ["critical", "warning", "info"]
    )
    rate_limit: int = 10
    rate_interval: float = 60.0

    email_enabled: bool = False
    slack_enabled: bool = False

    @classmethod
    def from_env(cls) -> NotifierConfig:
        """Build a config from the process environment.

        Raises ``RuntimeError`` when a required variable is missing
        and the corresponding channel is enabled.
        """
        config = cls(
            smtp_host=os.environ.get("BROKENLINKBRIEF_SMTP_HOST", ""),
            smtp_port=int(os.environ.get("BROKENLINKBRIEF_SMTP_PORT", "587")),
            smtp_user=os.environ.get("BROKENLINKBRIEF_SMTP_USER", ""),
            smtp_password=os.environ.get("BROKENLINKBRIEF_SMTP_PASSWORD", ""),
            smtp_from=os.environ.get("BROKENLINKBRIEF_SMTP_FROM", ""),
            slack_webhook_url=os.environ.get(
                "BROKENLINKBRIEF_SLACK_WEBHOOK_URL", ""
            ),
        )

        # Parse notify_on from comma-separated env var (default to all)
        notify_on_raw = os.environ.get("BROKENLINKBRIEF_NOTIFY_ON", "")
        if notify_on_raw:
            config.notify_on = [s.strip() for s in notify_on_raw.split(",")]

        # Rate limit / interval
        rate_limit_raw = os.environ.get("BROKENLINKBRIEF_NOTIFY_RATE_LIMIT")
        if rate_limit_raw:
            config.rate_limit = int(rate_limit_raw)

        rate_interval_raw = os.environ.get(
            "BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL"
        )
        if rate_interval_raw:
            config.rate_interval = float(rate_interval_raw)

        # Enable flags based on configuration presence
        config.email_enabled = bool(config.smtp_host and config.smtp_from)
        config.slack_enabled = bool(config.slack_webhook_url)

        # Validate required fields for enabled channels
        if config.email_enabled and not config.smtp_user:
            raise RuntimeError(
                "SMTP user is required for email notifications "
                "(BROKENLINKBRIEF_SMTP_USER)"
            )
        if config.email_enabled and not config.smtp_password:
            raise RuntimeError(
                "SMTP password is required for email notifications "
                "(BROKENLINKBRIEF_SMTP_PASSWORD)"
            )

        return config


# ---------------------------------------------------------------------------
# EmailNotifier
# ---------------------------------------------------------------------------


class EmailNotifier:
    """SMTP-based email delivery using stdlib ``smtplib`` + ``email.mime``."""

    def __init__(self, config: NotifierConfig) -> None:
        self._config = config

    def send(self, to: str | list[str], subject: str, body: str) -> bool:
        """Deliver a plain-text email.

        Args:
            to:       Single recipient address or list of addresses.
            subject:  Email subject line.
            body:     Plain-text body.

        Returns:
            True on success, False on connection / auth failure.
        """
        import smtplib
        from email.mime.text import MIMEText

        recipients = [to] if isinstance(to, str) else to

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._config.smtp_from
        msg["To"] = ", ".join(recipients)

        try:
            if self._config.smtp_port == 465:
                # SMTP over SSL
                with smtplib.SMTP_SSL(
                    self._config.smtp_host, self._config.smtp_port, timeout=10
                ) as server:
                    if self._config.smtp_user:
                        server.login(
                            self._config.smtp_user, self._config.smtp_password
                        )
                    server.sendmail(
                        self._config.smtp_from, recipients, msg.as_string()
                    )
            else:
                # STARTTLS (default 587) or plain SMTP (25)
                with smtplib.SMTP(
                    self._config.smtp_host, self._config.smtp_port, timeout=10
                ) as server:
                    if self._config.smtp_port == 587:
                        server.starttls()
                    if self._config.smtp_user:
                        server.login(
                            self._config.smtp_user, self._config.smtp_password
                        )
                    server.sendmail(
                        self._config.smtp_from, recipients, msg.as_string()
                    )
            return True
        except (smtplib.SMTPException, ConnectionError, TimeoutError, OSError):
            return False


# ---------------------------------------------------------------------------
# SlackNotifier
# ---------------------------------------------------------------------------


class SlackNotifier:
    """Slack Incoming Webhook integration.

    Reuses ``deliver_webhook`` from ``brokenlinkbrief.webhook``.
    """

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send(self, message: str) -> bool:
        """Deliver a Slack message via the configured webhook URL.

        The message payload is wrapped in a Slack-compatible JSON
        structure with ``{"text": ...}``.

        Returns:
            True on HTTP 2xx, False otherwise.
        """
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        payload = json.dumps({"text": message}).encode("utf-8")
        req = Request(
            self._webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, ConnectionError, TimeoutError):
            return False


# ---------------------------------------------------------------------------
# NotificationTemplates
# ---------------------------------------------------------------------------


class NotificationTemplates:
    """Template renderers for scan-result notifications."""

    @staticmethod
    def severity_label(status: int) -> str:
        """Map an HTTP status to a severity label.

        - 5xx → ``critical``
        - 4xx → ``warning``
        - 3xx → ``info``
        - 2xx → ``info``
        """
        if status >= 500:
            return SEVERITY_CRITICAL
        if status >= 400:
            return SEVERITY_WARNING
        return SEVERITY_INFO

    @staticmethod
    def render_summary(
        results: list[Any],
        scanned_url: str,
    ) -> str:
        """Render a human-readable scan summary.

        Includes URL, total links, broken count grouped by severity,
        and timestamp.
        """
        total = len(results)
        critical = sum(
            1
            for r in results
            if r.status is not None and r.status >= 500
        )
        warning = sum(
            1
            for r in results
            if r.status is not None and 400 <= r.status < 500
        )
        info = sum(
            1
            for r in results
            if r.status is not None and r.status < 400
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"Scan Report for: {scanned_url}",
            f"Timestamp: {timestamp}",
            f"Total links checked: {total}",
            "",
            "Broken links by severity:",
        ]
        if critical:
            lines.append(f"  🔴 Critical (5xx): {critical}")
        if warning:
            lines.append(f"  🟡 Warning (4xx): {warning}")
        if info:
            lines.append(f"  🟢 Info/OK (2xx/3xx): {info}")

        if critical or warning:
            lines.append("")
            lines.append("Details of broken links:")
            for r in results:
                label = NotificationTemplates.severity_label(
                    r.status if r.status is not None else 999
                )
                if label in (SEVERITY_CRITICAL, SEVERITY_WARNING):
                    status_str = str(r.status) if r.status is not None else "N/A"
                    reason_str = r.reason or ""
                    lines.append(f"  - [{label}] {r.url} ({status_str}: {reason_str})")

        return "\n".join(lines)

    @staticmethod
    def render_empty() -> str:
        """Render a short ``no issues found`` message."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"No broken links found during scan.\n"
            f"Timestamp: {timestamp}"
        )


# ---------------------------------------------------------------------------
# Internal helpers for notify_all
# ---------------------------------------------------------------------------


def _should_notify(config: NotifierConfig, results: list[Any]) -> bool:
    """Return True if results contain links at or above the severity threshold.

    When ``notify_on`` is empty, always notify.
    """
    if not config.notify_on:
        return True

    for r in results:
        status = r.status if r.status is not None else 999
        label = NotificationTemplates.severity_label(status)
        if label in config.notify_on:
            return True
    return False


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


# ---------------------------------------------------------------------------
# notify_all — coordinator
# ---------------------------------------------------------------------------


def notify_all(
    config: NotifierConfig,
    results: list[Any],
    scanned_url: str,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Fire notifications (email and/or Slack) based on *config*.

    Args:
        config:       Notification configuration.
        results:      Scan results (list of LinkResult).
        scanned_url:  The URL that was scanned.
        rate_limiter: Optional rate limiter; when provided each channel
                      is checked before sending.

    Returns:
        A dict with outcome summary::

            {
                "email": {"sent": True, "error": None}
                | {"sent": False, "error": "..."},
                "slack": {"sent": True, "error": None}
                | {"sent": False, "error": "..."},
            }
    """
    outcome: dict[str, Any] = {}

    # Check if we should notify based on severity
    if not _should_notify(config, results):
        outcome["email"] = _make_delivery_outcome(
            "email", False, "no links at configured severity"
        )
        outcome["slack"] = _make_delivery_outcome(
            "slack", False, "no links at configured severity"
        )
        return outcome

    # Rate-limit check
    if rate_limiter is not None and not rate_limiter.allow(scanned_url):
        outcome["email"] = _make_delivery_outcome(
            "email", False, "rate-limited"
        )
        outcome["slack"] = _make_delivery_outcome(
            "slack", False, "rate-limited"
        )
        return outcome

    # Build the summary text (reused by both channels)
    if results:
        summary_text = NotificationTemplates.render_summary(
            results, scanned_url
        )
    else:
        summary_text = NotificationTemplates.render_empty()

    # Email notification
    if config.email_enabled:
        try:
            notifier = EmailNotifier(config)
            email_sent = notifier.send(
                to=config.smtp_from,
                subject=f"BrokenLinkBrief Report: {scanned_url}",
                body=summary_text,
            )
            outcome["email"] = _make_delivery_outcome(
                "email", email_sent,
                None if email_sent else "send returned False",
            )
        except Exception as exc:
            outcome["email"] = _make_delivery_outcome(
                "email", False, str(exc)
            )
    else:
        outcome["email"] = _make_delivery_outcome(
            "email", False, "email not configured"
        )

    # Slack notification
    if config.slack_enabled:
        try:
            slack_data = {
                "text": summary_text,
            }
            # Use deliver_webhook from webhook module for reusability
            from brokenlinkbrief.webhook import deliver_webhook

            payload_bytes = json.dumps(slack_data).encode("utf-8")
            status_code = deliver_webhook(
                config.slack_webhook_url, payload_bytes, timeout=10.0
            )
            slack_sent = 200 <= status_code < 300
            outcome["slack"] = _make_delivery_outcome(
                "slack", slack_sent,
                None if slack_sent else f"HTTP {status_code}",
            )
        except Exception as exc:
            outcome["slack"] = _make_delivery_outcome(
                "slack", False, str(exc)
            )
    else:
        outcome["slack"] = _make_delivery_outcome(
            "slack", False, "slack not configured"
        )

    return outcome
