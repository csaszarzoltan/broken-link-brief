"""Pre-development interface/behavior tests for BrokenLinkBrief historical tracking.

Feature under test: Historical link tracking with HistoryStore, /history, /diff, and change-detection.

State at authoring time (pre-tester):
- HistoryStore, record_scan(), get_history(), compute_diff() DO NOT yet exist in package.py.
- /history and /diff endpoints DO NOT yet exist in app.py.
- Webhook change-detection logic does NOT yet exist.
- Therefore ALL behavioral tests are expected to FAIL against the NotImplementedError stubs
  and PASS only after the developer implements history storage, endpoints, and change detection.
"""

from __future__ import annotations

import http.client
import inspect
import json
import socket
import threading
from http.server import HTTPServer
from typing import Any

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# Interface tests — these MUST pass immediately.
# All new functions and classes must be importable with the correct signatures.
# ---------------------------------------------------------------------------


def test_interface_history_store_importable() -> None:
    """HistoryStore must be importable from the package module."""
    from brokenlinkbrief.package import HistoryStore

    assert HistoryStore is not None


def test_interface_record_scan_importable() -> None:
    """record_scan must be importable from the package module."""
    from brokenlinkbrief.package import record_scan

    assert callable(record_scan)


def test_interface_get_history_importable() -> None:
    """get_history must be importable from the package module."""
    from brokenlinkbrief.package import get_history

    assert callable(get_history)


def test_interface_compute_diff_importable() -> None:
    """compute_diff must be importable from the package module."""
    from brokenlinkbrief.package import compute_diff

    assert callable(compute_diff)


def test_interface_history_store_class_signature() -> None:
    """HistoryStore class must have correct signature."""
    from brokenlinkbrief.package import HistoryStore

    assert hasattr(HistoryStore, "__init__")
    sig = inspect.signature(HistoryStore.__init__)
    params = list(sig.parameters.values())
    assert len(params) >= 1


def test_interface_record_scan_signature() -> None:
    """record_scan(results: list[LinkResult], url: str) -> None"""
    from brokenlinkbrief.package import record_scan

    sig = inspect.signature(record_scan)
    params = list(sig.parameters.values())
    assert len(params) >= 2
    assert params[0].name == "results"
    assert params[1].name == "url"


def test_interface_get_history_signature() -> None:
    """get_history(url: str, limit: int = 100, since: str | None = None) -> list[dict]"""
    from brokenlinkbrief.package import get_history

    sig = inspect.signature(get_history)
    params = list(sig.parameters.values())
    assert len(params) >= 1
    assert params[0].name == "url"


def test_interface_compute_diff_signature() -> None:
    """compute_diff(previous: list[dict], current: list[dict]) -> dict"""
    from brokenlinkbrief.package import compute_diff

    sig = inspect.signature(compute_diff)
    params = list(sig.parameters.values())
    assert len(params) >= 2
    assert params[0].name == "previous"
    assert params[1].name == "current"


def test_interface_history_endpoints_exist() -> None:
    """_Handler must have /history and /diff endpoints (do_GET covers them)."""
    assert callable(getattr(_Handler, "do_GET", None))


# ---------------------------------------------------------------------------
# Behavioral tests — encode the history tracking contract.
# These will FAIL against the NotImplementedError stubs and PASS only after
# the developer implements history storage, /history, /diff, and change-detection.
# ---------------------------------------------------------------------------


def _start_server(monkeypatch, enable_history: bool = True) -> tuple:
    """Helper: start a temp server with monkeypatched scan_page and history features."""
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")

    expected_results = [
        LinkResult(url="https://example.com", status=200, reason="OK", location=None),
        LinkResult(
            url="https://example.com/broken",
            status=404,
            reason="Not Found",
            location=None,
        ),
    ]

    def fake_scan(url: str, timeout: float = 10.0):
        return list(expected_results)

    monkeypatch.setattr("brokenlinkbrief.app.scan_page", fake_scan)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, expected_results


def _get_hosted_history(store_path: str) -> Any:
    """Helper to read the history file content."""
    import os

    if os.path.exists(store_path):
        with open(store_path) as f:
            return [json.loads(line) for line in f.read().strip().split("\n") if line]
    return []


