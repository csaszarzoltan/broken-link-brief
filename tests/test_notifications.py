"""Pre-development interface and behavioral tests for Email/Slack notifications.

Interface tests verify that the required classes, functions, and constants
exist with correct signatures.  These MUST pass immediately.

Behavioral tests exercise the actual logic.  During the stub phase they
categorically assert `NotImplementedError` (the stub contract).  After the
developer implements the module, the ``pytest.raises`` wrapper is removed
and the test asserts the real return value / side-effect.

┌─────────────────────────────────────────────────────────────────────────┐
│                     Important safety rule                              │
│  Do NOT modify or delete lines in this file.  Only the test checker   │
│  (or a future refactor pass) may change tests.  The pre-tester has    │
│  sized this suite so that every behavioral assertion starts with       │
│  ``pytest.raises(NotImplementedError)``.  The implementer removes     │
│  that context manager and writes the real assertion.                   │
└─────────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import inspect
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from brokenlinkbrief.notifications import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    EmailNotifier,
    NotificationTemplates,
    NotifierConfig,
    RateLimiter,
    SlackNotifier,
    notify_all,
)
from brokenlinkbrief.package import LinkResult

# ═══════════════════════════════════════════════════════════════════════════
# 1. RateLimiter
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimiterInterface:
    """RateLimiter: structural / signature checks — must pass immediately."""

    def test_class_exists(self) -> None:
        assert isinstance(RateLimiter, type)

    def test_init_signature(self) -> None:
        sig = inspect.signature(RateLimiter.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "capacity" in params
        assert "fill_rate" in params

    def test_allow_signature(self) -> None:
        sig = inspect.signature(RateLimiter.allow)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "key" in params

    def test_reset_signature(self) -> None:
        sig = inspect.signature(RateLimiter.reset)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "key" in params

    def test_allow_returns_bool_annotation(self) -> None:
        """allow must be annotated as returning bool."""
        import typing

        hints = typing.get_type_hints(RateLimiter.allow)
        assert hints.get("return") is bool


class TestRateLimiterBehavior:
    """RateLimiter: behavioral tests for token-bucket algorithm."""

    def test_constructor_and_allow(self) -> None:
        rl = RateLimiter(capacity=10, fill_rate=1.0)
        assert isinstance(rl, RateLimiter)
        # Initial bucket should be full
        assert rl.allow("test") is True

    def test_depletes_and_respects_capacity(self) -> None:
        """With fill_rate=0, tokens deplete exactly to 0 then deny."""
        rl = RateLimiter(capacity=3, fill_rate=0.0)
        assert rl.allow("key") is True
        assert rl.allow("key") is True
        assert rl.allow("key") is True
        assert rl.allow("key") is False  # Empty - denied

    def test_allow_returns_false_when_empty(self) -> None:
        rl = RateLimiter(capacity=1, fill_rate=0.0)
        assert rl.allow("key") is True
        assert rl.allow("key") is False

    def test_reset_restores_tokens(self) -> None:
        rl = RateLimiter(capacity=1, fill_rate=0.0)
        assert rl.allow("key") is True
        assert rl.allow("key") is False
        rl.reset("key")
        assert rl.allow("key") is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. NotifierConfig
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifierConfigInterface:
    """NotifierConfig: shape checks — must pass immediately."""

    def test_is_dataclass(self) -> None:
        from dataclasses import is_dataclass

        assert is_dataclass(NotifierConfig)

    def test_has_smtp_fields(self) -> None:
        """SMTP fields exist."""
        from dataclasses import fields

        names = {f.name for f in fields(NotifierConfig)}
        for expected in ("smtp_host", "smtp_port", "smtp_user",
                         "smtp_password", "smtp_from"):
            assert expected in names, f"missing field: {expected}"

    def test_has_slack_field(self) -> None:
        from dataclasses import fields

        names = {f.name for f in fields(NotifierConfig)}
        assert "slack_webhook_url" in names

    def test_has_notify_fields(self) -> None:
        from dataclasses import fields

        names = {f.name for f in fields(NotifierConfig)}
        for expected in ("notify_on", "rate_limit", "rate_interval",
                         "email_enabled", "slack_enabled"):
            assert expected in names, f"missing field: {expected}"

    def test_from_env_classmethod_exists(self) -> None:
        assert callable(NotifierConfig.from_env)

    def test_from_env_returns_config_annotation(self) -> None:
        hints = inspect.signature(NotifierConfig.from_env).return_annotation
        assert hints in (NotifierConfig, NotifierConfig | None,
                         "NotifierConfig")


class TestNotifierConfigBehavior:
    """NotifierConfig: behavioral tests for from_env()."""

    def test_from_env_with_defaults(self) -> None:
        """from_env() with no env vars returns a default config."""
        config = NotifierConfig.from_env()
        assert isinstance(config, NotifierConfig)
        assert config.email_enabled is False
        assert config.slack_enabled is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. EmailNotifier
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailNotifierInterface:
    """EmailNotifier: existence / signature checks."""

    def test_class_exists(self) -> None:
        assert isinstance(EmailNotifier, type)

    def test_init_accepts_config(self) -> None:
        sig = inspect.signature(EmailNotifier.__init__)
        assert "config" in sig.parameters

    def test_send_signature(self) -> None:
        sig = inspect.signature(EmailNotifier.send)
        params = list(sig.parameters.keys())
        for expected in ("self", "to", "subject", "body"):
            assert expected in params, f"missing param: {expected}"

    def test_send_returns_bool_annotation(self) -> None:
        import typing

        hints = typing.get_type_hints(EmailNotifier.send)
        assert hints.get("return") is bool


class TestEmailNotifierBehavior:
    """EmailNotifier: behavioral tests."""

    def test_constructor(self) -> None:
        config = NotifierConfig()
        notifier = EmailNotifier(config)
        assert isinstance(notifier, EmailNotifier)

    def test_send_without_smtp_returns_false(self) -> None:
        config = NotifierConfig()
        notifier = EmailNotifier(config)
        result = notifier.send("test@example.com", "sub", "body")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. SlackNotifier
# ═══════════════════════════════════════════════════════════════════════════


class TestSlackNotifierInterface:
    """SlackNotifier: existence / signature checks."""

    def test_class_exists(self) -> None:
        assert isinstance(SlackNotifier, type)

    def test_init_accepts_webhook_url(self) -> None:
        sig = inspect.signature(SlackNotifier.__init__)
        assert "webhook_url" in sig.parameters

    def test_send_signature(self) -> None:
        sig = inspect.signature(SlackNotifier.send)
        assert "self" in sig.parameters
        assert "message" in sig.parameters

    def test_send_returns_bool_annotation(self) -> None:
        import typing

        hints = typing.get_type_hints(SlackNotifier.send)
        assert hints.get("return") is bool


class TestSlackNotifierBehavior:
    """SlackNotifier: behavioral tests."""

    def test_constructor(self) -> None:
        notifier = SlackNotifier("https://hooks.example.com")
        assert isinstance(notifier, SlackNotifier)

    def test_send_without_valid_webhook_returns_false(self) -> None:
        notifier = SlackNotifier("https://hooks.example.com")
        result = notifier.send("hello")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. NotificationTemplates
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationTemplatesInterface:
    """NotificationTemplates: shape / static-method checks."""

    def test_class_exists(self) -> None:
        assert isinstance(NotificationTemplates, type)

    def test_severity_label_is_staticmethod(self) -> None:
        """severity_label is a static method (no 'self' in signature)."""
        assert callable(NotificationTemplates.severity_label)
        # Static methods on the class don't bind 'self'
        import typing

        hints = typing.get_type_hints(NotificationTemplates.severity_label)
        assert hints.get("return") is str

    def test_severity_label_signature(self) -> None:
        sig = inspect.signature(NotificationTemplates.severity_label)
        assert "status" in sig.parameters
        # Must be a static method — no 'self' param
        assert "self" not in sig.parameters

    def test_render_summary_is_staticmethod(self) -> None:
        """render_summary is a static method with correct annotation."""
        assert callable(NotificationTemplates.render_summary)
        import typing

        hints = typing.get_type_hints(NotificationTemplates.render_summary)
        assert hints.get("return") is str

    def test_render_summary_signature(self) -> None:
        sig = inspect.signature(NotificationTemplates.render_summary)
        assert "results" in sig.parameters
        assert "scanned_url" in sig.parameters
        assert "self" not in sig.parameters

    def test_render_empty_is_staticmethod(self) -> None:
        """render_empty is a static method with str annotation."""
        assert callable(NotificationTemplates.render_empty)
        import typing

        hints = typing.get_type_hints(NotificationTemplates.render_empty)
        assert hints.get("return") is str


class TestNotificationTemplatesBehavior:
    """NotificationTemplates: stub contract — severity label mapping.

    These tests assert the expected behaviour of the Completed implementation.
    During the stub phase the static methods return a dummy string, so the
    assertions document what the real implementation MUST produce.
    """

    def test_severity_label_critical_for_5xx(self) -> None:
        """5xx status codes map to 'critical'."""
        label = NotificationTemplates.severity_label(500)
        assert label == SEVERITY_CRITICAL

    def test_severity_label_warning_for_4xx(self) -> None:
        """4xx status codes map to 'warning'."""
        label = NotificationTemplates.severity_label(404)
        assert label == SEVERITY_WARNING

    def test_severity_label_info_for_3xx(self) -> None:
        """3xx redirects map to 'info'."""
        label = NotificationTemplates.severity_label(301)
        assert label == SEVERITY_INFO

    def test_severity_label_info_for_2xx(self) -> None:
        """2xx success maps to 'info'."""
        label = NotificationTemplates.severity_label(200)
        assert label == SEVERITY_INFO

    def test_render_summary_includes_scanned_url(self) -> None:
        results = [
            LinkResult(url="http://broken.com", status=404, reason="Not Found"),
        ]
        summary = NotificationTemplates.render_summary(results, "http://target.com")
        assert isinstance(summary, str)
        assert "http://target.com" in summary

    def test_render_summary_counts_broken_links(self) -> None:
        results = [
            LinkResult(url="http://ok.com", status=200, reason="OK"),
            LinkResult(url="http://broken.com", status=404, reason="Not Found"),
            LinkResult(url="http://error.com", status=500, reason="Server Error"),
        ]
        summary = NotificationTemplates.render_summary(results, "http://target.com")
        assert isinstance(summary, str)
        assert "2" in summary or "broken" in summary.lower()

    def test_render_empty_returns_non_empty_string(self) -> None:
        msg = NotificationTemplates.render_empty()
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_render_summary_empty_results(self) -> None:
        """Empty results render without error."""
        summary = NotificationTemplates.render_summary([], "http://target.com")
        assert isinstance(summary, str)


# ═══════════════════════════════════════════════════════════════════════════
# 6. notify_all — coordinator
# ═══════════════════════════════════════════════════════════════════════════


class TestNotifyAllInterface:
    """notify_all: signature checks."""

    def test_function_exists(self) -> None:
        assert callable(notify_all)

    def test_signature(self) -> None:
        sig = inspect.signature(notify_all)
        params = list(sig.parameters.keys())
        for expected in ("config", "results", "scanned_url"):
            assert expected in params, f"missing param: {expected}"

    def test_returns_dict_annotation(self) -> None:
        import typing

        hints = typing.get_type_hints(notify_all)
        ret = hints.get("return")
        assert ret is not None


class TestNotifyAllBehavior:
    """notify_all: behavioral tests."""

    def test_basic_call_with_empty_config(self) -> None:
        config = NotifierConfig()
        result = notify_all(config, [], "http://target.com")
        assert isinstance(result, dict)

    def test_with_rate_limiter(self) -> None:
        config = NotifierConfig()
        limiter = RateLimiter(capacity=10, fill_rate=1.0)
        result = notify_all(config, [], "http://target.com", rate_limiter=limiter)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Severity constants
# ═══════════════════════════════════════════════════════════════════════════


class TestSeverityConstants:
    """Seventy label constants are correct strings."""

    def test_severity_critical(self) -> None:
        assert SEVERITY_CRITICAL == "critical"

    def test_severity_warning(self) -> None:
        assert SEVERITY_WARNING == "warning"

    def test_severity_info(self) -> None:
        assert SEVERITY_INFO == "info"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Integration — app.py calls notify_all after scan
# ═══════════════════════════════════════════════════════════════════════════
#
# These tests verify that the /scan and /scan-batch HTTP endpoints invoke
# ``notify_all`` after results are collected.  They patch ``notify_all``
# at the app-module level and assert it was called.
#
# During the stub phase these are EXPECTED TO FAIL because ``notify_all``
# is not yet imported or called from ``app.py``.
# ───────────────────────────────────────────────────────────────────────────


def _start_server_for_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, int]:
    """Start an ephemeral server with a fixed scan token.

    Returns (server, port).
    """
    # Clean history state from previous tests
    import shutil
    import socket
    import threading
    from http.server import HTTPServer

    from brokenlinkbrief.app import _Handler, _webhook_registry
    history_dir = os.path.join(os.getcwd(), ".history")
    if os.path.isdir(history_dir):
        shutil.rmtree(history_dir)

    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "test-token")
    _webhook_registry.clear()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


class TestIntegrationScanEndpoint:
    """/scan endpoint must call notify_all after scan results."""

    def test_scan_calls_notify_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After /scan with broken links, notify_all must be called."""
        from brokenlinkbrief.package import LinkResult

        broken_results = [
            LinkResult(url="http://broken.com/1", status=404, reason="Not Found"),
            LinkResult(url="http://ok.com/1", status=200, reason="OK"),
        ]

        notify_mock = MagicMock(return_value={"email": {}, "slack": {}})

        server, port = _start_server_for_integration(monkeypatch)
        try:
            with (
                patch("brokenlinkbrief.app.scan_page",
                      return_value=broken_results),
                patch("brokenlinkbrief.app.notify_all", notify_mock),
            ):
                import http.client

                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(
                    "GET",
                    "/scan?url=http://example.com",
                    headers={
                        "Host": "127.0.0.1",
                        "Authorization": "Bearer test-token",
                    },
                )
                resp = conn.getresponse()
                resp.read()
                conn.close()

                # notify_all should have been called at least once
                assert notify_mock.called, (
                    "notify_all was not called after /scan"
                )
        finally:
            server.shutdown()

    def test_scan_does_not_fire_notify_all_when_no_broken_links(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If the scan finds no broken links, notify_all should not fire."""
        notify_mock = MagicMock()

        server, port = _start_server_for_integration(monkeypatch)
        try:
            # Patch scan_page to return only OK results
            from brokenlinkbrief.package import LinkResult

            ok_results = [
                LinkResult(
                    url="http://example.com",
                    status=200,
                    reason="OK",
                ),
            ]

            with (
                patch("brokenlinkbrief.app.scan_page",
                      return_value=ok_results),
                patch("brokenlinkbrief.app.notify_all", notify_mock),
            ):
                import http.client

                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(
                    "GET",
                    "/scan?url=http://example.com",
                    headers={
                        "Host": "127.0.0.1",
                        "Authorization": "Bearer test-token",
                    },
                )
                resp = conn.getresponse()
                resp.read()
                conn.close()

                assert not notify_mock.called, (
                    "notify_all should not be called when no broken links"
                )
        finally:
            server.shutdown()


class TestIntegrationScanBatchEndpoint:
    """/scan-batch endpoint must call notify_all after scan results."""

    def test_scan_batch_calls_notify_all(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After /scan-batch with broken links, notify_all must be called."""
        import json

        from brokenlinkbrief.package import LinkResult

        mock_batch_results = {
            "http://example.com": [
                LinkResult(
                    url="http://example.com/page1",
                    status=404,
                    reason="Not Found",
                ),
                LinkResult(
                    url="http://example.com/page2",
                    status=200,
                    reason="OK",
                ),
            ],
        }

        notify_mock = MagicMock(return_value={"email": {}, "slack": {}})

        server, port = _start_server_for_integration(monkeypatch)
        try:
            with (
                patch(
                    "brokenlinkbrief.app.scan_batch",
                    return_value=mock_batch_results,
                ),
                patch("brokenlinkbrief.app.notify_all", notify_mock),
            ):
                import http.client

                conn = http.client.HTTPConnection(
                    "127.0.0.1", port, timeout=5
                )
                body = json.dumps({
                    "urls": ["http://example.com"],
                }).encode("utf-8")
                conn.request(
                    "POST",
                    "/scan-batch?token=test-token",
                    body=body,
                    headers={
                        "Host": "127.0.0.1",
                        "Content-Type": "application/json",
                    },
                )
                resp = conn.getresponse()
                resp.read()
                conn.close()

                assert notify_mock.called, (
                    "notify_all was not called after /scan-batch"
                )
        finally:
            server.shutdown()
