"""Pre-development tests for RegressionDetector and RegressionNotifier.

Interface tests: verify module loads, classes exist, method signatures correct.
Behavioral tests: expected behavior that raises NotImplementedError until implemented.
"""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass

import pytest

from brokenlinkbrief.regression_detector import (
    RegressionDetector,
    RegressionNotifier,
    RegressionReport,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_current_results() -> dict[str, list[dict]]:
    """Simulated current scan results (url -> list of link result dicts)."""
    return {
        "https://example.com": [
            {
                "url": "https://example.com/style.css",
                "status": 200,
                "reason": "OK",
                "location": None,
            },
            {
                "url": "https://example.com/missing.js",
                "status": 404,
                "reason": "Not Found",
                "location": None,
            },
        ],
        "https://example.com/api": [
            {
                "url": "https://example.com/api/health",
                "status": 200,
                "reason": "OK",
                "location": None,
            },
            {
                "url": "https://example.com/api/docs",
                "status": 503,
                "reason": "Service Unavailable",
                "location": None,
            },
        ],
    }


@pytest.fixture
def sample_previous_scan() -> dict:
    """Simulated previous successful scan_history entry."""
    return {
        "scan_id": "scan_prev_001",
        "project_id": "proj_test_001",
        "status": "completed",
        "scan_timestamp": "2026-07-30T09:00:00Z",
        "raw_results": {
            "https://example.com": [
                {"url": "https://example.com/style.css", "status": 200},
                {
                    "url": "https://example.com/missing.js",
                    "status": 200,
                },  # was OK, now 404
            ],
            "https://example.com/api": [
                {"url": "https://example.com/api/health", "status": 200},
                {
                    "url": "https://example.com/api/docs",
                    "status": 200,
                },  # was OK, now 503
            ],
        },
    }


@pytest.fixture
def sample_scan_history(sample_previous_scan: dict) -> list[dict]:
    """Simulated scan_history list with one previous successful scan."""
    return [sample_previous_scan]


@pytest.fixture
def previous_with_resolved() -> dict:
    """Previous scan where a link was broken (now resolved)."""
    return {
        "scan_id": "scan_prev_002",
        "project_id": "proj_test_001",
        "status": "completed",
        "scan_timestamp": "2026-07-29T09:00:00Z",
        "raw_results": {
            "https://example.com": [
                {"url": "https://example.com/old-broken.html", "status": 500},
                {"url": "https://example.com/ok.html", "status": 200},
            ],
        },
    }


@pytest.fixture
def notification_channels() -> list[dict]:
    """Sample notification channel configs."""
    return [
        {"type": "email", "target": "ops@example.com"},
        {
            "type": "slack",
            "target": "#alerts",
            "webhook_url": "https://hooks.slack.com/xxx",
        },
    ]


@pytest.fixture
def sample_regression_report() -> RegressionReport:
    """A pre-built RegressionReport with regressions."""
    return RegressionReport(
        project_id="proj_test_001",
        scan_id="scan_curr_001",
        previous_scan_id="scan_prev_001",
        timestamp="2026-07-31T09:00:00Z",
        new_broken=[
            {
                "url": "https://example.com/missing.js",
                "status": 404,
                "reason": "Not Found",
                "previous_status": 200,
            },
        ],
        resolved=[],
        status_changes=[
            {
                "url": "https://example.com/api/docs",
                "previous_status": 200,
                "current_status": 503,
            },
        ],
        has_regressions=True,
    )


@pytest.fixture
def clean_report() -> RegressionReport:
    """A RegressionReport with no regressions (only resolved)."""
    return RegressionReport(
        project_id="proj_test_001",
        scan_id="scan_curr_002",
        previous_scan_id="scan_prev_002",
        timestamp="2026-07-31T10:00:00Z",
        new_broken=[],
        resolved=[
            {
                "url": "https://example.com/old-broken.html",
                "previous_status": 500,
                "current_status": 200,
            },
        ],
        status_changes=[],
        has_regressions=False,
    )


# ============================================================================
# SECTION 1: IMPORT & CLASS EXISTENCE TESTS (should PASS immediately)
# ============================================================================


class TestModuleImport:
    """Verify module loads and classes are accessible."""

    def test_module_importable(self):
        """regression_detector module imports without error."""
        from brokenlinkbrief import regression_detector

        assert regression_detector is not None

    def test_detector_class_exists(self):
        """RegressionDetector class is importable."""
        assert RegressionDetector is not None

    def test_notifier_class_exists(self):
        """RegressionNotifier class is importable."""
        assert RegressionNotifier is not None

    def test_report_class_exists(self):
        """RegressionReport dataclass is importable."""
        assert RegressionReport is not None

    def test_detector_is_class(self):
        """RegressionDetector is a class (not a function or module)."""
        assert isinstance(RegressionDetector, type)

    def test_notifier_is_class(self):
        """RegressionNotifier is a class."""
        assert isinstance(RegressionNotifier, type)

    def test_report_is_dataclass(self):
        """RegressionReport is a dataclass."""
        assert is_dataclass(RegressionReport)


# ============================================================================
# SECTION 2: RegressionReport DATACLASS FIELD TESTS (should PASS immediately)
# ============================================================================


class TestRegressionReportFields:
    """Verify RegressionReport dataclass has all required fields."""

    def test_is_dataclass(self):
        assert is_dataclass(RegressionReport)

    def test_has_field_project_id(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "project_id" in field_names

    def test_has_field_scan_id(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "scan_id" in field_names

    def test_has_field_previous_scan_id(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "previous_scan_id" in field_names

    def test_has_field_timestamp(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "timestamp" in field_names

    def test_has_field_new_broken(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "new_broken" in field_names

    def test_has_field_resolved(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "resolved" in field_names

    def test_has_field_status_changes(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "status_changes" in field_names

    def test_has_field_has_regressions(self):
        field_names = {f.name for f in fields(RegressionReport)}
        assert "has_regressions" in field_names

    def test_field_count(self):
        """RegressionReport has exactly 8 fields."""
        assert len(fields(RegressionReport)) == 8

    def test_new_broken_default_is_empty_list(self):
        """new_broken defaults to empty list."""
        report = RegressionReport(
            project_id="p1", scan_id="s1", previous_scan_id=None, timestamp="t"
        )
        assert report.new_broken == []

    def test_resolved_default_is_empty_list(self):
        """resolved defaults to empty list."""
        report = RegressionReport(
            project_id="p1", scan_id="s1", previous_scan_id=None, timestamp="t"
        )
        assert report.resolved == []

    def test_status_changes_default_is_empty_list(self):
        """status_changes defaults to empty list."""
        report = RegressionReport(
            project_id="p1", scan_id="s1", previous_scan_id=None, timestamp="t"
        )
        assert report.status_changes == []

    def test_has_regressions_default_is_false(self):
        """has_regressions defaults to False."""
        report = RegressionReport(
            project_id="p1", scan_id="s1", previous_scan_id=None, timestamp="t"
        )
        assert report.has_regressions is False


# ============================================================================
# SECTION 3: SIGNATURE / INTERFACE TESTS (should PASS immediately)
# ============================================================================


class TestRegressionDetectorSignature:
    """Verify RegressionDetector method signatures match expected interface."""

    def test_init_signature(self):
        sig = inspect.signature(RegressionDetector.__init__)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "scan_history" in param_names

    def test_init_scan_history_default_is_none(self):
        sig = inspect.signature(RegressionDetector.__init__)
        assert sig.parameters["scan_history"].default is None

    def test_detect_signature(self):
        sig = inspect.signature(RegressionDetector.detect)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "project_id" in param_names
        assert "current_results" in param_names
        assert "scan_history" in param_names

    def test_detect_scan_history_default_is_none(self):
        sig = inspect.signature(RegressionDetector.detect)
        assert sig.parameters["scan_history"].default is None

    def test_detect_return_annotation(self):
        sig = inspect.signature(RegressionDetector.detect)
        ret = sig.return_annotation
        # With `from __future__ import annotations`, ret is a string
        assert ret is RegressionReport or ret == "RegressionReport"

    def test_get_last_successful_signature(self):
        sig = inspect.signature(RegressionDetector.get_last_successful)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "scan_history" in param_names

    def test_compare_link_is_static(self):
        """compare_link is a static method."""
        assert isinstance(
            inspect.getattr_static(RegressionDetector, "compare_link"),
            staticmethod,
        )

    def test_compare_link_signature(self):
        sig = inspect.signature(RegressionDetector.compare_link)
        param_names = list(sig.parameters.keys())
        assert "current" in param_names
        assert "previous" in param_names
        assert "self" not in param_names  # static method

    def test_compare_link_return_annotation(self):
        sig = inspect.signature(RegressionDetector.compare_link)
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_extract_broken_urls_is_static(self):
        """extract_broken_urls is a static method."""
        assert isinstance(
            inspect.getattr_static(RegressionDetector, "extract_broken_urls"),
            staticmethod,
        )

    def test_extract_broken_urls_signature(self):
        sig = inspect.signature(RegressionDetector.extract_broken_urls)
        param_names = list(sig.parameters.keys())
        assert "results" in param_names
        assert "self" not in param_names  # static method

    def test_extract_broken_urls_return_annotation(self):
        sig = inspect.signature(RegressionDetector.extract_broken_urls)
        ret = sig.return_annotation
        # Returns set[str]
        assert "set" in str(ret).lower() or ret is set


class TestRegressionNotifierSignature:
    """Verify RegressionNotifier method signatures match expected interface."""

    def test_init_signature(self):
        sig = inspect.signature(RegressionNotifier.__init__)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "notifier_config" in param_names
        assert "rate_limiter" in param_names

    def test_init_defaults(self):
        sig = inspect.signature(RegressionNotifier.__init__)
        assert sig.parameters["notifier_config"].default is None
        assert sig.parameters["rate_limiter"].default is None

    def test_notify_signature(self):
        sig = inspect.signature(RegressionNotifier.notify)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "report" in param_names
        assert "notification_channels" in param_names

    def test_notify_return_annotation(self):
        sig = inspect.signature(RegressionNotifier.notify)
        ret = sig.return_annotation
        # Returns dict[str, Any]
        assert "dict" in str(ret).lower() or ret is dict

    def test_format_alert_signature(self):
        sig = inspect.signature(RegressionNotifier.format_alert)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "report" in param_names

    def test_format_alert_return_annotation(self):
        sig = inspect.signature(RegressionNotifier.format_alert)
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_format_resolution_signature(self):
        sig = inspect.signature(RegressionNotifier.format_resolution)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "report" in param_names

    def test_format_resolution_return_annotation(self):
        sig = inspect.signature(RegressionNotifier.format_resolution)
        ret = sig.return_annotation
        assert ret is str or ret == "str"

    def test_should_notify_signature(self):
        sig = inspect.signature(RegressionNotifier.should_notify)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "report" in param_names

    def test_should_notify_return_annotation(self):
        sig = inspect.signature(RegressionNotifier.should_notify)
        ret = sig.return_annotation
        assert ret is bool or ret == "bool"


# ============================================================================
# SECTION 4: BEHAVIORAL TESTS — REGRESSION DETECTOR INIT (RED phase)
# ============================================================================


class TestDetectorInit:
    """Behavioral tests for RegressionDetector initialization."""

    def test_default_init(self):
        """Detector can be created with defaults."""
        try:
            detector = RegressionDetector()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert detector is not None

    def test_init_with_history(self):
        """Detector can be created with scan_history."""
        try:
            detector = RegressionDetector(scan_history=[{"scan_id": "s1"}])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert detector is not None

# ============================================================================
# SECTION 5: BEHAVIORAL TESTS — DETECT (RED phase)
# ============================================================================


class TestDetect:
    """Behavioral tests for the detect method."""

    def test_returns_regression_report(self):
        """detect returns a RegressionReport instance."""
        try:
            detector = RegressionDetector()
            report = detector.detect(
                project_id="proj1",
                current_results={
                    "https://a.com": [
                        {
                            "url": "https://a.com",
                            "status": 200,
                            "reason": "OK",
                            "location": None,
                        }
                    ]
                },
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(report, RegressionReport)

    def test_report_has_project_id(self):
        """Report.project_id matches input."""
        try:
            detector = RegressionDetector()
            report = detector.detect(
                project_id="proj_xyz",
                current_results={},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.project_id == "proj_xyz"

    def test_report_has_timestamp(self):
        """Report.timestamp is a non-empty string."""
        try:
            detector = RegressionDetector()
            report = detector.detect(project_id="p1", current_results={})
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(report.timestamp, str)
        assert len(report.timestamp) > 0

    def test_no_previous_no_regressions(self):
        """With no previous scan, has_regressions is False."""
        try:
            detector = RegressionDetector()
            report = detector.detect(
                project_id="p1",
                current_results={
                    "https://a.com": [
                        {
                            "url": "https://a.com",
                            "status": 200,
                            "reason": "OK",
                            "location": None,
                        }
                    ]
                },
                scan_history=None,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_regressions is False
        assert report.new_broken == []
        assert report.previous_scan_id is None

    def test_detects_new_broken_links(self):
        """Detects links that were OK previously but are now broken."""
        try:
            detector = RegressionDetector()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com/page",
                        "status": 404,
                        "reason": "Not Found",
                        "location": None,
                    },
                ],
            }
            history = [
                {
                    "scan_id": "prev1",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [
                            {"url": "https://a.com/page", "status": 200},
                        ],
                    },
                },
            ]
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_regressions is True
        assert len(report.new_broken) >= 1
        assert any("a.com/page" in b.get("url", "") for b in report.new_broken)

    def test_detects_resolved_links(self):
        """Detects links that were broken but are now OK."""
        try:
            detector = RegressionDetector()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com/fixed",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    },
                ],
            }
            history = [
                {
                    "scan_id": "prev2",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [
                            {"url": "https://a.com/fixed", "status": 500},
                        ],
                    },
                },
            ]
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(report.resolved) >= 1
        assert any("a.com/fixed" in r.get("url", "") for r in report.resolved)

    def test_detects_status_changes(self):
        """Status changed between two different broken codes."""
        try:
            detector = RegressionDetector()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com/page",
                        "status": 503,
                        "reason": "Unavailable",
                        "location": None,
                    },
                ],
            }
            history = [
                {
                    "scan_id": "prev3",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [
                            {"url": "https://a.com/page", "status": 404},
                        ],
                    },
                },
            ]
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(report.status_changes) >= 1

    def test_no_regressions_when_all_unchanged(self):
        """has_regressions is False when nothing changed."""
        try:
            detector = RegressionDetector()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com/ok",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    },
                ],
            }
            history = [
                {
                    "scan_id": "prev4",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [
                            {"url": "https://a.com/ok", "status": 200},
                        ],
                    },
                },
            ]
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_regressions is False
        assert report.new_broken == []
        assert report.status_changes == []

    def test_ignores_non_completed_history(self):
        """Only uses 'completed' scans from history for comparison."""
        try:
            detector = RegressionDetector()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com/page",
                        "status": 404,
                        "reason": "Not Found",
                        "location": None,
                    },
                ],
            }
            history = [
                {
                    "scan_id": "prev_failed",
                    "project_id": "p1",
                    "status": "failed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {},
                },
            ]
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # No successful previous scan → no regressions detected
        assert report.has_regressions is False
        assert report.previous_scan_id is None

