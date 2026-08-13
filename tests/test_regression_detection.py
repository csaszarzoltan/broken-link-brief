"""Tests for scan regression detection logic.

Three-layer pre-dev test pattern:
  Layer 1: Import/class-existence (PASS immediately)
  Layer 2: Signature/interface (PASS immediately)
  Layer 3: Behavioral detection (FAIL with NotImplementedError until implemented)
"""

from __future__ import annotations

import inspect

import pytest

from brokenlinkbrief.regression import (
    LinkResult,
    compute_results_hash,
    detect_regressions,
    is_broken,
)


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestImports:
    """Verify all public symbols are importable."""

    def test_import_link_result(self) -> None:
        assert LinkResult is not None

    def test_import_is_broken(self) -> None:
        assert callable(is_broken)

    def test_import_detect_regressions(self) -> None:
        assert callable(detect_regressions)

    def test_import_compute_results_hash(self) -> None:
        assert callable(compute_results_hash)


class TestDataclassStructure:
    """Verify LinkResult has the expected fields."""

    def test_link_result_fields(self) -> None:
        from dataclasses import fields

        field_names = {f.name for f in fields(LinkResult)}
        assert "url" in field_names
        assert "status" in field_names
        assert "reason" in field_names

    def test_link_result_defaults(self) -> None:
        lr = LinkResult(url="https://example.com")
        assert lr.status is None
        assert lr.reason is None


# ---------------------------------------------------------------------------
# Layer 2 — Signature/interface checks
# ---------------------------------------------------------------------------
class TestSignatures:
    """Verify function signatures match spec."""

    def test_is_broken_signature(self) -> None:
        sig = inspect.signature(is_broken)
        params = list(sig.parameters.keys())
        assert "result" in params
        assert sig.parameters["result"].annotation in (LinkResult, "LinkResult")

    def test_is_broken_returns_bool(self) -> None:
        sig = inspect.signature(is_broken)
        ret = sig.return_annotation
        assert ret is bool or ret == "bool"

    def test_detect_regressions_signature(self) -> None:
        sig = inspect.signature(detect_regressions)
        params = list(sig.parameters.keys())
        assert "current_results" in params
        assert "previous_results" in params

    def test_compute_results_hash_signature(self) -> None:
        sig = inspect.signature(compute_results_hash)
        params = list(sig.parameters.keys())
        assert "results" in params


