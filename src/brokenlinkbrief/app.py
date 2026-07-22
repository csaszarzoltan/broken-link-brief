"""BrokenLinkBrief stdlib HTTP server."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from brokenlinkbrief.package import (
    compute_diff,
    get_configured_scan_token,
    get_history,
    is_scan_authorized,
    record_scan,
    render_csv,
    render_jsonl,
    render_markdown,
    scan_batch,
    scan_page,
    validate_scan_url,
)
from brokenlinkbrief.webhook import WebhookRegistry, trigger_webhooks

_AUTH_DETAIL = "missing or invalid scan token"
_LOG_TOKEN_ENV = "BROKENLINKBRIEF_LOG_FILE"
_webhook_registry = WebhookRegistry()


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: float
    details: str | None = None


@dataclass
class HealthResponse:
    """Health check response model."""

    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    timestamp: str
    checks: list[HealthCheck]


def _count_broken(results: list[Any]) -> int:
    return sum(
        1
        for r in results
        if (r.status is not None and r.status >= 400)
        or (r.status is None and r.reason is not None)
    )


def _check_external_http() -> HealthCheck:
    """Check external HTTP connectivity to a reliable endpoint."""
    start = time.perf_counter()
    try:
        req = Request("https://httpbin.org/get", method="GET")
        with urlopen(req, timeout=5.0) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            latency = (time.perf_counter() - start) * 1000
            if status == 200:
                return HealthCheck(
                    name="external_http",
                    status="healthy",
                    latency_ms=round(latency, 2),
                    details=f"HTTP {status}",
                )
            return HealthCheck(
                name="external_http",
                status="degraded",
                latency_ms=round(latency, 2),
                details=f"HTTP {status}",
            )
    except (HTTPError, URLError, socket.timeout) as exc:
        latency = (time.perf_counter() - start) * 1000
        return HealthCheck(
            name="external_http",
            status="unhealthy",
            latency_ms=round(latency, 2),
            details=str(exc),
        )


def _check_history_store() -> HealthCheck:
    """Check if history store is accessible."""
    start = time.perf_counter()
    try:
        from brokenlinkbrief.package import HistoryStore

        store = HistoryStore()
        # Just try to list the directory - this verifies the store is accessible
        _ = list(store._dir.glob("*.jsonl"))  # noqa: SLF001
        latency = (time.perf_counter() - start) * 1000
        return HealthCheck(
            name="history_store",
            status="healthy",
            latency_ms=round(latency, 2),
            details="accessible",
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return HealthCheck(
            name="history_store",
            status="unhealthy",
            latency_ms=round(latency, 2),
            details=str(exc),
        )


def _check_dns_resolution() -> HealthCheck:
    """Check DNS resolution works."""
    start = time.perf_counter()
    try:
        socket.gethostbyname("google.com")
        latency = (time.perf_counter() - start) * 1000
        return HealthCheck(
            name="dns_resolution",
            status="healthy",
            latency_ms=round(latency, 2),
            details="resolved google.com",
        )
    except (socket.gaierror, OSError) as exc:
        latency = (time.perf_counter() - start) * 1000
        return HealthCheck(
            name="dns_resolution",
            status="unhealthy",
            latency_ms=round(latency, 2),
            details=str(exc),
        )


def run_health_checks() -> HealthResponse:
    """Run all health checks and return aggregated response."""
    checks = [
        _check_external_http(),
        _check_history_store(),
        _check_dns_resolution(),
    ]

    # Determine overall status
    unhealthy_count = sum(1 for c in checks if c.status == "unhealthy")
    degraded_count = sum(1 for c in checks if c.status == "degraded")

    if unhealthy_count > 0:
        overall_status = "unhealthy"
    elif degraded_count > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return HealthResponse(
        status=overall_status,
        version="0.7.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
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
            health = run_health_checks()
            status_code = 200 if health.status == "healthy" else 503
            _write_json(self, status_code, asdict(health))
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

            # Record scan and trigger webhooks only on changes
            import threading

            # Record this scan in history
            record_scan(scan_results, target_url)

            # Get previous scan for comparison
            history = get_history(target_url, limit=2)
            if len(history) >= 2:
                previous_results = history[1].get("results", [])
                current_results = [{"url": r.url, "status": r.status} for r in scan_results]
                diff = compute_diff(previous_results, current_results)
                # Only fire webhooks if there are changes
                if diff.get("added_broken") or diff.get("fixed"):
                    def _fire_webhooks() -> None:
                        trigger_webhooks(_webhook_registry, target_url, scan_results)

                    threading.Thread(target=_fire_webhooks, daemon=True).start()
            elif scan_results:
                # First scan with broken links - fire webhooks
                broken = [r for r in scan_results if r.status and r.status >= 400]
                if broken:
                    def _fire_webhooks() -> None:
                        trigger_webhooks(_webhook_registry, target_url, scan_results)

                    threading.Thread(target=_fire_webhooks, daemon=True).start()

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

        # HISTORY ENDPOINTS
        if path == "/history":
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

            # Authenticate and get history
            results = get_history(target_url)
            _write_json(self, 200, results)
            return

        _write_json(self, 404, {"detail": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/webhooks":
            # Auth check (same as /scan)
            expected_token = get_configured_scan_token()
            if expected_token is not None:
                provided_token = None
                if "Authorization" in self.headers:
                    authorization = self.headers.get("Authorization") or ""
                    if authorization.startswith("Bearer "):
                        provided_token = authorization.split(" ", 1)[1]
                if not is_scan_authorized(provided_token):
                    _write_json(self, 401, {"detail": _AUTH_DETAIL})
                    return

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b""
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"detail": "invalid JSON"})
                return

            url = body.get("url")
            if not url:
                _write_json(self, 400, {"detail": "missing url field"})
                return

            secret = body.get("secret")

            # Check duplicate
            existing = _webhook_registry.find_by_url(url)
            if existing is not None:
                _write_json(self, 409, {"detail": "URL already registered"})
                return

            # Register
            try:
                reg = _webhook_registry.register(url, secret=secret)
            except ValueError as exc:
                _write_json(self, 400, {"detail": str(exc)})
                return

            _write_json(self, 201, {"id": reg.id, "url": reg.url})
            return

        if path == "/scan-batch":
            # Auth check (same as /scan)
            expected_token = get_configured_scan_token()
            if expected_token is not None:
                params = {
                    key: values[0]
                    for key, values in parse_qs(parsed.query).items()
                    if values
                }
                provided_token = params.get("token")
                if provided_token is None and "Authorization" in self.headers:
                    authorization = self.headers.get("Authorization") or ""
                    if authorization.startswith("Bearer "):
                        provided_token = authorization.split(" ", 1)[1]
                if not is_scan_authorized(provided_token):
                    _write_json(self, 401, {"detail": _AUTH_DETAIL})
                    return

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b""
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"detail": "invalid JSON"})
                return

            urls = body.get("urls")
            if not isinstance(urls, list) or len(urls) == 0:
                _write_json(self, 400, {"detail": "urls must be a non-empty list"})
                return

            # Reject duplicates
            if len(urls) != len(set(urls)):
                _write_json(self, 400, {"detail": "duplicate URLs in request"})
                return

            # Reject >50 URLs
            if len(urls) > 50:
                _write_json(
                    self, 400, {"detail": "maximum 50 URLs per batch request"}
                )
                return

            # SSRF validation
            for url in urls:
                error = validate_scan_url(url)
                if error is not None:
                    _write_json(
                        self,
                        400,
                        {"detail": f"SSRF blocked: {url} - {error}"},
                    )
                    return

            # Concurrency: cap at 20
            concurrency = body.get("concurrency", 10)
            try:
                concurrency = min(int(concurrency), 20)
            except (TypeError, ValueError):
                concurrency = 10

            # Scan
            start = time.perf_counter()
            batch_results = scan_batch(urls, timeout=10.0, max_workers=concurrency)
            latency = time.perf_counter() - start

            # Record scan history and trigger webhooks on changes
            import threading

            for url in urls:
                if url in batch_results:
                    results = batch_results[url]
                    record_scan(results, url)

                    # Check for changes and trigger webhooks
                    history = get_history(url, limit=2)
                    if len(history) >= 2:
                        previous_results = history[1].get("results", [])
                        current_results = [{"url": r.url, "status": r.status} for r in results]
                        diff = compute_diff(previous_results, current_results)
                        if diff.get("added_broken") or diff.get("fixed"):
                            def _fire_webhooks(u=url, r=results) -> None:
                                trigger_webhooks(_webhook_registry, u, r)

                            threading.Thread(target=_fire_webhooks, daemon=True).start()

            # Flatten results for non-JSON formats
            all_results = []
            for url in urls:
                all_results.extend(batch_results.get(url, []))

            broken_count = _count_broken(all_results)

            # JSONL logging for batch
            batch_id = f"{int(start * 1000)}_{len(urls)}"
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "batch_id": batch_id,
                "url_count": len(urls),
                "total_broken": broken_count,
                "latency_seconds": round(latency, 6),
            }
            log_file = _get_log_file()
            try:
                log_file.write(json.dumps(log_entry) + "\n")
                log_file.flush()
            finally:
                if log_file is not sys.stderr:
                    log_file.close()

            # Format response
            response_format = body.get("format")
            if response_format and response_format.lower() == "csv":
                _write_csv(self, render_csv(all_results))
                return
            if response_format and response_format.lower() == "markdown":
                _write_markdown(self, render_markdown(all_results))
                return
            if response_format and response_format.lower() == "jsonl":
                _write_jsonl(self, render_jsonl(all_results))
                return

            # Default: JSON with results and summary
            serializable = {
                url: [r.__dict__ for r in results]
                for url, results in batch_results.items()
            }
            summary = {
                "total_urls": len(urls),
                "broken_count": broken_count,
                "latency_seconds": round(latency, 6),
            }
            _write_json(self, 200, {"results": serializable, "summary": summary})
            return

        if path == "/diff":
            # Auth check (same as /scan-batch)
            expected_token = get_configured_scan_token()
            if expected_token is not None:
                params = {
                    key: values[0]
                    for key, values in parse_qs(parsed.query).items()
                    if values
                }
                provided_token = params.get("token")
                if provided_token is None and "Authorization" in self.headers:
                    authorization = self.headers.get("Authorization") or ""
                    if authorization.startswith("Bearer "):
                        provided_token = authorization.split(" ", 1)[1]
                if not is_scan_authorized(provided_token):
                    _write_json(self, 401, {"detail": _AUTH_DETAIL})
                    return

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b""
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"detail": "invalid JSON"})
                return

            previous = body.get("previous")
            current = body.get("current")
            if not previous or not current:
                _write_json(self, 400, {"detail": "missing previous or current in request"})
                return

            diff_result = compute_diff(previous, current)
            _write_json(self, 200, diff_result)
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


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "8000"))
    run(host="0.0.0.0", port=port)
