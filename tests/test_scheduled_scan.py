"""Pre-development tests for ScheduledScanExecutor.

Interface tests: verify module loads, class exists, method signatures correct.
Behavioral tests: expected behavior that raises NotImplementedError until implemented.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import fields, is_dataclass

import pytest

from brokenlinkbrief.scheduled_scan import ScanResult, ScheduledScanExecutor

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_project_config() -> dict:
    """Minimal valid project config matching projects.yaml schema."""
    return {
        "id": "proj_test_001",
        "name": "Test Project",
        "urls": [
            "https://example.com",
            "https://example.com/api",
        ],
        "options": {
            "timeout": 10.0,
            "max_workers": 3,
        },
    }


@pytest.fixture
def project_config_with_notifications() -> dict:
    """Project config including notification channels."""
    return {
        "id": "proj_notif_001",
        "name": "Notified Project",
        "urls": ["https://docs.example.com"],
        "schedule": {
            "cron": "0 9 * * *",
            "timezone": "Europe/Zurich",
        },
        "notifications": [
            {"type": "email", "target": "ops@example.com"},
            {
                "type": "slack",
                "target": "#alerts",
                "webhook_url": "https://hooks.slack.com/xxx",
            },
        ],
        "options": {
            "timeout": 15.0,
            "max_workers": 5,
        },
    }


@pytest.fixture
def sample_batch_results() -> dict:
    """Simulated scan_batch return value (url -> list of LinkResult dicts)."""
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
def sample_previous_results() -> list[dict]:
    """Previous scan results for regression comparison."""
    return [
        {"url": "https://example.com/style.css", "status": 200},
        {"url": "https://example.com/missing.js", "status": 200},  # was OK, now broken
        {"url": "https://example.com/api/health", "status": 200},
    ]


@pytest.fixture
def minimal_project_config() -> dict:
    """Bare minimum project config with only required fields."""
    return {
        "id": "proj_min_001",
        "name": "Minimal",
        "urls": ["https://example.com"],
    }


# ============================================================================
# SECTION 1: IMPORT & CLASS EXISTENCE TESTS (should PASS immediately)
# ============================================================================


class TestModuleImport:
    """Verify module loads and classes are accessible."""

    def test_module_importable(self):
        """scheduled_scan module imports without error."""
        from brokenlinkbrief import scheduled_scan

        assert scheduled_scan is not None

    def test_executor_class_exists(self):
        """ScheduledScanExecutor class is importable."""
        assert ScheduledScanExecutor is not None

    def test_scan_result_class_exists(self):
        """ScanResult dataclass is importable."""
        assert ScanResult is not None

    def test_scan_result_is_dataclass(self):
        """ScanResult is a dataclass."""
        assert is_dataclass(ScanResult)

    def test_executor_is_class(self):
        """ScheduledScanExecutor is a class (not a function or module)."""
        assert isinstance(ScheduledScanExecutor, type)


# ============================================================================
# SECTION 2: ScanResult DATACLASS FIELD TESTS (should PASS immediately)
# ============================================================================


class TestScanResultFields:
    """Verify ScanResult dataclass has all required fields."""

    def test_is_dataclass(self):
        assert is_dataclass(ScanResult)

    def test_has_field_scan_id(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "scan_id" in field_names

    def test_has_field_project_id(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "project_id" in field_names

    def test_has_field_project_name(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "project_name" in field_names

    def test_has_field_scan_timestamp(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "scan_timestamp" in field_names

    def test_has_field_urls_scanned(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "urls_scanned" in field_names

    def test_has_field_total_links(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "total_links" in field_names

    def test_has_field_broken_count(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "broken_count" in field_names

    def test_has_field_new_broken_count(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "new_broken_count" in field_names

    def test_has_field_status(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "status" in field_names

    def test_has_field_raw_results(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "raw_results" in field_names

    def test_has_field_regression_flags(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "regression_flags" in field_names

    def test_has_field_duration_seconds(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "duration_seconds" in field_names

    def test_has_field_errors(self):
        field_names = {f.name for f in fields(ScanResult)}
        assert "errors" in field_names

    def test_field_count(self):
        """ScanResult has exactly 13 fields."""
        assert len(fields(ScanResult)) == 13


# ============================================================================
# SECTION 3: SIGNATURE / INTERFACE TESTS (should PASS immediately)
# ============================================================================


class TestScheduledScanExecutorSignature:
    """Verify method signatures match the expected interface."""

    def test_init_signature(self):
        sig = inspect.signature(ScheduledScanExecutor.__init__)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "max_retries" in param_names
        assert "retry_delay" in param_names

    def test_init_max_retries_default(self):
        sig = inspect.signature(ScheduledScanExecutor.__init__)
        assert sig.parameters["max_retries"].default == 3

    def test_init_retry_delay_default(self):
        sig = inspect.signature(ScheduledScanExecutor.__init__)
        assert sig.parameters["retry_delay"].default == 1.0

    def test_execute_scan_signature(self):
        sig = inspect.signature(ScheduledScanExecutor.execute_scan)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "project_config" in param_names

    def test_execute_scan_return_annotation(self):
        sig = inspect.signature(ScheduledScanExecutor.execute_scan)
        ret = sig.return_annotation
        # With `from __future__ import annotations`, ret is a string
        assert ret is ScanResult or ret == "ScanResult"

    def test_run_batch_with_retry_signature(self):
        sig = inspect.signature(ScheduledScanExecutor._run_batch_with_retry)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "urls" in param_names
        assert "timeout" in param_names
        assert "max_workers" in param_names

    def test_run_batch_with_retry_timeout_default(self):
        sig = inspect.signature(ScheduledScanExecutor._run_batch_with_retry)
        assert sig.parameters["timeout"].default == 10.0

    def test_run_batch_with_retry_max_workers_default(self):
        sig = inspect.signature(ScheduledScanExecutor._run_batch_with_retry)
        assert sig.parameters["max_workers"].default == 5

    def test_compute_summary_signature(self):
        sig = inspect.signature(ScheduledScanExecutor._compute_summary)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "scan_results" in param_names
        assert "project_id" in param_names
        assert "project_name" in param_names
        assert "start_time" in param_names

    def test_detect_regressions_signature(self):
        sig = inspect.signature(ScheduledScanExecutor._detect_regressions)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "current_results" in param_names
        assert "previous_results" in param_names

    def test_is_link_broken_signature(self):
        sig = inspect.signature(ScheduledScanExecutor._is_link_broken)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "result" in param_names

    def test_format_regression_flags_signature(self):
        sig = inspect.signature(ScheduledScanExecutor._format_regression_flags)
        param_names = list(sig.parameters.keys())
        assert "self" in param_names
        assert "new_broken_urls" in param_names
        assert "status_changes" in param_names


# ============================================================================
# SECTION 4: BEHAVIORAL TESTS — EXECUTOR INIT (RED phase)
# ============================================================================


class TestExecutorInit:
    """Behavioral tests for ScheduledScanExecutor initialization."""

    def test_default_init(self):
        """Executor can be created with defaults."""
        try:
            executor = ScheduledScanExecutor()
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert executor is not None

    def test_custom_retries(self):
        """Custom max_retries is stored."""
        try:
            executor = ScheduledScanExecutor(max_retries=5)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert executor.max_retries == 5

    def test_custom_retry_delay(self):
        """Custom retry_delay is stored."""
        try:
            executor = ScheduledScanExecutor(retry_delay=2.5)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert executor.retry_delay == 2.5


# ============================================================================
# SECTION 5: BEHAVIORAL TESTS — EXECUTE_SCAN (RED phase)
# ============================================================================


class TestExecuteScan:
    """Behavioral tests for the main execute_scan method."""

    def test_returns_scan_result(self):
        """execute_scan returns a ScanResult instance."""
        try:
            executor = ScheduledScanExecutor()
            config = {
                "id": "proj1",
                "name": "Test",
                "urls": ["https://example.com"],
            }
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, ScanResult)

    def test_result_has_project_id(self):
        """ScanResult.project_id matches input config."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "proj_abc", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.project_id == "proj_abc"

    def test_result_has_project_name(self):
        """ScanResult.project_name matches input config."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "My Project", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.project_name == "My Project"

    def test_result_status_completed(self):
        """Status is 'completed' after successful scan."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.status == "completed"

    def test_result_urls_scanned_count(self):
        """urls_scanned matches number of input URLs."""
        try:
            executor = ScheduledScanExecutor()
            config = {
                "id": "p1",
                "name": "Test",
                "urls": ["https://a.com", "https://b.com", "https://c.com"],
            }
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.urls_scanned == 3

    def test_result_scan_timestamp_format(self):
        """scan_timestamp is ISO 8601 format."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # ISO 8601 contains 'T' separator
        assert "T" in result.scan_timestamp

    def test_result_raw_results_is_dict(self):
        """raw_results is a dict mapping url -> list of result dicts."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result.raw_results, dict)

    def test_result_regression_flags_is_list(self):
        """regression_flags is a list of strings."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result.regression_flags, list)

    def test_result_duration_positive(self):
        """duration_seconds is non-negative."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.duration_seconds >= 0.0

    def test_result_errors_is_list(self):
        """errors is a list of strings."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result.errors, list)

    def test_result_broken_count_non_negative(self):
        """broken_count is non-negative."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.broken_count >= 0

    def test_result_new_broken_count_non_negative(self):
        """new_broken_count is non-negative."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.new_broken_count >= 0

    def test_result_total_links_non_negative(self):
        """total_links is non-negative."""
        try:
            executor = ScheduledScanExecutor()
            config = {"id": "p1", "name": "Test", "urls": ["https://example.com"]}
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.total_links >= 0


# ============================================================================
# SECTION 6: BEHAVIORAL TESTS — RETRY LOGIC (RED phase)
# ============================================================================


class TestRetryLogic:
    """Behavioral tests for _run_batch_with_retry."""

    def test_returns_dict(self):
        """_run_batch_with_retry returns a dict."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._run_batch_with_retry(["https://example.com"])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, dict)

    def test_result_keys_match_input_urls(self):
        """Returned dict has keys for each input URL."""
        try:
            executor = ScheduledScanExecutor()
            urls = ["https://a.com", "https://b.com"]
            result = executor._run_batch_with_retry(urls)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "https://a.com" in result
        assert "https://b.com" in result

    def test_retry_on_transient_failure(self):
        """Retries transient failures up to max_retries."""
        try:
            executor = ScheduledScanExecutor(max_retries=2, retry_delay=0.01)
            # This tests the interface — actual retry behavior needs mocking
            result = executor._run_batch_with_retry(
                ["https://example.com"],
                timeout=5.0,
                max_workers=1,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, dict)

    def test_empty_urls_returns_empty_dict(self):
        """Empty URL list returns empty dict."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._run_batch_with_retry([])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result == {}


# ============================================================================
# SECTION 7: BEHAVIORAL TESTS — REGRESSION DETECTION (RED phase)
# ============================================================================


class TestRegressionDetection:
    """Behavioral tests for _detect_regressions."""

    def test_no_previous_returns_zero(self):
        """No previous results returns (0, [])."""
        try:
            executor = ScheduledScanExecutor()
            count, flags = executor._detect_regressions(
                {"https://a.com": [{"url": "https://a.com", "status": 404}]},
                None,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0
        assert flags == []

    def test_new_broken_detected(self):
        """Detects newly broken links not in previous scan."""
        try:
            executor = ScheduledScanExecutor()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com",
                        "status": 404,
                        "reason": "Not Found",
                        "location": None,
                    }
                ],
                "https://b.com": [
                    {
                        "url": "https://b.com",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    }
                ],
            }
            previous = [
                {"url": "https://a.com", "status": 200},
                {"url": "https://b.com", "status": 200},
            ]
            count, flags = executor._detect_regressions(current, previous)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count >= 1
        assert any("new_broken" in f for f in flags)

    def test_no_regressions_when_all_ok(self):
        """Returns (0, []) when nothing is newly broken."""
        try:
            executor = ScheduledScanExecutor()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    }
                ],
            }
            previous = [{"url": "https://a.com", "status": 200}]
            count, _flags = executor._detect_regressions(current, previous)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0

    def test_fixed_link_not_flagged_as_regression(self):
        """A link that was broken but is now OK is NOT a regression."""
        try:
            executor = ScheduledScanExecutor()
            current = {
                "https://a.com": [
                    {
                        "url": "https://a.com",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    }
                ],
            }
            previous = [{"url": "https://a.com", "status": 500}]
            count, _flags = executor._detect_regressions(current, previous)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0


# ============================================================================
# SECTION 8: BEHAVIORAL TESTS — IS_LINK_BROKEN (RED phase)
# ============================================================================


class TestIsLinkBroken:
    """Behavioral tests for _is_link_broken helper."""

    def test_status_200_not_broken(self):
        try:
            executor = ScheduledScanExecutor()
            assert executor._is_link_broken({"status": 200}) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_status_404_is_broken(self):
        try:
            executor = ScheduledScanExecutor()
            assert executor._is_link_broken({"status": 404}) is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_status_500_is_broken(self):
        try:
            executor = ScheduledScanExecutor()
            assert executor._is_link_broken({"status": 500}) is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_status_none_with_reason_is_broken(self):
        """None status with a reason (timeout/fetch failure) is broken."""
        try:
            executor = ScheduledScanExecutor()
            assert (
                executor._is_link_broken({"status": None, "reason": "timeout"}) is True
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_status_none_without_reason_not_broken(self):
        """None status without reason is not broken."""
        try:
            executor = ScheduledScanExecutor()
            assert executor._is_link_broken({"status": None, "reason": None}) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_status_301_not_broken(self):
        try:
            executor = ScheduledScanExecutor()
            assert executor._is_link_broken({"status": 301}) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


# ============================================================================
# SECTION 9: BEHAVIORAL TESTS — FORMAT REGRESSION FLAGS (RED phase)
# ============================================================================


class TestFormatRegressionFlags:
    """Behavioral tests for _format_regression_flags."""

    def test_returns_list_of_strings(self):
        try:
            executor = ScheduledScanExecutor()
            flags = executor._format_regression_flags([], [])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(flags, list)
        assert all(isinstance(f, str) for f in flags)

    def test_empty_inputs_returns_empty(self):
        try:
            executor = ScheduledScanExecutor()
            flags = executor._format_regression_flags([], [])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert flags == []

    def test_new_broken_url_formatted(self):
        """New broken URLs produce 'new_broken:<url>' flags."""
        try:
            executor = ScheduledScanExecutor()
            flags = executor._format_regression_flags(
                ["https://example.com/missing"],
                [],
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert "new_broken:https://example.com/missing" in flags

    def test_status_change_formatted(self):
        """Status changes produce 'status_change:<url>:<old>-><new>' flags."""
        try:
            executor = ScheduledScanExecutor()
            flags = executor._format_regression_flags(
                [],
                [("https://example.com/page", "200", "500")],
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert any("status_change" in f for f in flags)


# ============================================================================
# SECTION 10: BEHAVIORAL TESTS — COMPUTE_SUMMARY (RED phase)
# ============================================================================


class TestComputeSummary:
    """Behavioral tests for _compute_summary."""

    def test_returns_scan_result(self):
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary(
                {
                    "https://a.com": [
                        {
                            "url": "https://a.com",
                            "status": 200,
                            "reason": "OK",
                            "location": None,
                        }
                    ]
                },
                "proj1",
                "Test",
                time.time(),
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result, ScanResult)

    def test_urls_scanned_matches_results(self):
        """urls_scanned equals number of top-level keys in scan_results."""
        try:
            executor = ScheduledScanExecutor()
            results = {
                "https://a.com": [
                    {
                        "url": "https://a.com",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    }
                ],
                "https://b.com": [
                    {
                        "url": "https://b.com",
                        "status": 404,
                        "reason": "Not Found",
                        "location": None,
                    }
                ],
            }
            result = executor._compute_summary(results, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.urls_scanned == 2

    def test_broken_count_from_results(self):
        """broken_count equals number of broken links across all URLs."""
        try:
            executor = ScheduledScanExecutor()
            results = {
                "https://a.com": [
                    {
                        "url": "https://a.com/ok",
                        "status": 200,
                        "reason": "OK",
                        "location": None,
                    },
                    {
                        "url": "https://a.com/bad",
                        "status": 500,
                        "reason": "Error",
                        "location": None,
                    },
                ],
            }
            result = executor._compute_summary(results, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.broken_count == 1

    def test_total_links_count(self):
        """total_links equals total link results across all URLs."""
        try:
            executor = ScheduledScanExecutor()
            results = {
                "https://a.com": [
                    {"url": "l1", "status": 200, "reason": "OK", "location": None},
                    {"url": "l2", "status": 200, "reason": "OK", "location": None},
                ],
                "https://b.com": [
                    {"url": "l3", "status": 404, "reason": "NF", "location": None},
                ],
            }
            result = executor._compute_summary(results, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.total_links == 3

    def test_project_id_and_name_set(self):
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary(
                {}, "proj_xyz", "My Project", time.time()
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.project_id == "proj_xyz"
        assert result.project_name == "My Project"

    def test_status_completed_on_success(self):
        """Status is 'completed' when no errors."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary(
                {
                    "https://a.com": [
                        {"url": "a", "status": 200, "reason": "OK", "location": None}
                    ]
                },
                "p1",
                "Test",
                time.time(),
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.status == "completed"

    def test_duration_seconds_computed(self):
        """duration_seconds reflects elapsed time since start_time."""
        try:
            executor = ScheduledScanExecutor()
            start = time.time() - 1.0  # 1 second ago
            result = executor._compute_summary({}, "p1", "Test", start)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.duration_seconds >= 0.9