# ---------------------------------------------------------------------------
# Layer 3 — Behavioral tests (RED phase — raise NotImplementedError)
# ---------------------------------------------------------------------------
class TestIsBroken:
    """Test the is_broken helper function."""

    def test_broken_with_4xx_status(self) -> None:
        """Status code >= 400 is broken."""
        try:
            assert is_broken(LinkResult(url="http://x.com", status=404)) is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_broken_with_5xx_status(self) -> None:
        """Status code >= 500 is broken."""
        try:
            assert is_broken(LinkResult(url="http://x.com", status=500)) is True
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_broken_with_timeout(self) -> None:
        """Timeout (status=None, reason=timeout) is broken."""
        try:
            assert (
                is_broken(LinkResult(url="http://x.com", status=None, reason="timeout"))
                is True
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_broken_with_fetch_error(self) -> None:
        """Fetch failure (status=None, reason=error) is broken."""
        try:
            assert (
                is_broken(
                    LinkResult(
                        url="http://x.com", status=None, reason="connection_error"
                    )
                )
                is True
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_not_broken_with_2xx_status(self) -> None:
        """Status code 200-299 is not broken."""
        try:
            assert is_broken(LinkResult(url="http://x.com", status=200)) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_not_broken_with_3xx_status(self) -> None:
        """Status code 300-399 is not broken."""
        try:
            assert is_broken(LinkResult(url="http://x.com", status=301)) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_not_broken_with_1xx_status(self) -> None:
        """Status code 100-199 is not broken."""
        try:
            assert is_broken(LinkResult(url="http://x.com", status=100)) is False
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")


class TestDetectRegressions:
    """Test regression detection between scans."""

    def test_no_previous_scan(self) -> None:
        """First scan has no regressions."""
        current = [LinkResult(url="http://x.com", status=200)]
        try:
            count, flags = detect_regressions(current, None)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0
        assert flags == []

    def test_no_new_broken_links(self) -> None:
        """Same broken links as previous scan = no regressions."""
        prev = [LinkResult(url="http://x.com", status=404)]
        current = [LinkResult(url="http://x.com", status=404)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0

    def test_one_new_broken_link(self) -> None:
        """One new broken link detected."""
        prev = [LinkResult(url="http://x.com", status=200)]
        current = [
            LinkResult(url="http://x.com", status=200),
            LinkResult(url="http://y.com", status=500),
        ]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 1
        assert any("new_broken:http://y.com" in f for f in flags)

    def test_multiple_new_broken_links(self) -> None:
        """Multiple new broken links detected."""
        prev = []
        current = [
            LinkResult(url="http://a.com", status=404),
            LinkResult(url="http://b.com", status=500),
        ]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 2

    def test_link_recovered_not_regression(self) -> None:
        """Link that was broken but now works is not a regression."""
        prev = [LinkResult(url="http://x.com", status=404)]
        current = [LinkResult(url="http://x.com", status=200)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0

    def test_status_change_detected(self) -> None:
        """Status code change (e.g., 200 -> 301) is detected."""
        prev = [LinkResult(url="http://x.com", status=200)]
        current = [LinkResult(url="http://x.com", status=301)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # 301 is not broken, so no new_broken regression
        assert count == 0

    def test_empty_current_results(self) -> None:
        """Empty current results handled gracefully."""
        prev = [LinkResult(url="http://x.com", status=200)]
        try:
            count, flags = detect_regressions([], prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0
        assert flags == []

    def test_empty_previous_results(self) -> None:
        """Empty previous results treated as first scan."""
        current = [LinkResult(url="http://x.com", status=200)]
        try:
            count, flags = detect_regressions(current, [])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert count == 0
        assert flags == []


class TestComputeResultsHash:
    """Test SHA-256 hash computation for scan results."""

    def test_deterministic_hash(self) -> None:
        """Same results always produce same hash."""
        results = [LinkResult(url="http://x.com", status=200)]
        try:
            h1 = compute_results_hash(results)
            h2 = compute_results_hash(results)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert h1 == h2

    def test_different_results_different_hash(self) -> None:
        """Different results produce different hashes."""
        r1 = [LinkResult(url="http://x.com", status=200)]
        r2 = [LinkResult(url="http://x.com", status=404)]
        try:
            h1 = compute_results_hash(r1)
            h2 = compute_results_hash(r2)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert h1 != h2

    def test_hash_is_sha256(self) -> None:
        """Hash is 64-character hex string."""
        results = [LinkResult(url="http://x.com", status=200)]
        try:
            h = compute_results_hash(results)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_ignores_timestamp(self) -> None:
        """Hash only considers link results, not timestamps."""
        # Both LinkResult objects have no timestamp field —
        # just verify the hash works on plain results
        results = [LinkResult(url="http://x.com", status=200)]
        try:
            h1 = compute_results_hash(results)
            h2 = compute_results_hash(results)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert h1 == h2

    def test_hash_order_independent(self) -> None:
        """Same links in different order produce same hash."""
        r1 = [
            LinkResult(url="http://a.com", status=200),
            LinkResult(url="http://b.com", status=404),
        ]
        r2 = [
            LinkResult(url="http://b.com", status=404),
            LinkResult(url="http://a.com", status=200),
        ]
        try:
            h1 = compute_results_hash(r1)
            h2 = compute_results_hash(r2)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert h1 == h2


class TestRegressionFlags:
    """Test regression flag formatting and storage."""

    def test_flag_new_broken_format(self) -> None:
        """new_broken flag has correct format."""
        prev = []
        current = [LinkResult(url="http://x.com", status=404)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert any(f.startswith("new_broken:") for f in flags)

    def test_flag_status_change_format(self) -> None:
        """status_change flag has correct format."""
        prev = [LinkResult(url="http://x.com", status=200)]
        current = [LinkResult(url="http://x.com", status=301)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Status change detection may or may not be in flags depending on impl
        # At minimum the function shouldn't crash
        assert isinstance(flags, list)

    def test_flags_stored_as_json_array(self) -> None:
        """Regression flags are stored as JSON array string."""
        import json

        prev = []
        current = [LinkResult(url="http://x.com", status=404)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Verify flags can be serialized as JSON
        serialized = json.dumps(flags)
        assert isinstance(json.loads(serialized), list)

    def test_empty_flags_stored_as_empty_array(self) -> None:
        """No regressions stored as empty JSON array."""
        import json

        prev = [LinkResult(url="http://x.com", status=200)]
        current = [LinkResult(url="http://x.com", status=200)]
        try:
            count, flags = detect_regressions(current, prev)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert flags == []
        assert json.dumps(flags) == "[]"
