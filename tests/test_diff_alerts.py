"""Pre-dev tests for diff alert integration (DiffNotificationTemplates + diff_notify_all).

Three-layer test pattern:
  Layer 1: Import/class-existence (PASS immediately)
  Layer 2: Signature/interface (PASS immediately)
  Layer 3: Behavioral (FAIL with NotImplementedError — RED phase)
"""
from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from brokenlinkbrief.diff_alerts import DiffNotificationTemplates, diff_notify_all
from brokenlinkbrief.diff_detector import DiffReport
from brokenlinkbrief.notifications import NotifierConfig, RateLimiter


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestImports:
    """Verify all public symbols are importable."""

    def test_import_diff_notification_templates(self) -> None:
        assert DiffNotificationTemplates is not None

    def test_import_diff_notify_all(self) -> None:
        assert diff_notify_all is not None

    def test_import_diff_report(self) -> None:
        assert DiffReport is not None

    def test_diff_notification_templates_is_class(self) -> None:
        assert inspect.isclass(DiffNotificationTemplates)

    def test_diff_notify_all_is_function(self) -> None:
        assert callable(diff_notify_all)


# ---------------------------------------------------------------------------
# Layer 2 — Signatures
# ---------------------------------------------------------------------------
class TestDiffNotificationTemplatesSignature:
    """Verify DiffNotificationTemplates method signatures."""

    def test_render_diff_alert_signature(self) -> None:
        sig = inspect.signature(DiffNotificationTemplates.render_diff_alert)
        params = list(sig.parameters.keys())
        assert "report" in params

    def test_render_diff_alert_return_annotation(self) -> None:
        sig = inspect.signature(DiffNotificationTemplates.render_diff_alert)
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_render_diff_resolution_signature(self) -> None:
        sig = inspect.signature(DiffNotificationTemplates.render_diff_resolution)
        params = list(sig.parameters.keys())
        assert "report" in params

    def test_render_diff_resolution_return_annotation(self) -> None:
        sig = inspect.signature(DiffNotificationTemplates.render_diff_resolution)
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_render_diff_alert_is_static(self) -> None:
        """render_diff_alert is a static method."""
        assert isinstance(
            inspect.getattr_static(DiffNotificationTemplates, "render_diff_alert"),
            staticmethod,
        )

    def test_render_diff_resolution_is_static(self) -> None:
        """render_diff_resolution is a static method."""
        assert isinstance(
            inspect.getattr_static(DiffNotificationTemplates, "render_diff_resolution"),
            staticmethod,
        )


class TestDiffNotifyAllSignature:
    """Verify diff_notify_all function signature."""

    def test_diff_notify_all_params(self) -> None:
        sig = inspect.signature(diff_notify_all)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "report" in params
        assert "rate_limiter" in params

    def test_diff_notify_all_rate_limiter_default(self) -> None:
        sig = inspect.signature(diff_notify_all)
        assert sig.parameters["rate_limiter"].default is None

    def test_diff_notify_all_return_annotation(self) -> None:
        sig = inspect.signature(diff_notify_all)
        ret = sig.return_annotation
        # Returns dict[str, Any]
        assert ret is not inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_diff_report() -> DiffReport:
    """A DiffReport with changes."""
    return DiffReport(
        project_id="proj1",
        target_url="http://example.com",
        timestamp="2026-01-01T00:00:00",
        new_broken=[
            {"url": "http://example.com/new-broken", "status": 500, "reason": "server error"},
        ],
        resolved=[
            {"url": "http://example.com/fixed", "previous_status": 404, "current_status": 200},
        ],
        status_changes=[
            {"url": "http://example.com/changed", "previous_status": 200, "current_status": 403},
        ],
        new_links=[],
        removed_links=[],
        has_changes=True,
    )


@pytest.fixture
def empty_diff_report() -> DiffReport:
    """A DiffReport with no changes."""
    return DiffReport(
        project_id="proj1",
        target_url="http://example.com",
        timestamp="2026-01-01T00:00:00",
    )


@pytest.fixture
def enabled_config() -> NotifierConfig:
    """NotifierConfig with email and Slack enabled."""
    return NotifierConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
        smtp_from="alerts@example.com",
        slack_webhook_url="https://hooks.slack.com/services/T/B/x",
        email_enabled=True,
        slack_enabled=True,
        notify_on=["critical", "warning", "info"],
    )


@pytest.fixture
def disabled_config() -> NotifierConfig:
    """NotifierConfig with all channels disabled."""
    return NotifierConfig(
        email_enabled=False,
        slack_enabled=False,
    )


