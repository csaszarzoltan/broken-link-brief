"""Pre-development interface/behavior tests for POST /scan-batch endpoint."""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
from http.server import HTTPServer

from brokenlinkbrief.app import _Handler  # noqa: I001

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_server(
    scan_token: str | None = None,
) -> tuple[HTTPServer, int]:
    """Spin up the BrokenLinkBrief HTTPServer and return (server, port)."""
    if scan_token is not None:
        os.environ["BROKENLINKBRIEF_SCAN_TOKEN"] = scan_token
    else:
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _post_json(
    port: int,
    path: str,
    body: dict,
    token: str | None = None,
) -> http.client.HTTPResponse | None:
    """POST JSON to the server and return the raw response."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Host": "127.0.0.1",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("POST", path, body=json.dumps(body), headers=headers)
    try:
        return conn.getresponse()
    except (ConnectionError, http.client.RemoteDisconnected):
        return None


# ---------------------------------------------------------------------------
# Interface tests (must pass immediately)
# ---------------------------------------------------------------------------


def test_interface_batch_endpoint_returns_json() -> None:
    """POST /scan-batch should exist and respond with JSON."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {"urls": ["https://example.com"]})
        assert resp is not None, "Expected a response from /scan-batch"
        body = resp.read().decode()
        assert resp.status in (200, 400, 401, 404, 405), (
            f"Expected standard status, got {resp.status}"
        )
        if resp.status not in (404, 405):
            data = json.loads(body)
            assert isinstance(data, dict)
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_interface_batch_endpoint_request_schema() -> None:
    """POST /scan-batch should accept a JSON body with a 'urls' list."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {"urls": ["https://example.com"]})
        assert resp is not None
        assert resp.status in (200, 400, 401, 404, 405)
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


# ---------------------------------------------------------------------------
# Behavior tests (implemented after feature is complete)
# ---------------------------------------------------------------------------


def test_behavior_batch_endpoint_missing_urls() -> None:
    """POST /scan-batch without urls -> 400."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {})
        assert resp is not None
        assert resp.status == 400
        data = json.loads(resp.read().decode())
        assert "detail" in data
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_empty_urls() -> None:
    """POST /scan-batch with empty urls -> 400."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {"urls": []})
        assert resp is not None
        assert resp.status == 400
        data = json.loads(resp.read().decode())
        assert "detail" in data
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_too_many_urls() -> None:
    """POST /scan-batch with >50 URLs -> 400."""
    server, port = _start_server()
    try:
        urls = [f"https://example{i}.com" for i in range(51)]
        resp = _post_json(port, "/scan-batch", {"urls": urls})
        assert resp is not None
        assert resp.status == 400
        data = json.loads(resp.read().decode())
        assert "50" in data["detail"] or "max" in data["detail"].lower()
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_duplicate_urls() -> None:
    """POST /scan-batch with duplicate URLs -> 400."""
    server, port = _start_server()
    try:
        resp = _post_json(
            port,
            "/scan-batch",
            {"urls": ["https://example.com", "https://example.com"]},
        )
        assert resp is not None
        assert resp.status == 400
        data = json.loads(resp.read().decode())
        assert "duplicate" in data["detail"].lower()
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_auth_required() -> None:
    """POST /scan-batch without token when token set -> 401."""
    server, port = _start_server(scan_token="secret")
    try:
        resp = _post_json(port, "/scan-batch", {"urls": ["https://example.com"]})
        assert resp is not None
        assert resp.status == 401
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_ssrf_blocked() -> None:
    """POST /scan-batch with private IP -> 400."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {"urls": ["http://127.0.0.1"]})
        assert resp is not None
        assert resp.status == 400
        data = json.loads(resp.read().decode())
        assert "SSRF" in data["detail"] or "ssrf" in data["detail"].lower()
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_concurrency_param() -> None:
    """POST /scan-batch respects concurrency field."""
    server, port = _start_server()
    try:
        resp = _post_json(
            port,
            "/scan-batch",
            {"urls": ["https://example.com"], "concurrency": 2},
        )
        assert resp is not None
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "results" in data
        assert "summary" in data
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)


def test_behavior_batch_endpoint_json_response_shape() -> None:
    """POST /scan-batch response has 'results' and 'summary' keys."""
    server, port = _start_server()
    try:
        resp = _post_json(port, "/scan-batch", {"urls": ["https://example.com"]})
        assert resp is not None
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "results" in data
        assert "summary" in data
        summary = data["summary"]
        assert "total_urls" in summary
        assert "latency_seconds" in summary
    finally:
        server.shutdown()
        os.environ.pop("BROKENLINKBRIEF_SCAN_TOKEN", None)
