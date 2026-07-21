"""Pre-development interface/behavior tests for BrokenLinkBrief JSONL export.

Feature under test: ``GET /scan?url=<target>&format=jsonl`` must return
``200`` with ``Content-Type: application/x-jsonlines`` and a body that is
one valid JSON object per line, each containing the expected scan result
fields (url, status, reason, location).

State at authoring time (pre-tester, t_aa1183e2):
- ``render_jsonl`` does NOT yet exist in ``apps/brokenlinkbrief/package.py``.
  It is stubbed via ``conftest.py`` to raise ``NotImplementedError``.
- The ``format=jsonl`` branch does NOT yet exist in
  ``apps/brokenlinkbrief/app.py`` (only ``csv`` and ``markdown`` are routed).
  The ``_Handler`` is patched to raise ``NotImplementedError`` on jsonl format.
- Therefore ALL behavioral tests are expected to FAIL against the stubs and
  PASS only after the developer wires the route and implements ``render_jsonl``.
"""
from __future__ import annotations

import http.client
import inspect
import json
import socket
import threading
from http.server import HTTPServer

import pytest

from apps.brokenlinkbrief.app import _Handler
from apps.brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# Interface tests — these MUST pass immediately.
# render_jsonl is stubbed to raise NotImplementedError, so we verify it
# exists as a callable with the correct signature without invoking it.
# ---------------------------------------------------------------------------

def test_interface_render_jsonl_importable() -> None:
    """render_jsonl must be importable from the package module."""
    from apps.brokenlinkbrief.package import render_jsonl
    assert callable(render_jsonl)


def test_interface_render_jsonl_signature_matches_contract() -> None:
    """render_jsonl(results: list[LinkResult]) -> str"""
    from apps.brokenlinkbrief.package import render_jsonl
    signature = inspect.signature(render_jsonl)
    params = list(signature.parameters.values())
    assert len(params) == 1
    assert params[0].name == "results"
    assert str(signature.return_annotation) == "str"


def test_interface_scan_handler_exposes_do_GET() -> None:
    """_Handler must have a do_GET method (shared by all /scan formats)."""
    assert callable(getattr(_Handler, "do_GET", None))


# ---------------------------------------------------------------------------
# Behavioral tests — encode the JSONL endpoint contract.
# These will FAIL against the NotImplementedError stubs and PASS only after
# the developer implements render_jsonl and wires format=jsonl in app.py.
# ---------------------------------------------------------------------------

def _start_server(monkeypatch):  # noqa: D401
    """Helper: start a temp server with monkeypatched scan_page."""
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

    monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, expected_results


def test_behavior_jsonl_output_one_valid_json_object_per_line() -> None:
    """Each line of JSONL output must be a parseable JSON object."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, expected = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=jsonl&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        lines = [line for line in body.strip().split("\n") if line]
        assert len(lines) == len(expected)
        for line in lines:
            obj = json.loads(line)
            assert isinstance(obj, dict)
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_jsonl_result_fields_match_contract() -> None:
    """Each JSONL object must contain url, status, reason, location fields."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, expected = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=jsonl&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        lines = [line for line in body.strip().split("\n") if line]
        for i, line in enumerate(lines):
            obj = json.loads(line)
            assert "url" in obj, f"line {i} missing 'url'"
            assert "status" in obj, f"line {i} missing 'status'"
            assert "reason" in obj, f"line {i} missing 'reason'"
            assert "location" in obj, f"line {i} missing 'location'"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_jsonl_content_type_header() -> None:
    """JSONL response must use Content-Type: application/x-jsonlines."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, _expected = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=jsonl&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        _body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "application/x-jsonlines"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_jsonl_values_match_scan_results() -> None:
    """JSONL objects must reflect the actual scan result values."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, expected = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=jsonl&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        lines = [line for line in body.strip().split("\n") if line]
        for i, line in enumerate(lines):
            obj = json.loads(line)
            assert obj["url"] == expected[i].url
            assert obj["status"] == expected[i].status
            assert obj["reason"] == expected[i].reason
            assert obj["location"] == expected[i].location
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_jsonl_fallback_for_unknown_format() -> None:
    """Unknown format must still return JSON (regression guard)."""
    monkeypatch = pytest.MonkeyPatch()
    server, port, _expected = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=unknown&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "application/json"
        parsed = json.loads(body)
        assert isinstance(parsed, list)
        assert parsed[0]["url"] == "https://example.com"
    finally:
        server.shutdown()
        monkeypatch.undo()
