"""Pre-development interface/behavior tests for BrokenLinkBrief markdown endpoint.

Feature under test: ``GET /scan?url=<target>&format=markdown`` must return
``200`` with ``Content-Type: text/markdown; charset=utf-8`` and a body equal to
``render_markdown(scan_page(target))``.

State at authoring time (pre-tester, t_9223169c):
- ``render_markdown`` is ALREADY shipped and tested (package.py:199 +
  tests/test_brokenlinkbrief_export.py). It is NOT stubbed here.
- The ``format=markdown`` branch does NOT yet exist in
  apps/brokenlinkbrief/app.py (only ``csv`` is routed at app.py:50-52). The
  route wiring is developer-owned (P0, t_d5c66bee).
- Therefore the behavioral markdown-endpoint test is marked ``xfail``: it
  encodes the contract and is expected to PASS only after the developer wires
  the route. The JSON-fallback test is a regression guard that must pass both
  before and after wiring.
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
from apps.brokenlinkbrief.export import render_markdown as render_markdown_from_export
from apps.brokenlinkbrief.package import LinkResult, render_markdown

# ---------------------------------------------------------------------------
# Interface tests — these MUST pass immediately (render_markdown is shipped).
# Mirrors/extends tests/test_brokenlinkbrief_export.py per analyst guidance
# (extend rather than duplicate) so this endpoint file is self-contained.
# ---------------------------------------------------------------------------


def test_interface_render_markdown_importable() -> None:
    assert callable(render_markdown)
    assert callable(render_markdown_from_export)


def test_interface_render_markdown_signature_matches_contract() -> None:
    signature = inspect.signature(render_markdown)
    params = list(signature.parameters.values())
    assert len(params) == 1
    assert params[0].name == "results"
    assert str(signature.return_annotation) == "str"


def test_interface_scan_handler_exposes_do_GET() -> None:
    assert callable(getattr(_Handler, "do_GET", None))


# ---------------------------------------------------------------------------
# Behavioral tests — encode the endpoint contract.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "markdown endpoint branch not yet wired in apps/brokenlinkbrief/app.py "
        "(only csv is routed). Expected to PASS after developer implements P0."
    ),
    strict=False,
)
def test_behavior_scan_endpoint_markdown_when_format_markdown_requested() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
    expected_results = [
        LinkResult(url="https://example.com", status=200, reason="OK", location=None)
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
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/scan?url=https://example.com&format=markdown&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "text/markdown; charset=utf-8"
        assert body == render_markdown(expected_results)
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_scan_endpoint_json_fallback_when_format_unknown() -> None:
    """Regression guard: unknown format keeps the unchanged JSON path.

    Must pass BOTH before and after the markdown route is wired.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
    expected_results = [
        LinkResult(url="https://example.com", status=200, reason="OK", location=None)
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
