"""Pre-development interface/behavior tests for BrokenLinkBrief batch scanning.

State at authoring time (pre-tester, t_223c730d):
- ``validate_scan_url`` is stubbed in ``package.py`` to raise ``NotImplementedError``.
- ``scan_batch`` is stubbed in ``package.py`` to raise ``NotImplementedError``.
- ``_Handler.do_POST`` for ``/scan-batch`` is stubbed to raise ``NotImplementedError``.
- Therefore ALL behavioral tests are expected to FAIL against the stubs and
  PASS only after the developer implements the batch scanning feature.
"""

from __future__ import annotations

import inspect

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# Interface tests — these MUST pass immediately.
# Stubs raise NotImplementedError, so we verify existence and signature
# without invoking the actual implementation.
# ---------------------------------------------------------------------------


def test_interface_validate_scan_url_importable() -> None:
    """validate_scan_url must be importable from the package module."""
    from brokenlinkbrief.package import validate_scan_url

    assert callable(validate_scan_url)


def test_interface_validate_scan_url_signature() -> None:
    """validate_scan_url(url: str) -> str | None"""
    from brokenlinkbrief.package import validate_scan_url

    sig = inspect.signature(validate_scan_url)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "url"
    assert str(sig.return_annotation) == "str | None"


def test_interface_scan_batch_importable() -> None:
    """scan_batch must be importable from the package module."""
    from brokenlinkbrief.package import scan_batch

    assert callable(scan_batch)


def test_interface_scan_batch_signature() -> None:
    """scan_batch(urls: list[str], timeout: float, max_workers: int) -> dict"""
    from brokenlinkbrief.package import scan_batch

    sig = inspect.signature(scan_batch)
    params = list(sig.parameters.values())
    assert len(params) == 3
    assert params[0].name == "urls"
    assert params[0].default is inspect.Parameter.empty
    assert params[1].name == "timeout"
    assert params[1].default == 10.0
    assert params[2].name == "max_workers"
    assert params[2].default == 5


def test_interface_scan_handler_exposes_do_post() -> None:
    """_Handler must have a do_POST method (needed for /scan-batch)."""
    assert callable(getattr(_Handler, "do_POST", None))


# ---------------------------------------------------------------------------
# Behavioral tests — encode the batch scanning contract.
# These will FAIL against the NotImplementedError stubs and PASS only after
# the developer implements validate_scan_url, scan_batch, and the endpoint.
# ---------------------------------------------------------------------------


# --- validate_scan_url behavioral tests ---


def test_behavior_validate_scan_url_allows_public_http() -> None:
    """Public HTTP URLs should be allowed."""
    from brokenlinkbrief.package import validate_scan_url

    assert validate_scan_url("http://example.com") is None


def test_behavior_validate_scan_url_allows_public_https() -> None:
    """Public HTTPS URLs should be allowed."""
    from brokenlinkbrief.package import validate_scan_url

    assert validate_scan_url("https://example.com") is None


def test_behavior_validate_scan_url_blocks_loopback() -> None:
    """Loopback addresses must be blocked."""
    from brokenlinkbrief.package import validate_scan_url

    result = validate_scan_url("http://127.0.0.1")
    assert result is not None


def test_behavior_validate_scan_url_blocks_ipv6_loopback() -> None:
    """IPv6 loopback must be blocked."""
    from brokenlinkbrief.package import validate_scan_url

    result = validate_scan_url("http://[::1]")
    assert result is not None


def test_behavior_validate_scan_url_blocks_private_ip() -> None:
    """Private IPs (10.x, 172.16-31.x, 192.168.x) must be blocked."""
    from brokenlinkbrief.package import validate_scan_url

    result = validate_scan_url("http://10.0.0.1")
    assert result is not None


def test_behavior_validate_scan_url_blocks_metadata_endpoint() -> None:
    """Cloud metadata endpoints must be blocked."""
    from brokenlinkbrief.package import validate_scan_url

    result = validate_scan_url("http://169.254.169.254/metadata")
    assert result is not None


def test_behavior_validate_scan_url_blocks_invalid_url() -> None:
    """Invalid / unparseable URLs must be blocked."""
    from brokenlinkbrief.package import validate_scan_url

    result = validate_scan_url("not-a-url")
    assert result is not None


# --- scan_batch behavioral tests ---


def test_behavior_scan_batch_returns_dict_keyed_by_url() -> None:
    """scan_batch must return a dict keyed by input URL."""
    from brokenlinkbrief.package import scan_batch

    result = scan_batch(["https://a.example.com", "https://b.example.com"])
    assert isinstance(result, dict)
    assert "https://a.example.com" in result
    assert "https://b.example.com" in result


def test_behavior_scan_batch_values_are_link_result_lists() -> None:
    """Each value must be a list of LinkResult objects."""
    from brokenlinkbrief.package import scan_batch

    result = scan_batch(["https://a.example.com"])
    assert isinstance(result["https://a.example.com"], list)
    assert isinstance(result["https://a.example.com"][0], LinkResult)