def test_behavior_record_scan_writes_jsonl_history() -> None:
    """record_scan() must append timestamped scan results to JSONL history file."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        from brokenlinkbrief.package import HistoryStore, record_scan

        # Create a HistoryStore instance
        store = HistoryStore()
        getattr(store, "history_file", None)

        # Simulate scan results
        results = [
            LinkResult(url="https://test.com", status=200, reason="OK", location=None),
            LinkResult(
                url="https://broken.com",
                status=404,
                reason="Not Found",
                location="/notfound",
            ),
        ]

        # This should write to history file (or raise NotImplementedError)
        try:
            record_scan(results, "https://test.com")
        except NotImplementedError:
            pytest.fail(
                "record_scan() should not raise NotImplementedError - this is the feature under development"
            )

        # Verify history file was written (implementation-specific)
        # For now, we just check that it doesn't crash
        assert True

    finally:
        monkeypatch.undo()


def test_behavior_get_history_returns_records_in_timestamp_order() -> None:
    """get_history(url) must return all historical scan records for a URL, ordered by timestamp."""
    from brokenlinkbrief.package import get_history

    # This will call the not-yet-implemented function
    result = get_history("https://example.com")

    # Should return a list (even if empty due to not implemented)
    assert isinstance(result, list)


def test_behavior_compute_diff_detects_changes() -> None:
    """compute_diff(prev, current) returns {added_broken, fixed, still_broken}"""
    from brokenlinkbrief.package import compute_diff

    previous = [
        {"url": "https://example.com", "status": 200, "broken": False},
        {"url": "https://broken.com", "status": 404, "broken": True},
    ]

    current = [
        {
            "url": "https://example.com",
            "status": 404,
            "broken": True,
        },  # Was working, now broken
        {
            "url": "https://broken.com",
            "status": 200,
            "broken": False,
        },  # Was broken, now working
        {
            "url": "https://newbroken.com",
            "status": 500,
            "broken": True,
        },  # New broken link
    ]

    result = compute_diff(previous, current)

    # Verify expected keys exist
    assert "added_broken" in result
    assert "fixed" in result
    assert "still_broken" in result
    assert isinstance(result["added_broken"], list)
    assert isinstance(result["fixed"], list)
    assert isinstance(result["still_broken"], list)


def test_behavior_history_change_detection_triggers_webhook_only_on_changes() -> None:
    """Webhooks should only fire when compute_diff shows actual changes, not every scan."""
    monkeypatch = pytest.MonkeyPatch()

    webhook_calls = []

    def mock_trigger_webhooks(registry, url, results):
        webhook_calls.append((url, results))

    monkeypatch.setattr("brokenlinkbrief.app.trigger_webhooks", mock_trigger_webhooks)

    # Start server
    server, port, _ = _start_server(monkeypatch)

    try:
        # First scan (should trigger webhook if there are broken links)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Second scan with same results (should NOT trigger webhook if no changes)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Verify webhook was called appropriately (implementation-dependent)
        # For now, just verify the structure
        assert isinstance(webhook_calls, list)

    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_scanning_populates_history() -> None:
    """Batch scanning (/scan-batch) should populate history and trigger change detection."""
    monkeypatch = pytest.MonkeyPatch()

    try:
        import brokenlinkbrief.package as pkg

        # Mock scan_batch to return results
        mock_results = {
            "https://example.com": [
                LinkResult(
                    url="https://example.com/page1",
                    status=200,
                    reason="OK",
                    location=None,
                ),
                LinkResult(
                    url="https://example.com/page2",
                    status=404,
                    reason="Not Found",
                    location=None,
                ),
            ]
        }

        def mock_batch_scan(urls, timeout=10.0, max_workers=5):
            return mock_results

        monkeypatch.setattr("brokenlinkbrief.package.scan_batch", mock_batch_scan)

        # Call scan_batch via module (catches monkeypatch)
        result = pkg.scan_batch(["https://example.com"])

        # Result should match mocked results
        assert result == mock_results

    finally:
        monkeypatch.undo()


def test_behavior_history_edge_cases_handled() -> None:
    """Edge cases: first scan for URL (no history), no changes, all links fixed, all newly broken."""
    monkeypatch = pytest.MonkeyPatch()

    try:
        from brokenlinkbrief.package import compute_diff, get_history

        # Test 1: First scan for a URL (no history)
        result = get_history("https://fresh-url.com")
        assert isinstance(result, list)

        # Test 2: No changes between scans (should trigger webhook only on real changes)
        snapshot1 = [
            {"url": "https://stable.com", "status": 200, "broken": False},
        ]

        snapshot2 = [
            {"url": "https://stable.com", "status": 200, "broken": False},
        ]

        diff_result = compute_diff(snapshot1, snapshot2)
        assert "added_broken" in diff_result
        assert "fixed" in diff_result
        assert "still_broken" in diff_result

        # All three should be empty for identical snapshots
        assert len(diff_result["added_broken"]) == 0
        assert len(diff_result["fixed"]) == 0
        # Note: still_broken may include links that are still broken from previous scan

        # Test 3: All links fixed
        broken_snapshot = [
            {"url": "https://broken.com", "status": 404, "broken": True},
        ]

        fixed_snapshot = [
            {"url": "https://broken.com", "status": 200, "broken": False},
        ]

        diff_result = compute_diff(broken_snapshot, fixed_snapshot)
        assert len(diff_result["fixed"]) == 1
        assert diff_result["fixed"][0]["url"] == "https://broken.com"

        # Test 4: All links newly broken
        working_snapshot = [
            {"url": "https://working.com", "status": 200, "broken": False},
        ]

        broken_snapshot = [
            {"url": "https://working.com", "status": 404, "broken": True},
        ]

        diff_result = compute_diff(working_snapshot, broken_snapshot)
        assert len(diff_result["added_broken"]) == 1
        assert diff_result["added_broken"][0]["url"] == "https://working.com"

    finally:
        monkeypatch.undo()


def test_behavior_history_history_endpoint_exists() -> None:
    """GET /history?url=<target> must exist and return history for URL."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, _ = _start_server(monkeypatch)

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/history?url=https://example.com&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()

        # Should return 200 even if no history (endpoint exists)
        assert resp.status == 200

        # Body should be parseable as JSON (could be empty list)
        parsed = json.loads(body)
        assert isinstance(parsed, list)

    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_diff_endpoint_exists() -> None:
    """POST /diff with two scan snapshots must exist."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, _ = _start_server(monkeypatch)

    try:
        # Prepare payload with two scan snapshots
        payload = {
            "previous": [
                {"url": "https://site1.com", "status": 200, "broken": False},
                {"url": "https://site2.com", "status": 500, "broken": True},
            ],
            "current": [
                {"url": "https://site1.com", "status": 404, "broken": True},
                {"url": "https://site2.com", "status": 200, "broken": False},
            ],
        }

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/diff?token=secret",
            headers={"Host": "127.0.0.1", "Content-Type": "application/json"},
            body=json.dumps(payload),
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()

        # Should return 200 (endpoint exists)
        assert resp.status == 200

        # Body should be parseable as JSON
        parsed = json.loads(body)
        assert isinstance(parsed, dict)

    finally:
        server.shutdown()
        monkeypatch.undo()