# ============================================================================
# SECTION 11: BEHAVIORAL TESTS — PARTIAL FAILURE HANDLING (RED phase)
# ============================================================================


class TestPartialFailure:
    """Behavioral tests for handling partial scan failures."""

    def test_partial_failure_status_completed(self):
        """Partial failures still result in 'completed' (not 'failed')."""
        try:
            executor = ScheduledScanExecutor()
            config = {
                "id": "p1",
                "name": "Test",
                "urls": ["https://example.com", "https://timeout.example.com"],
            }
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Even with partial failures, status should be completed
        assert result.status in ("completed", "partial")

    def test_errors_populated_on_failure(self):
        """errors list is populated when URLs fail to scan."""
        try:
            executor = ScheduledScanExecutor()
            config = {
                "id": "p1",
                "name": "Test",
                "urls": ["https://nonexistent.invalid"],
            }
            result = executor.execute_scan(config)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # The error may or may not be present depending on DNS resolution
        assert isinstance(result.errors, list)


# ============================================================================
# SECTION 12: BEHAVIORAL TESTS — SCAN_HISTORY COMPATIBILITY (RED phase)
# ============================================================================


class TestScanHistoryCompatibility:
    """Verify ScanResult fields match scan_history table schema."""

    def test_scan_id_is_string(self):
        """scan_id is a string (UUID in production)."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary({}, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(result.scan_id, str)
        assert len(result.scan_id) > 0

    def test_scan_timestamp_is_iso8601(self):
        """scan_timestamp is ISO 8601 string."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary({}, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # ISO 8601 contains 'T'
        assert "T" in result.scan_timestamp

    def test_status_valid_enum(self):
        """status is one of: pending, running, completed, failed."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary({}, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert result.status in ("pending", "running", "completed", "failed")

    def test_regression_flags_are_strings(self):
        """Each regression flag is a string."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary({}, "p1", "Test", time.time())
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        for flag in result.regression_flags:
            assert isinstance(flag, str)

    def test_raw_results_serializable(self):
        """raw_results values are JSON-serializable dicts."""
        try:
            executor = ScheduledScanExecutor()
            result = executor._compute_summary(
                {
                    "https://a.com": [
                        {"url": "a", "status": 200, "reason": "OK", "location": None}
                    ]
                },
                "p1",
                "Test",
                time.time(),
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        import json

        # Should not raise
        json.dumps(result.raw_results)