def test_behavior_scan_batch_handles_per_url_exceptions() -> None:
    """Per-URL exceptions must be captured, not propagated."""
    from brokenlinkbrief.package import scan_batch

    result = scan_batch(["https://a.example.com", "https://b.example.com"])
    # At least one URL should have a result (even if it's an error)
    assert len(result) == 2


def test_behavior_scan_batch_respects_max_workers() -> None:
    """max_workers parameter must be accepted and respected."""
    from brokenlinkbrief.package import scan_batch

    result = scan_batch(["https://a.example.com"], max_workers=1)
    assert isinstance(result, dict)


# --- POST /scan-batch endpoint behavioral tests ---


def _start_server(monkeypatch):  # noqa: D401
    """Helper: start a temp server with monkeypatched scan functions."""
    import socket
    import threading
    from http.server import HTTPServer

    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")

    def fake_scan_page(url: str, timeout: float = 10.0):
        return [LinkResult(url=url, status=200, reason="OK", location=None)]

    def fake_scan_batch(urls, timeout=10.0, max_workers=5):
        return {url: fake_scan_page(url, timeout) for url in urls}

    def fake_validate(url: str):
        return None

    monkeypatch.setattr("brokenlinkbrief.app.scan_page", fake_scan_page)
    monkeypatch.setattr("brokenlinkbrief.package.scan_batch", fake_scan_batch)
    monkeypatch.setattr("brokenlinkbrief.package.validate_scan_url", fake_validate)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_behavior_batch_endpoint_accepts_post_with_urls() -> None:
    """POST /scan-batch with a JSON body containing urls list must be accepted."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        parsed = json.loads(data)
        assert "results" in parsed
        assert "summary" in parsed
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_returns_per_url_results_and_summary() -> None:
    """Response must include per-URL results and an aggregated summary."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://a.example.com", "https://b.example.com"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        parsed = json.loads(data)
        assert "https://a.example.com" in parsed["results"]
        assert "https://b.example.com" in parsed["results"]
        summary = parsed["summary"]
        assert summary["total_urls"] == 2
        assert "latency_seconds" in summary
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_requires_auth_token() -> None:
    """When BROKENLINKBRIEF_SCAN_TOKEN is set, missing/invalid token must return 401."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"]})
        conn.request(
            "POST",
            "/scan-batch",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 401
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_rejects_empty_urls() -> None:
    """Empty or missing urls list must return 400."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": []})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 400
        parsed = json.loads(data)
        assert "detail" in parsed
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_rejects_duplicate_urls() -> None:
    """Duplicate URLs in the request must return 400."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com", "https://example.com"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 400
        parsed = json.loads(data)
        assert "duplicate" in parsed["detail"].lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_rejects_ssrf_urls() -> None:
    """URLs blocked by SSRF policy must return 400."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)

    # Override validate_scan_url to actually block loopback
    def blocking_validate(url: str):
        if "127.0.0.1" in url:
            return "blocked host"
        return None

    monkeypatch.setattr("brokenlinkbrief.package.validate_scan_url", blocking_validate)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["http://127.0.0.1"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 400
        parsed = json.loads(data)
        assert "SSRF" in parsed["detail"] or "ssrf" in parsed["detail"].lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_caps_concurrency_at_20() -> None:
    """concurrency parameter must be capped at 20, even if caller requests higher."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"], "concurrency": 999})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        assert resp.status == 200
        resp.read()
        conn.close()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_rejects_over_50_urls() -> None:
    """More than 50 URLs must return 400."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        urls = [f"https://example{i}.com" for i in range(51)]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": urls})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 400
        parsed = json.loads(data)
        assert "50" in parsed["detail"] or "max" in parsed["detail"].lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_json_format_default() -> None:
    """Default format must be JSON with results and summary."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "application/json"
        parsed = json.loads(data)
        assert "results" in parsed
        assert "summary" in parsed
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_csv_format() -> None:
    """format=csv must return CSV content type."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"], "format": "csv"})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        _data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert "csv" in resp.getheader("Content-Type", "").lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_markdown_format() -> None:
    """format=markdown must return markdown content type."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"], "format": "markdown"})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        _data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert "markdown" in resp.getheader("Content-Type", "").lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_jsonl_format() -> None:
    """format=jsonl must return JSONL content type."""
    import http.client
    import json

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"], "format": "jsonl"})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        _data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert "jsonlines" in resp.getheader("Content-Type", "").lower()
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_batch_endpoint_jsonl_logging_records_batch() -> None:
    """Batch scan must be logged via JSONL with batch_id field."""
    import http.client
    import json
    import os
    import tempfile

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    fd, log_path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    monkeypatch.setenv("BROKENLINKBRIEF_LOG_FILE", log_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"urls": ["https://example.com"]})
        conn.request(
            "POST",
            "/scan-batch?token=secret",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 200
        # Verify log file has batch entry with batch_id
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) >= 1
        log_entry = json.loads(lines[-1])
        assert "batch_id" in log_entry
        assert "url_count" in log_entry
        assert "total_broken" in log_entry
        assert "latency_seconds" in log_entry
    finally:
        server.shutdown()
        monkeypatch.undo()
        os.unlink(log_path)