# ============================================================================
# SECTION 6: BEHAVIORAL TESTS — GET_LAST_SUCCESSFUL (RED phase)
# ============================================================================


class TestGetLastSuccessful:
    """Behavioral tests for get_last_successful."""

    def test_returns_most_recent_completed(self):
        """Returns the most recent completed scan from history."""
        try:
            detector = RegressionDetector()
            history = [
                {
                    "scan_id": "s1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-29T09:00:00Z",
                },
                {
                    "scan_id": "s2",
                    "status": "failed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                },
                {
                    "scan_id": "s3",
                    "status": "completed",
                    "scan_timestamp": "2026-07-31T09:00:00Z",
                },
            ]
            result = detector.get_last_successful(history)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is not None
        assert result["scan_id"] == "s3"

    def test_returns_none_when_no_completed(self):
        """Returns None when no scan has status 'completed'."""
        try:
            detector = RegressionDetector()
            history = [
                {
                    "scan_id": "s1",
                    "status": "failed",
                    "scan_timestamp": "2026-07-29T09:00:00Z",
                },
                {
                    "scan_id": "s2",
                    "status": "running",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                },
            ]
            result = detector.get_last_successful(history)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is None

    def test_returns_none_for_empty_history(self):
        """Returns None for empty history list."""
        try:
            detector = RegressionDetector()
            result = detector.get_last_successful([])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is None

# ============================================================================
# SECTION 7: BEHAVIORAL TESTS — COMPARE_LINK (RED phase)
# ============================================================================


class TestCompareLink:
    """Behavioral tests for the static compare_link method."""

    def test_unchanged_200(self):
        """Both 200 → 'unchanged'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 200},
                {"url": "https://a.com", "status": 200},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "unchanged"

    def test_new_broken_200_to_404(self):
        """200 → 404 → 'new_broken'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 404},
                {"url": "https://a.com", "status": 200},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "new_broken"

    def test_new_broken_200_to_500(self):
        """200 → 500 → 'new_broken'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 500},
                {"url": "https://a.com", "status": 200},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "new_broken"

    def test_resolved_404_to_200(self):
        """404 → 200 → 'resolved'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 200},
                {"url": "https://a.com", "status": 404},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "resolved"

    def test_status_change_404_to_503(self):
        """404 → 503 → 'status_change'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 503},
                {"url": "https://a.com", "status": 404},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "status_change"

    def test_new_broken_none_to_404(self):
        """None → 404 → 'new_broken'."""
        try:
            result = RegressionDetector.compare_link(
                {"url": "https://a.com", "status": 404},
                {"url": "https://a.com", "status": None},
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == "new_broken"




# ============================================================================
# SECTION 8: BEHAVIORAL TESTS — EXTRACT_BROKEN_URLS (RED phase)
# ============================================================================


class TestExtractBrokenUrls:
    """Behavioral tests for the static extract_broken_urls method."""

    def test_404_is_broken(self):
        """Status 404 is identified as broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [{"url": "https://a.com/bad", "status": 404}],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/bad" in urls

    def test_500_is_broken(self):
        """Status 500 is identified as broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [{"url": "https://a.com/bad", "status": 500}],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/bad" in urls

    def test_200_not_broken(self):
        """Status 200 is not broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [{"url": "https://a.com/ok", "status": 200}],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/ok" not in urls

    def test_301_not_broken(self):
        """Status 301 (redirect) is not broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [{"url": "https://a.com/redir", "status": 301}],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/redir" not in urls

    def test_none_status_with_reason_is_broken(self):
        """None status with a reason (timeout) is broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [
                        {
                            "url": "https://a.com/timeout",
                            "status": None,
                            "reason": "timeout",
                        }
                    ],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/timeout" in urls

    def test_none_status_without_reason_not_broken(self):
        """None status without reason is not broken."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [
                        {"url": "https://a.com/unknown", "status": None, "reason": None}
                    ],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com/unknown" not in urls

    def test_empty_results_returns_empty_set(self):
        """Empty results → empty set."""
        try:
            urls = RegressionDetector.extract_broken_urls({})
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert urls == set()

    def test_returns_set(self):
        """Return type is a set."""
        try:
            urls = RegressionDetector.extract_broken_urls(
                {
                    "https://a.com": [{"url": "https://a.com/bad", "status": 500}],
                }
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(urls, set)

# ============================================================================
# SECTION 9: BEHAVIORAL TESTS — REGRESSION NOTIFIER INIT (RED phase)
# ============================================================================


class TestNotifierInit:
    """Behavioral tests for RegressionNotifier initialization."""

    def test_default_init(self):
        """Notifier can be created with defaults."""
        try:
            notifier = RegressionNotifier()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert notifier is not None

    def test_init_with_config(self):
        """Notifier can be created with a notifier_config."""
        try:
            from brokenlinkbrief.notifications import NotifierConfig

            config = NotifierConfig()
            notifier = RegressionNotifier(notifier_config=config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert notifier is not None

# ============================================================================
# SECTION 10: BEHAVIORAL TESTS — NOTIFY (RED phase)
# ============================================================================


class TestNotify:
    """Behavioral tests for RegressionNotifier.notify."""

    def test_returns_dict(self):
        """notify returns a dict of delivery outcomes."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                has_regressions=True,
                new_broken=[{"url": "https://a.com", "status": 404}],
            )
            result = notifier.notify(report, [{"type": "email", "target": "x@y.com"}])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, dict)

    def test_empty_channels_returns_empty_dict(self):
        """Empty channels → empty outcome dict."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                has_regressions=True,
            )
            result = notifier.notify(report, [])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == {}




# ============================================================================
# SECTION 11: BEHAVIORAL TESTS — FORMAT_ALERT (RED phase)
# ============================================================================


class TestFormatAlert:
    """Behavioral tests for RegressionNotifier.format_alert."""

    def test_returns_string(self):
        """format_alert returns a non-empty string."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id="s0",
                timestamp="2026-07-31T09:00:00Z",
                new_broken=[
                    {
                        "url": "https://a.com/bad",
                        "status": 404,
                        "reason": "Not Found",
                        "previous_status": 200,
                    },
                ],
                has_regressions=True,
            )
            msg = notifier.format_alert(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_includes_project_id(self):
        """Alert message contains the project_id."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="proj_xyz",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                new_broken=[{"url": "https://a.com", "status": 404}],
                has_regressions=True,
            )
            msg = notifier.format_alert(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "proj_xyz" in msg

    def test_includes_broken_urls(self):
        """Alert message includes broken URL information."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                new_broken=[
                    {
                        "url": "https://example.com/missing",
                        "status": 404,
                        "previous_status": 200,
                    },
                ],
                has_regressions=True,
            )
            msg = notifier.format_alert(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "example.com/missing" in msg




# ============================================================================
# SECTION 12: BEHAVIORAL TESTS — FORMAT_RESOLUTION (RED phase)
# ============================================================================


class TestFormatResolution:
    """Behavioral tests for RegressionNotifier.format_resolution."""

    def test_returns_string(self):
        """format_resolution returns a non-empty string."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id="s0",
                timestamp="2026-07-31T09:00:00Z",
                resolved=[
                    {
                        "url": "https://a.com/fixed",
                        "previous_status": 500,
                        "current_status": 200,
                    },
                ],
                has_regressions=False,
            )
            msg = notifier.format_resolution(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_includes_resolved_urls(self):
        """Resolution message includes resolved URL information."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                resolved=[
                    {
                        "url": "https://example.com/fixed",
                        "previous_status": 500,
                        "current_status": 200,
                    },
                ],
                has_regressions=False,
            )
            msg = notifier.format_resolution(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "example.com/fixed" in msg

# ============================================================================
# SECTION 13: BEHAVIORAL TESTS — SHOULD_NOTIFY (RED phase)
# ============================================================================


class TestShouldNotify:
    """Behavioral tests for RegressionNotifier.should_notify."""

    def test_true_when_has_new_broken(self):
        """should_notify is True when report has new_broken links."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                new_broken=[{"url": "https://a.com", "status": 404}],
                has_regressions=True,
            )
            result = notifier.should_notify(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is True

    def test_true_when_has_resolved(self):
        """should_notify is True when report has resolved links (positive news)."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                resolved=[
                    {
                        "url": "https://a.com",
                        "previous_status": 500,
                        "current_status": 200,
                    }
                ],
                has_regressions=False,
            )
            result = notifier.should_notify(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is True

    def test_false_when_nothing_interesting(self):
        """should_notify is False when no regressions or resolutions."""
        try:
            notifier = RegressionNotifier()
            report = RegressionReport(
                project_id="p1",
                scan_id="s1",
                previous_scan_id=None,
                timestamp="t",
                has_regressions=False,
            )
            result = notifier.should_notify(report)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result is False

# ============================================================================
# SECTION 14: CROSS-MODULE INTEGRATION TESTS (RED phase)
# ============================================================================


class TestNotificationIntegration:
    """Verify RegressionNotifier integrates with existing notifications module."""

    def test_notifier_imports_from_notifications(self):
        """RegressionNotifier's notifier_config type is NotifierConfig."""
        try:
            from brokenlinkbrief.notifications import NotifierConfig

            config = NotifierConfig()
            notifier = RegressionNotifier(notifier_config=config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert notifier is not None

    def test_can_use_rate_limiter(self):
        """RegressionNotifier accepts a RateLimiter."""
        try:
            from brokenlinkbrief.notifications import NotifierConfig, RateLimiter

            config = NotifierConfig()
            limiter = RateLimiter(capacity=10, fill_rate=0.1667)
            notifier = RegressionNotifier(notifier_config=config, rate_limiter=limiter)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert notifier is not None


# ============================================================================
# SECTION 15: EDGE CASE TESTS (RED phase)
# ============================================================================


class TestEdgeCases:
    """Edge case behavioral tests for regression detection."""

    def test_empty_current_results(self):
        """Empty current results with history → no regressions."""
        try:
            detector = RegressionDetector()
            history = [
                {
                    "scan_id": "prev1",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [{"url": "https://a.com", "status": 200}]
                    },
                },
            ]
            report = detector.detect(
                project_id="p1", current_results={}, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_regressions is False

    def test_history_with_multiple_entries_uses_most_recent(self):
        """When history has multiple entries, uses the most recent completed one."""
        try:
            detector = RegressionDetector()
            history = [
                {
                    "scan_id": "old",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-28T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [{"url": "https://a.com", "status": 200}]
                    },
                },
                {
                    "scan_id": "newer",
                    "project_id": "p1",
                    "status": "completed",
                    "scan_timestamp": "2026-07-30T09:00:00Z",
                    "raw_results": {
                        "https://a.com": [{"url": "https://a.com", "status": 404}]
                    },
                },
            ]
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    }
                ]
            }
            report = detector.detect(
                project_id="p1", current_results=current, scan_history=history
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # "newer" scan had 404, current has 200 → resolved (not regression)
        assert len(report.resolved) >= 1

    def test_report_serializable(self):
        """RegressionReport can be converted to dict (for JSON serialisation)."""
        report = RegressionReport(
            project_id="p1",
            scan_id="s1",
            previous_scan_id="s0",
            timestamp="2026-07-31T09:00:00Z",
            new_broken=[{"url": "https://a.com", "status": 404}],
            resolved=[],
            status_changes=[],
            has_regressions=True,
        )
        import json

        d = {
            "project_id": report.project_id,
            "scan_id": report.scan_id,
            "new_broken": report.new_broken,
            "resolved": report.resolved,
            "status_changes": report.status_changes,
            "has_regressions": report.has_regressions,
        }
        # Should not raise
        json.dumps(d)

    def test_new_broken_count_matches_list_length(self):
        """new_broken list length reflects the actual count."""
        report = RegressionReport(
            project_id="p1",
            scan_id="s1",
            previous_scan_id=None,
            timestamp="t",
            new_broken=[
                {"url": "https://a.com/1", "status": 404},
                {"url": "https://a.com/2", "status": 500},
            ],
        )
        assert len(report.new_broken) == 2
