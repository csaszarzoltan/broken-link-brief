"""BrokenLinkBrief stdlib HTTP server."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from apps.brokenlinkbrief.package import (
    get_configured_scan_token,
    is_scan_authorized,
    render_csv,
    render_jsonl,
    render_markdown,
    scan_page,
)

_AUTH_DETAIL = "missing or invalid scan token"
_LOG_TOKEN_ENV = "BROKENLINKBRIEF_LOG_FILE"


def _count_broken(results: list[Any]) -> int:
    return sum(
        1
        for r in results
        if (r.status is not None and r.status >= 400)
        or (r.reason is not None and r.reason != "OK")
    )


def _get_log_file():
    path = __import__("os").environ.get(_LOG_TOKEN_ENV)
    if path:
        return open(path, "a", encoding="utf-8")
    return sys.stderr


def _log_scan(
    target_url: str,
    results: list[Any],
    response_format: str | None,
    latency_seconds: float,
) -> None:
    broken = _count_broken(results)
    status = "ok" if broken == 0 else "error"
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_url": target_url,
        "result_count": len(results),
        "broken_count": broken,
        "format": response_format or "json",
        "latency_seconds": round(latency_seconds, 6),
        "status": status,
    }
    log_file = _get_log_file()
    try:
        log_file.write(json.dumps(log_entry) + "\n")
        log_file.flush()
    finally:
        if log_file is not sys.stderr:
            log_file.close()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = {
            key: values[0]
            for key, values in parse_qs(parsed.query).items()
            if values
        }

        if path == "/health":
            _write_json(self, 200, {"status": "ok"})
            return

        if path == "/scan":
            expected_token = get_configured_scan_token()
            if expected_token is not None:
                provided_token = params.get("token")
                if provided_token is None and "Authorization" in self.headers:
                    authorization = self.headers.get("Authorization") or ""
                    if authorization.startswith("Bearer "):
                        provided_token = authorization.split(" ", 1)[1]
                if not is_scan_authorized(provided_token):
                    _write_json(self, 401, {"detail": _AUTH_DETAIL})
                    return
            target_url = params.get("url")
            if not target_url:
                _write_json(self, 400, {"detail": "missing url query parameter"})
                return

            start = time.perf_counter()
            scan_results = scan_page(target_url)
            latency = time.perf_counter() - start

            response_format = params.get("format")
            if response_format is not None and response_format.lower() == "csv":
                _log_scan(target_url, scan_results, response_format, latency)
                _write_csv(self, render_csv(scan_results))
                return
            if response_format is not None and response_format.lower() == "markdown":
                _log_scan(target_url, scan_results, response_format, latency)
                _write_markdown(self, render_markdown(scan_results))
                return
            if response_format is not None and response_format.lower() == "jsonl":
                _log_scan(target_url, scan_results, response_format, latency)
                _write_jsonl(self, render_jsonl(scan_results))
                return

            _log_scan(target_url, scan_results, "json", latency)
            results = [result.__dict__ for result in scan_results]
            _write_json(self, 200, results)
            return

        _write_json(self, 404, {"detail": "not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def _write_json(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    payload: object,
) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_csv(
    handler: BaseHTTPRequestHandler,
    payload: str,
) -> None:
    body = payload.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_markdown(
    handler: BaseHTTPRequestHandler,
    payload: str,
) -> None:
    body = payload.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/markdown; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_jsonl(
    handler: BaseHTTPRequestHandler,
    payload: str,
) -> None:
    """Write a JSONL response with the ``application/x-jsonlines`` content type."""
    body = payload.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-jsonlines")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = HTTPServer((host, port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