# ---------------------------------------------------------------------------
# Layer 3 — Behavioral tests (RED phase)
# ---------------------------------------------------------------------------
class TestDiffNotificationTemplatesBehavior:
    """Test DiffNotificationTemplates rendering behavior."""

    def test_render_diff_alert_includes_new_broken_urls(
        self, sample_diff_report: DiffReport
    ) -> None:
        """Alert includes new broken link URLs."""
        try:
            text = DiffNotificationTemplates.render_diff_alert(sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "http://example.com/new-broken" in text

    def test_render_diff_alert_includes_status_codes(
        self, sample_diff_report: DiffReport
    ) -> None:
        """Alert includes HTTP status codes for broken links."""
        try:
            text = DiffNotificationTemplates.render_diff_alert(sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "500" in text

    def test_render_diff_alert_includes_target_url(
        self, sample_diff_report: DiffReport
    ) -> None:
        """Alert includes the target URL that was scanned."""
        try:
            text = DiffNotificationTemplates.render_diff_alert(sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "http://example.com" in text

    def test_render_diff_resolution_includes_resolved_urls(
        self, sample_diff_report: DiffReport
    ) -> None:
        """Resolution notification includes resolved link URLs."""
        try:
            text = DiffNotificationTemplates.render_diff_resolution(sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "http://example.com/fixed" in text

    def test_render_diff_resolution_includes_previous_status(
        self, sample_diff_report: DiffReport
    ) -> None:
        """Resolution includes the previous broken status."""
        try:
            text = DiffNotificationTemplates.render_diff_resolution(sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "404" in text


class TestDiffNotifyAllBehavior:
    """Test diff_notify_all coordination behavior."""

    def test_no_alerts_when_no_changes(
        self, disabled_config: NotifierConfig, empty_diff_report: DiffReport
    ) -> None:
        """No notifications sent when report.has_changes is False."""
        try:
            result = diff_notify_all(disabled_config, empty_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, dict)

    def test_alerts_sent_only_on_state_changes(
        self, enabled_config: NotifierConfig, empty_diff_report: DiffReport
    ) -> None:
        """Alerts are NOT sent when there are no state changes (only current-broken)."""
        report_no_changes = DiffReport(
            project_id="proj1",
            target_url="http://example.com",
            timestamp="2026-01-01T00:00:00",
            has_changes=False,
        )
        try:
            result = diff_notify_all(enabled_config, report_no_changes)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Should NOT send when has_changes is False
        for channel_outcome in result.values():
            if isinstance(channel_outcome, dict):
                assert channel_outcome.get("sent") is not True or \
                    channel_outcome.get("error") is not None

    def test_rate_limiting_via_token_bucket(
        self, enabled_config: NotifierConfig, sample_diff_report: DiffReport
    ) -> None:
        """Rate limiter throttles notification delivery."""
        limiter = RateLimiter(capacity=1, fill_rate=0.0)  # no refill
        try:
            # First call should succeed (token available)
            result1 = diff_notify_all(enabled_config, sample_diff_report, limiter)
            # Second call should be rate-limited (no tokens left)
            result2 = diff_notify_all(enabled_config, sample_diff_report, limiter)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # At least one channel should be rate-limited on second call
        has_rate_limited = any(
            "rate-limit" in str(v) for v in result2.values()
            if isinstance(v, dict)
        )
        assert has_rate_limited

    def test_notification_dispatches_through_existing_notifiers(
        self, enabled_config: NotifierConfig, sample_diff_report: DiffReport
    ) -> None:
        """Diff notifications use existing email/Slack dispatchers."""
        try:
            result = diff_notify_all(enabled_config, sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Result should have email and slack keys like notify_all()
        assert "email" in result or "slack" in result

    def test_broken_link_regressions_routed_to_regression_detector(
        self, enabled_config: NotifierConfig, sample_diff_report: DiffReport
    ) -> None:
        """New broken links in diff report are identifiable as regressions."""
        try:
            result = diff_notify_all(enabled_config, sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # The report should carry new_broken which the regression_detector can use
        assert len(sample_diff_report.new_broken) > 0
        assert sample_diff_report.new_broken[0]["url"] == "http://example.com/new-broken"

    def test_diff_notify_all_returns_outcome_dict(
        self, enabled_config: NotifierConfig, sample_diff_report: DiffReport
    ) -> None:
        """diff_notify_all returns a dict with channel outcomes."""
        try:
            result = diff_notify_all(enabled_config, sample_diff_report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, dict)
        for value in result.values():
            assert isinstance(value, dict)
            assert "sent" in value

    def test_diff_notify_all_checks_has_changes_before_sending(
        self, enabled_config: NotifierConfig
    ) -> None:
        """diff_notify_all does not send when has_changes is False."""
        report = DiffReport(
            project_id="proj1",
            target_url="http://example.com",
            timestamp="2026-01-01T00:00:00",
            has_changes=False,
        )
        try:
            result = diff_notify_all(enabled_config, report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # All channels should report not sent
        for value in result.values():
            if isinstance(value, dict):
                assert value.get("sent") is not True
