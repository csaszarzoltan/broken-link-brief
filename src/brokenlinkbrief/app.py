"""BrokenLinkBrief stdlib HTTP server."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from brokenlinkbrief import __version__
from brokenlinkbrief.finding_service import FindingService
from brokenlinkbrief.findings import FindingStore, VersionConflictError
from brokenlinkbrief.job_service import JobService
from brokenlinkbrief.notifications import NotifierConfig, RateLimiter, notify_all
from brokenlinkbrief.package import (
    HistoryStore,
    compute_diff,
    fetch_html,
    get_configured_scan_token,
    get_history,
    is_scan_authorized,
    record_scan,
    render_csv,
    render_jsonl,
    render_markdown,
    scan_batch,
    scan_link_detailed,
    scan_page,
    validate_scan_url,
)
from brokenlinkbrief.portfolio import (
    get_portfolio,
    get_portfolio_rows,
    get_portfolio_trends,
    portfolio_rows_to_dicts,
)
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_history import ScanHistoryStore
from brokenlinkbrief.scan_jobs import JobConflict
from brokenlinkbrief.scan_policy import PolicyConflict, ScanPolicyStore
from brokenlinkbrief.scheduled_projects import aggregate_scheduled_projects
from brokenlinkbrief.scheduler import ScheduleStore
from brokenlinkbrief.spa_scanner import SpaScanner
from brokenlinkbrief.triage import extract_occurrences
from brokenlinkbrief.webhook import WebhookRegistry, trigger_webhooks

_AUTH_DETAIL = "missing or invalid scan token"
_LOG_TOKEN_ENV = "BROKENLINKBRIEF_LOG_FILE"
_webhook_registry = WebhookRegistry()
_notifier_config = NotifierConfig.from_env()
_rate_limiter = RateLimiter(capacity=10, fill_rate=0.1667)  # ~10 per 60s
_job_service: JobService | None = None


def _jobs() -> JobService:
    global _job_service
    if _job_service is None:
        _job_service = JobService()
        _job_service.start()
    return _job_service


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
    except (TimeoutError, HTTPError, URLError) as exc:
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
    # /health is a liveness signal for deployment platforms. External HTTP and
    # DNS are diagnostic dependencies, not reasons to restart an otherwise
    # healthy service. Local state accessibility remains the critical check.
    history_check = next(c for c in checks if c.name == "history_store")
    overall_status = "healthy" if history_check.status == "healthy" else "unhealthy"

    return HealthResponse(
        status=overall_status,
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )


def _get_log_file():
    path = __import__("os").environ.get(_LOG_TOKEN_ENV)
    if path:
        return open(path, "a", encoding="utf-8")
    return sys.stderr


def _bearer_token(
    params: dict[str, str],
    headers: BaseHTTPRequestHandler,
) -> str | None:
    """Resolve the scan token from query params or Authorization header."""
    provided = params.get("token")
    if provided is None:
        authorization = headers.get("Authorization") or ""
        if authorization.startswith("Bearer "):
            provided = authorization.split(" ", 1)[1]
    return provided


def _require_scan_auth(
    handler: BaseHTTPRequestHandler,
    params: dict[str, str],
) -> bool:
    """Authorize the request; write 401 and return False when rejected."""
    expected_token = get_configured_scan_token()
    if expected_token is None:
        return True
    if not is_scan_authorized(_bearer_token(params, handler.headers)):
        _write_json(handler, 401, {"detail": _AUTH_DETAIL})
        return False
    return True


def _parse_query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    return {key: values[0] for key, values in parse_qs(parsed.query).items() if values}


def _read_json_body(
    handler: BaseHTTPRequestHandler,
) -> dict[str, Any] | None:
    """Read and parse a JSON request body; write 400 and return None on error."""
    content_length = int(handler.headers.get("Content-Length", 0))
    raw_body = handler.rfile.read(content_length) if content_length else b""
    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        _write_json(handler, 400, {"code": "invalid_json", "detail": "invalid JSON"})
        return None
    if not isinstance(body, dict):
        _write_json(
            handler,
            400,
            {"code": "invalid_json", "detail": "JSON body must be an object"},
        )
        return None
    return body


def _validate_targets(
    handler: BaseHTTPRequestHandler,
    targets: Any,
) -> bool:
    """Validate a list of target URLs; write 400 and return False when invalid."""
    if not isinstance(targets, list):
        _write_json(
            handler,
            400,
            {"code": "invalid_targets", "detail": "targets must be a list"},
        )
        return False
    for target in targets:
        if not isinstance(target, str):
            _write_json(
                handler,
                400,
                {"code": "invalid_target", "detail": "every target must be a string"},
            )
            return False
        error = validate_scan_url(target)
        if error is not None:
            _write_json(
                handler,
                400,
                {
                    "code": "unsafe_target",
                    "detail": f"Target URL is not allowed: {error}",
                },
            )
            return False
    return True


def _fire_webhooks(target_url: str, scan_results: list[Any]) -> None:
    """Trigger webhooks asynchronously and notify synchronously on changes."""

    def _fire() -> None:
        trigger_webhooks(_webhook_registry, target_url, scan_results)

    threading.Thread(target=_fire, daemon=True).start()
    notify_all(_notifier_config, scan_results, target_url, _rate_limiter)


def _record_scan_and_notify(
    target_url: str,
    scan_results: list[Any],
) -> None:
    """Record a scan in history and fire webhooks/notifications on changes."""
    record_scan(scan_results, target_url)

    history = get_history(target_url, limit=2)
    if len(history) >= 2:
        previous_results = history[1].get("results", [])
        current_results = [{"url": r.url, "status": r.status} for r in scan_results]
        diff = compute_diff(previous_results, current_results)
        if diff.get("added_broken") or diff.get("fixed"):
            _fire_webhooks(target_url, scan_results)
    elif scan_results:
        broken = [r for r in scan_results if r.status and r.status >= 400]
        if broken:
            _fire_webhooks(target_url, scan_results)


def _write_scan_response(
    handler: BaseHTTPRequestHandler,
    target_url: str,
    scan_results: list[Any],
    response_format: str | None,
    latency: float,
) -> None:
    """Write the /scan response in the requested format."""
    if response_format is not None:
        lower = response_format.lower()
        if lower == "csv":
            _log_scan(target_url, scan_results, response_format, latency)
            _write_csv(handler, render_csv(scan_results))
            return
        if lower == "markdown":
            _log_scan(target_url, scan_results, response_format, latency)
            _write_markdown(handler, render_markdown(scan_results))
            return
        if lower == "jsonl":
            _log_scan(target_url, scan_results, response_format, latency)
            _write_jsonl(handler, render_jsonl(scan_results))
            return

    _log_scan(target_url, scan_results, "json", latency)
    results = [result.__dict__ for result in scan_results]
    _write_json(handler, 200, results)


def _scan_project_targets(target_url: str, project_id: str) -> None:
    """Verify a saved project target and observe trusted findings for it."""
    project = ProjectStore().get(project_id)
    if target_url not in project.targets or project.archived:
        raise ValueError("target is not active in this project")
    source_body = fetch_html(target_url)
    if source_body is not None:
        service = FindingService(FindingStore())
        for occurrence in extract_occurrences(target_url, source_body):
            occurrence_error = validate_scan_url(occurrence.target_url)
            if occurrence_error is not None:
                continue
            detail = scan_link_detailed(occurrence.target_url)
            service.observe(project_id, occurrence, list(detail.attempts))


def _handle_scan(
    handler: BaseHTTPRequestHandler,
    params: dict[str, str],
) -> None:
    """Handle GET /scan."""
    if not _require_scan_auth(handler, params):
        return
    target_url = params.get("url")
    if not target_url:
        _write_json(handler, 400, {"detail": "missing url query parameter"})
        return

    validation_error = validate_scan_url(target_url)
    if validation_error is not None:
        _write_json(
            handler,
            400,
            {
                "code": "unsafe_target",
                "detail": f"Target URL is not allowed: {validation_error}",
            },
        )
        return

    start = time.perf_counter()
    # SPA mode: use Playwright to render JS before extracting links
    render_js = params.get("render_js", "").lower() in ("1", "true", "yes")
    if render_js:
        scanner = SpaScanner(headless=True)
        scan_results = scanner.scan_page(target_url, render_js=True)
    else:
        scan_results = scan_page(target_url)
    latency = time.perf_counter() - start

    # Saved-project scans additionally maintain trusted findings while
    # preserving the legacy scan response contract.
    project_id = params.get("project_id")
    if project_id:
        try:
            _scan_project_targets(target_url, project_id)
        except (KeyError, ValueError) as exc:
            _write_json(
                handler, 400, {"code": "invalid_project_scan", "detail": str(exc)}
            )
            return

    # Record scan and trigger webhooks only on changes
    _record_scan_and_notify(target_url, scan_results)

    _write_scan_response(
        handler, target_url, scan_results, params.get("format"), latency
    )


def _handle_history(
    handler: BaseHTTPRequestHandler,
    params: dict[str, str],
) -> None:
    """Handle GET /history."""
    if not _require_scan_auth(handler, params):
        return
    target_url = params.get("url")
    if not target_url:
        _write_json(handler, 400, {"detail": "missing url query parameter"})
        return

    results = get_history(target_url)
    _write_json(handler, 200, results)


def _handle_dashboard(
    handler: BaseHTTPRequestHandler,
    params: dict[str, str],
) -> None:
    """Handle GET /api/dashboard/* subpaths."""
    if not _require_scan_auth(handler, params):
        return
    store = HistoryStore()
    subpath = params["_subpath"]

    if subpath == "summary":
        try:
            days = max(0, int(params.get("days", "7")))
        except (ValueError, TypeError):
            days = 7
        since = None
        if days:
            from datetime import timedelta

            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = store.get_dashboard_summary(since=since)
        _write_json(handler, 200, result)
        return

    if subpath == "trends":
        try:
            days = int(params.get("days", "7"))
        except (ValueError, TypeError):
            days = 7
        result = store.get_trend_data(days=days)
        _write_json(handler, 200, result)
        return

    if subpath == "severity":
        try:
            days = int(params.get("days", "7"))
        except (ValueError, TypeError):
            days = 7
        result = store.get_severity_breakdown(days=days)
        _write_json(handler, 200, result)
        return

    if subpath == "target-history":
        target_url = params.get("url")
        if not target_url:
            _write_json(
                handler,
                400,
                {
                    "code": "missing_url",
                    "detail": "missing url query parameter",
                },
            )
            return
        try:
            limit = min(50, max(1, int(params.get("limit", "20"))))
        except (ValueError, TypeError):
            limit = 20
        result = store.get_target_timeline(target_url, limit=limit)
        _write_json(handler, 200, result)
        return

    if subpath == "recent-targets":
        try:
            limit = min(50, max(1, int(params.get("limit", "10"))))
        except (ValueError, TypeError):
            limit = 10
        _write_json(handler, 200, store.get_recent_targets(limit=limit))
        return

    if subpath == "domains":
        try:
            days = int(params.get("days", "7"))
        except (ValueError, TypeError):
            days = 7
        result = store.get_domain_breakdown(days=days)
        _write_json(handler, 200, result)
        return

    _write_json(handler, 404, {"detail": "not found"})


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


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BrokenLinkBrief Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      Oxygen, sans-serif;
    background: #1a1a2e; color: #e0e0e0; padding: 20px; min-height: 100vh;
  }
  h1 { color: #e94560; font-size: 1.5rem; margin-bottom: 20px;
    text-align: center; }
  .filters {
    display: flex; gap: 8px; justify-content: center;
    margin-bottom: 24px; flex-wrap: wrap;
  }
  .filters button {
    background: #16213e; color: #e0e0e0; border: 1px solid #0f3460;
    padding: 8px 16px; border-radius: 6px; cursor: pointer;
    font-size: 0.875rem; transition: all 0.2s;
  }
  .filters button:hover { background: #0f3460; }
  .filters button.active {
    background: #e94560; border-color: #e94560; color: #fff;
  }
  .cards {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px; margin-bottom: 28px;
  }
  .card {
    background: #16213e; border-radius: 10px; padding: 20px;
    text-align: center; border: 1px solid #0f3460;
  }
  .card .value { font-size: 2rem; font-weight: 700; color: #e94560; }
  .card .label {
    font-size: 0.8rem; color: #8892b0; margin-top: 6px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .charts { display: grid; grid-template-columns: 1fr; gap: 24px; }
  .chart-container {
    background: #16213e; border-radius: 10px; padding: 20px;
    border: 1px solid #0f3460;
  }
  .chart-container h2 { font-size: 1rem; color: #8892b0; margin-bottom: 12px; }
  .chart-container canvas { max-height: 300px; }
  @media (min-width: 768px) {
    .charts { grid-template-columns: 1fr 1fr; }
    .chart-container.trend { grid-column: 1 / -1; }
  }
  @media (min-width: 1280px) {
    body { max-width: 1200px; margin: 0 auto; }
    .cards { grid-template-columns: repeat(4, 1fr); }
  }
  .loading { text-align: center; padding: 40px; color: #8892b0; }
  .error { text-align: center; padding: 20px; color: #e94560; }
  .skip-link { position:absolute; left:-9999px; top:8px; background:#fff; color:#111; padding:8px; z-index:10; }
  .skip-link:focus { left:8px; }
  .scan-panel { background:#16213e; border:1px solid #0f3460; border-radius:10px; padding:20px; margin-bottom:24px; }
  .scan-panel h2 { font-size:1.1rem; margin-bottom:12px; }
  .scan-row { display:flex; gap:8px; flex-wrap:wrap; }
  .scan-row input { flex:1 1 360px; min-width:0; padding:10px 12px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; }
  .primary { border:0; border-radius:6px; padding:10px 18px; background:#e94560; color:#fff; font-weight:700; cursor:pointer; }
  .primary:disabled { opacity:.6; cursor:wait; }
  .status { min-height:1.5rem; margin-top:10px; color:#b8c2dd; }
  .results { margin-top:14px; overflow:auto; }
  table { width:100%; border-collapse:collapse; font-size:.875rem; }
  th, td { text-align:left; padding:9px; border-bottom:1px solid #294066; }
  th { color:#b8c2dd; }
  .badge { display:inline-block; border-radius:999px; padding:2px 8px; font-weight:700; }
  .badge.bad { background:#5d2030; color:#ffd7df; } .badge.good { background:#164a3c; color:#d4ffef; }
  .muted { color:#8892b0; }
  .recent-list { display:grid; gap:8px; margin-top:12px; }
  .recent-item { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 0; border-bottom:1px solid #294066; }
  .recent-meta { min-width:0; }
  .recent-url { overflow-wrap:anywhere; font-weight:650; }
  .secondary { background:#0f3460; color:#fff; border:1px solid #52658a; border-radius:6px; padding:8px 12px; cursor:pointer; white-space:nowrap; }
  .secondary:hover, .secondary:focus-visible { background:#1a4b7d; }
  .recent-actions { display:flex; gap:8px; flex-wrap:wrap; }
  dialog { width:min(760px, calc(100% - 32px)); max-height:85vh; overflow:auto; color:#e0e0e0; background:#16213e; border:1px solid #52658a; border-radius:10px; padding:20px; }
  dialog::backdrop { background:rgba(0,0,0,.72); }
  .dialog-head { display:flex; justify-content:space-between; align-items:start; gap:16px; margin-bottom:14px; }
  .icon-button { background:transparent; color:#fff; border:1px solid #52658a; border-radius:6px; padding:6px 10px; cursor:pointer; }
  .timeline { display:grid; gap:10px; }
  .timeline-item { border-left:4px solid #0f3460; padding:10px 12px; background:#0e1730; }
  .change-good { color:#81e6c3; } .change-bad { color:#ff9aac; }
  .result-tools { display:flex; gap:8px; align-items:end; flex-wrap:wrap; margin-top:14px; padding-top:14px; border-top:1px solid #294066; }
  .result-tools[hidden] { display:none; }
  .result-tools label { display:grid; gap:4px; flex:1 1 240px; }
  .result-tools input, .result-tools select { width:100%; padding:8px 10px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; }
  .filter-group { display:flex; gap:6px; flex-wrap:wrap; }
  .filter-group button[aria-pressed="true"] { background:#e94560; border-color:#e94560; }
  .result-count { flex-basis:100%; margin:0; }
  .mode-tabs { display:flex; gap:8px; margin-bottom:16px; }
  .mode-tabs button[aria-selected="true"] { background:#e94560; border-color:#e94560; }
  .scan-mode-panel[hidden] { display:none; }
  .batch-grid { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:12px; align-items:end; }
  .batch-grid label { display:grid; gap:4px; }
  textarea { min-height:130px; resize:vertical; padding:10px 12px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; font:inherit; }
  input[type="number"] { padding:10px 12px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; }
  @media (max-width:640px) { .batch-grid { grid-template-columns:1fr; } }
  .project-form { display:grid; gap:10px; }
  .project-form input, .project-form textarea { width:100%; padding:10px 12px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; font:inherit; }
  .project-list { display:grid; gap:10px; margin-top:16px; }
  .project-item { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:12px; border:1px solid #294066; border-radius:8px; }
  .project-item strong { display:block; }
  :root { --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --focus:#8bd3ff; }
  :focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
  .finding-filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; align-items:end; }
  .finding-filters label { display:grid; gap:4px; }
  .finding-filters select,.finding-filters input { padding:10px; border-radius:6px; border:1px solid #52658a; background:#0e1730; color:#fff; }
  .finding-card { border:1px solid #294066; border-radius:8px; padding:12px; margin-top:8px; }
  @media (prefers-reduced-motion:reduce) { * { scroll-behavior:auto!important; transition:none!important; } }
</style>
</head>
<body>
<a class="skip-link" href="#scanResults">Skip to results</a>
<h1>BrokenLinkBrief Dashboard</h1>
<section class="scan-panel" aria-labelledby="projectsHeading">
  <h2 id="projectsHeading">Saved projects</h2>
  <p class="muted">Save frequently scanned pages as a reusable project. Pinned projects appear first.</p>
  <form id="projectForm" class="project-form">
    <label for="projectName">Project name
      <input id="projectName" required maxlength="120" placeholder="Main website">
    </label>
    <label for="projectTargets">Project targets
      <textarea id="projectTargets" required placeholder="https://example.com&#10;https://example.org" aria-describedby="projectHelp projectStatus"></textarea>
    </label>
    <p id="projectHelp" class="muted">Enter one public URL per line, up to 50 targets.</p>
    <div class="recent-actions">
      <button type="submit" id="saveProject" class="primary">Save project</button>
      <button type="button" id="cancelProjectEdit" class="secondary" hidden>Cancel edit</button>
      <button type="button" id="toggleArchivedProjects" class="secondary">Show archived</button>
      <label class="secondary" for="projectImportFile">Import project</label>
      <input id="projectImportFile" type="file" accept="application/json,.json" hidden>
    </div>
  </form>
  <div id="projectStatus" class="status" role="status" aria-live="polite"></div>
  <div id="projectList" class="project-list" aria-live="polite"><p class="muted">Loading projects…</p></div>
</section>
<section class="scan-panel" aria-labelledby="jobsHeading" id="scanJobs"><h2 id="jobsHeading" tabindex="-1">Scan jobs</h2><p class="muted">Saved-project scans continue after refresh and preserve per-source progress.</p><div class="recent-actions"><button class="secondary" id="refreshJobs" type="button">Refresh jobs</button></div><div id="jobsStatus" class="status" role="status" aria-live="polite">Loading scan jobs.</div><ol id="jobsList" class="project-list"></ol></section>
<section class="scan-panel" aria-labelledby="findingsHeading" id="findingsWorkspace">
  <h2 id="findingsHeading">Trusted findings</h2>
  <p class="muted">Confirmed broken links become durable repair work with evidence and source context.</p>
  <div class="finding-filters"><label for="findingProject">Project<select id="findingProject"><option value="">Choose a project</option></select></label><label for="findingState">State<select id="findingState"><option value="">Open and acknowledged</option><option>OPEN</option><option>ACKNOWLEDGED</option><option>IGNORED</option><option>RESOLVED</option></select></label><label for="findingClassification">Classification<select id="findingClassification"><option value="">All classifications</option><option>CONFIRMED_BROKEN</option><option>TRANSIENT</option><option>BOT_BLOCKED</option><option>RECOVERED</option><option>INCONCLUSIVE</option></select></label><label for="findingSearch">Search<input id="findingSearch" type="search" placeholder="Target or assignee"></label><button class="secondary" id="refreshFindings" type="button">Refresh findings</button></div>
  <div id="findingStatus" class="status" role="status" aria-live="polite">Choose a saved project to review findings.</div><div id="findingList" aria-live="polite"></div>
</section>
<dialog id="findingDialog" aria-labelledby="findingDialogTitle"><div class="dialog-head"><h2 id="findingDialogTitle">Finding details</h2><button type="button" id="closeFinding" class="icon-button">Close</button></div><div id="findingActionStatus" role="status" aria-live="assertive"></div><div id="findingDetail"></div></dialog>
<section class="scan-panel" aria-labelledby="scanHeading">
  <h2 id="scanHeading">Scan pages</h2>
  <div class="mode-tabs" role="tablist" aria-label="Scan mode">
    <button type="button" class="secondary" role="tab" aria-selected="true" data-scan-mode="single" aria-controls="singleScanPanel">Single page</button>
    <button type="button" class="secondary" role="tab" aria-selected="false" data-scan-mode="batch" aria-controls="batchScanPanel">Multiple pages</button>
  </div>
  <div id="singleScanPanel" class="scan-mode-panel" role="tabpanel">
  <form id="scanForm">
    <label for="scanUrl">Page URL</label>
    <div class="scan-row"><input id="scanUrl" name="url" type="url" inputmode="url" required placeholder="https://example.com" autocomplete="url" aria-describedby="scanHelp scanStatus"><button class="primary" id="scanButton" type="submit">Run scan</button></div>
    <p id="scanHelp" class="muted">Enter a public HTTP or HTTPS page. Private network targets are blocked.</p>
  </form>
  <div id="scanStatus" class="status" role="status" aria-live="polite"></div>
  </div>
  <div id="batchScanPanel" class="scan-mode-panel" role="tabpanel" hidden>
    <form id="batchScanForm">
      <div class="batch-grid">
        <label for="batchUrls">Page URLs
          <textarea id="batchUrls" required placeholder="https://example.com&#10;https://example.org" aria-describedby="batchHelp batchStatus"></textarea>
        </label>
        <label for="batchConcurrency">Parallel scans
          <input id="batchConcurrency" type="number" min="1" max="20" value="10">
        </label>
      </div>
      <p id="batchHelp" class="muted">Enter one URL per line, up to 50 unique public URLs.</p>
      <button class="primary" id="batchScanButton" type="submit">Run batch scan</button>
    </form>
    <div id="batchStatus" class="status" role="status" aria-live="polite"></div>
  </div>
  <div id="resultTools" class="result-tools" hidden>
    <div class="filter-group" role="group" aria-label="Filter scan results">
      <button type="button" class="secondary" data-result-filter="all" aria-pressed="true">All results</button>
      <button type="button" class="secondary" data-result-filter="attention" aria-pressed="false">Needs attention</button>
      <button type="button" class="secondary" data-result-filter="healthy" aria-pressed="false">Healthy</button>
    </div>
    <label for="sourceFilter">Source page
      <select id="sourceFilter"><option value="">All source pages</option></select>
    </label>
    <label for="resultSearch">Search results
      <input id="resultSearch" type="search" placeholder="Source, URL, status, or reason" autocomplete="off">
    </label>
    <button type="button" id="exportResults" class="secondary">Export visible CSV</button>
    <p id="visibleResultCount" class="muted result-count" aria-live="polite">0 results shown</p>
  </div>
  <div id="scanResults" class="results" tabindex="-1"></div>
</section>
<section class="scan-panel" aria-labelledby="recentHeading">
  <h2 id="recentHeading">Recent pages</h2>
  <p class="muted">Quickly repeat a scan without re-entering the URL.</p>
  <div id="recentTargets" class="recent-list" aria-live="polite">
    <p class="muted">Loading recent pages…</p>
  </div>
</section>
<div class="filters" aria-label="Dashboard date range">
  <button onclick="setDays(7)" class="active" id="d7">7 days</button>
  <button onclick="setDays(30)" id="d30">30 days</button>
  <button onclick="setDays(90)" id="d90">90 days</button>
  <button onclick="setDays(0)" id="d0">All time</button>
</div>
<div class="cards" id="summaryCards">
  <div class="card">
    <div class="value" id="totalScans">-</div>
    <div class="label">Total Scans</div>
  </div>
  <div class="card">
    <div class="value" id="totalBroken">-</div>
    <div class="label">Broken Links</div>
  </div>
  <div class="card">
    <div class="value" id="totalLinks">-</div>
    <div class="label">Links Checked</div>
  </div>
  <div class="card">
    <div class="value" id="lastScan">-</div>
    <div class="label">Last Scan</div>
  </div>
</div>
<section class="scan-panel" aria-labelledby="portfolioHeading" id="portfolioSection">
  <h2 id="portfolioHeading" tabindex="-1">Portfolio overview</h2>
  <p class="muted">Cross-project health for all saved projects. Select a date range to focus the overview.</p>
  <div class="recent-actions">
    <button type="button" id="exportPortfolio" class="secondary">Export CSV</button>
  </div>
  <div class="filters" id="portfolioDays" role="group" aria-label="Portfolio date range">
    <button type="button" class="secondary" data-portfolio-days="7">7 days</button>
    <button type="button" class="secondary active" data-portfolio-days="30" aria-pressed="true">30 days</button>
    <button type="button" class="secondary" data-portfolio-days="90">90 days</button>
    <button type="button" class="secondary" data-portfolio-days="0">All time</button>
  </div>
  <div class="cards" id="portfolioCards" aria-live="polite">
    <p class="muted">Portfolio summary will appear here.</p>
  </div>
  <div id="portfolioRows" aria-live="polite"></div>
  <div class="chart-container trend">
    <h2>Portfolio Broken-Links Trend</h2>
    <canvas id="portfolioTrendCanvas"></canvas>
  </div>
</section>
<div class="charts">
  <div class="chart-container trend">
    <h2>Broken Links Trend</h2>
    <canvas id="trendChart"></canvas>
  </div>
  <div class="chart-container">
    <h2>Severity Breakdown</h2>
    <canvas id="severityChart"></canvas>
  </div>
  <div class="chart-container">
    <h2>Domain Breakdown</h2>
    <canvas id="domainChart"></canvas>
  </div>
</div>
<dialog id="historyDialog" aria-labelledby="historyTitle">
  <div class="dialog-head">
    <div><h2 id="historyTitle">Scan history</h2><p id="historyTarget" class="muted"></p></div>
    <div class="recent-actions">
      <button type="button" id="exportHistory" class="secondary">Export history JSON</button>
      <button type="button" id="closeHistory" class="icon-button" aria-label="Close history">Close</button>
    </div>
  </div>
  <div id="historyContent" aria-live="polite"><p class="muted">Select a page to view its history.</p></div>
</dialog>
<script>
let currentDays = 7;
let trendChartInstance = null;
let severityChartInstance = null;
let domainChartInstance = null;
let activeHistory = {url: '', items: []};
let latestScanResults = [];
let visibleScanResults = [];
let activeResultFilter = 'all';
let editingProjectId = null;
let showingArchivedProjects = false;

function getToken() {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');
  if (token) return `token=${token}`;
  return '';
}

async function setDays(days) {
  currentDays = days;
  document.querySelectorAll('.filters button').forEach(
    b => b.classList.remove('active')
  );
  const btn = document.getElementById(`d${days}`);
  if (btn) btn.classList.add('active');
  await loadAll();
}

async function loadTargetHistory(url) {
  const dialog = document.getElementById('historyDialog');
  const content = document.getElementById('historyContent');
  document.getElementById('historyTarget').textContent = url;
  content.innerHTML = '<p class="muted">Loading scan history…</p>';
  if (!dialog.open) dialog.showModal();
  const token = new URLSearchParams(window.location.search).get('token');
  const query = new URLSearchParams({url, limit: '20'});
  if (token) query.set('token', token);
  try {
    const response = await fetch(`/api/dashboard/target-history?${query}`);
    const items = await response.json();
    if (!response.ok) throw new Error(items.detail || 'History could not be loaded');
    if (!items.length) {
      content.innerHTML = '<p class="muted">No scan history is available for this page.</p>';
      return;
    }
    activeHistory = {url, items};
    content.innerHTML = `<div class="timeline">${items.map(item => {
      const when = item.timestamp ? new Date(item.timestamp).toLocaleString() : 'Unknown time';
      return `<article class="timeline-item"><strong>${escapeHtml(when)}</strong>`
        + `<p>${item.total_links} links checked, ${item.broken_count} need attention</p>`
        + `<p><span class="change-bad">Newly broken: ${item.newly_broken_count}</span> · `
        + `<span class="change-good">Fixed: ${item.fixed_count}</span></p>`
        + `<details><summary>Change details</summary>`
        + `<h3>Newly broken links</h3>${renderChangeList(item.newly_broken, 'No newly broken links.')}`
        + `<h3>Fixed links</h3>${renderChangeList(item.fixed, 'No fixed links.')}</details></article>`;
    }).join('')}</div>`;
  } catch (error) {
    content.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

function renderChangeList(items, emptyMessage) {
  if (!items || !items.length) return `<p class="muted">${escapeHtml(emptyMessage)}</p>`;
  return `<ul>${items.map(item => `<li><span class="recent-url">${escapeHtml(item.url)}</span> `
    + `<span class="muted">Status: ${escapeHtml(item.status ?? 'No response')}</span></li>`).join('')}</ul>`;
}

function exportTargetHistory() {
  if (!activeHistory.items.length) return;
  const payload = JSON.stringify(activeHistory, null, 2);
  const blob = new Blob([payload], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'brokenlinkbrief-history.json';
  link.click();
  URL.revokeObjectURL(link.href);
}

document.getElementById('exportHistory').addEventListener('click', exportTargetHistory);
document.getElementById('closeHistory').addEventListener('click', () => {
  document.getElementById('historyDialog').close();
});
document.getElementById('historyDialog').addEventListener('click', (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

function apiTokenQuery() {
  const token = new URLSearchParams(window.location.search).get('token');
  return token ? `?token=${encodeURIComponent(token)}` : '';
}

function runProjectScan(project) {
  window.activeProjectScanId = project.id;
  loadProjectTargets(project);
  if (project.targets.length === 1) {
    document.getElementById('scanForm').requestSubmit();
  } else {
    document.getElementById('batchScanForm').requestSubmit();
  }
}

function loadProjectTargets(project) {
  const targets = project.targets || [];
  if (targets.length === 1) {
    document.querySelector('[data-scan-mode="single"]').click();
    document.getElementById('scanUrl').value = targets[0];
  } else {
    document.querySelector('[data-scan-mode="batch"]').click();
    document.getElementById('batchUrls').value = targets.join('\n');
  }
  document.getElementById('scanHeading').scrollIntoView({behavior: 'smooth'});
}

async function loadProjects() {
  const container = document.getElementById('projectList');
  try {
    const archived = showingArchivedProjects ? '&archived=1' : '';
    const suffix = apiTokenQuery();
    const response = await fetch(`/api/projects${suffix}${suffix ? archived : archived.replace('&', '?')}`);
    const projects = await response.json();
    if (!response.ok) throw new Error(projects.detail || 'Projects could not be loaded');
    if (!projects.length) {
      container.innerHTML = '<p class="muted">No saved projects yet. Save your recurring targets above.</p>';
      return;
    }
    container.innerHTML = projects.map((project, index) =>
      `<article class="project-item"><div><strong>${escapeHtml(project.name)}</strong>`
      + `<span class="muted">${project.targets.length} target${project.targets.length === 1 ? '' : 's'}</span>`
      + `<span class="muted">${project.scan_summary && project.scan_summary.last_scan_timestamp
        ? `${project.scan_summary.broken_count} need attention · last scan ${new Date(project.scan_summary.last_scan_timestamp).toLocaleString()}`
        : 'Never scanned'}</span></div>`
      + `<div class="recent-actions">`
      + (!project.archived ? `<button type="button" class="primary" data-project-run="${index}">Run project scan</button>` : '')
      + `<button type="button" class="secondary" data-project-index="${index}">Load targets</button>`
      + `<button type="button" class="secondary" data-project-export="${index}">Export project</button>`
      + `<button type="button" class="secondary" data-project-duplicate="${index}">Duplicate</button>`
      + `<button type="button" class="secondary" data-project-pin="${index}">${project.pinned ? 'Unpin' : 'Pin'}</button>`
      + (project.archived
        ? `<button type="button" class="secondary" data-project-restore="${index}">Restore</button>`
        : `<button type="button" class="secondary" data-project-edit="${index}">Edit</button>`
          + `<button type="button" class="icon-button" data-project-archive="${index}">Archive</button>`)
      + `</div></article>`
    ).join('');
    container.querySelectorAll('[data-project-run]').forEach(button => {
      button.addEventListener('click', () => runProjectScan(projects[Number(button.dataset.projectRun)]));
    });
    container.querySelectorAll('[data-project-index]').forEach(button => {
      button.addEventListener('click', () => loadProjectTargets(projects[Number(button.dataset.projectIndex)]));
    });
    container.querySelectorAll('[data-project-archive]').forEach(button => {
      button.addEventListener('click', () => archiveProject(projects[Number(button.dataset.projectArchive)]));
    });
    container.querySelectorAll('[data-project-export]').forEach(button => {
      button.addEventListener('click', () => exportProject(projects[Number(button.dataset.projectExport)]));
    });
    container.querySelectorAll('[data-project-duplicate]').forEach(button => {
      button.addEventListener('click', () => duplicateProject(projects[Number(button.dataset.projectDuplicate)]));
    });
    container.querySelectorAll('[data-project-pin]').forEach(button => {
      button.addEventListener('click', () => toggleProjectPin(projects[Number(button.dataset.projectPin)]));
    });
    container.querySelectorAll('[data-project-edit]').forEach(button => {
      button.addEventListener('click', () => editProject(projects[Number(button.dataset.projectEdit)]));
    });
    container.querySelectorAll('[data-project-restore]').forEach(button => {
      button.addEventListener('click', () => restoreProject(projects[Number(button.dataset.projectRestore)]));
    });
  } catch (error) {
    container.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

async function toggleProjectPin(project) {
  const status = document.getElementById('projectStatus');
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}/pin${apiTokenQuery()}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pinned: !project.pinned}),
    });
    const updated = await response.json();
    if (!response.ok) throw new Error(updated.detail || 'Project pin could not be updated');
    status.textContent = `${updated.pinned ? 'Pinned' : 'Unpinned'} ${project.name}.`;
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
}

async function duplicateProject(project) {
  const status = document.getElementById('projectStatus');
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}/duplicate${apiTokenQuery()}`, {method: 'POST'});
    const duplicate = await response.json();
    if (!response.ok) throw new Error(duplicate.detail || 'Project could not be duplicated');
    status.textContent = `Duplicated ${project.name} as ${duplicate.name}.`;
    showingArchivedProjects = false;
    document.getElementById('toggleArchivedProjects').textContent = 'Show archived';
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
}

async function exportProject(project) {
  const status = document.getElementById('projectStatus');
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}/export${apiTokenQuery()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Project could not be exported');
    const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'brokenlinkbrief-project.json';
    link.click();
    URL.revokeObjectURL(link.href);
    status.textContent = `Exported ${project.name}.`;
  } catch (error) { status.textContent = error.message; }
}

async function importProject(file) {
  const status = document.getElementById('projectStatus');
  try {
    const text = await file.text();
    let configuration;
    try { configuration = JSON.parse(text); }
    catch (error) { throw new Error('The selected file is not valid JSON.'); }
    const response = await fetch(`/api/projects/import${apiTokenQuery()}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(configuration),
    });
    const project = await response.json();
    if (!response.ok) throw new Error(project.detail || 'Project could not be imported');
    status.textContent = `Imported ${project.name}.`;
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
  finally { document.getElementById('projectImportFile').value = ''; }
}

document.getElementById('projectImportFile').addEventListener('change', event => {
  const file = event.target.files[0];
  if (file) importProject(file);
});

function editProject(project) {
  editingProjectId = project.id;
  document.getElementById('projectName').value = project.name;
  document.getElementById('projectTargets').value = project.targets.join('\n');
  document.getElementById('saveProject').textContent = 'Update project';
  document.getElementById('cancelProjectEdit').hidden = false;
  document.getElementById('projectName').focus();
}

function resetProjectForm() {
  editingProjectId = null;
  document.getElementById('projectForm').reset();
  document.getElementById('saveProject').textContent = 'Save project';
  document.getElementById('cancelProjectEdit').hidden = true;
}

async function restoreProject(project) {
  const status = document.getElementById('projectStatus');
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}/restore${apiTokenQuery()}`, {method: 'POST'});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Project could not be restored');
    status.textContent = `Restored ${project.name}.`;
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
}

document.getElementById('cancelProjectEdit').addEventListener('click', resetProjectForm);
document.getElementById('toggleArchivedProjects').addEventListener('click', async () => {
  showingArchivedProjects = !showingArchivedProjects;
  document.getElementById('toggleArchivedProjects').textContent = showingArchivedProjects ? 'Show active' : 'Show archived';
  await loadProjects();
});

async function archiveProject(project) {
  if (!window.confirm(`Archive ${project.name}? Scans and history are not deleted.`)) return;
  const status = document.getElementById('projectStatus');
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}${apiTokenQuery()}`, {method: 'DELETE'});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Project could not be archived');
    status.textContent = `Archived ${project.name}.`;
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
}

document.getElementById('projectForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.getElementById('projectStatus');
  const button = document.getElementById('saveProject');
  let targets;
  try { targets = parseBatchUrls(document.getElementById('projectTargets').value); }
  catch (error) { status.textContent = error.message; return; }
  button.disabled = true;
  status.textContent = 'Saving project…';
  try {
    const url = editingProjectId ? `/api/projects/${encodeURIComponent(editingProjectId)}${apiTokenQuery()}` : `/api/projects${apiTokenQuery()}`;
    const response = await fetch(url, {
      method: editingProjectId ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: document.getElementById('projectName').value, targets}),
    });
    const project = await response.json();
    if (!response.ok) throw new Error(project.detail || 'Project could not be saved');
    status.textContent = `${editingProjectId ? 'Updated' : 'Saved'} ${project.name} with ${project.targets.length} targets.`;
    resetProjectForm();
    await loadProjects();
  } catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});

async function loadRecentTargets() {
  const container = document.getElementById('recentTargets');
  const token = new URLSearchParams(window.location.search).get('token');
  const query = new URLSearchParams({limit: '8'});
  if (token) query.set('token', token);
  try {
    const response = await fetch(`/api/dashboard/recent-targets?${query}`);
    if (!response.ok) throw new Error('Recent pages could not be loaded');
    const items = await response.json();
    if (!items.length) {
      container.innerHTML = '<p class="muted">Your scanned pages will appear here for quick access.</p>';
      return;
    }
    container.innerHTML = items.map((item, index) => {
      const summary = `${item.total_links} links, ${item.broken_count} need attention`;
      return `<div class="recent-item"><div class="recent-meta"><div class="recent-url">${escapeHtml(item.url)}</div>`
        + `<div class="muted">${escapeHtml(summary)}</div></div>`
        + `<div class="recent-actions"><button type="button" class="secondary" data-history-index="${index}">View history</button>`
        + `<button type="button" class="secondary" data-recent-index="${index}">Scan again</button></div></div>`;
    }).join('');
    container.querySelectorAll('[data-history-index]').forEach((button) => {
      button.addEventListener('click', () => {
        loadTargetHistory(items[Number(button.dataset.historyIndex)].url);
      });
    });
    container.querySelectorAll('[data-recent-index]').forEach((button) => {
      button.addEventListener('click', () => {
        document.getElementById('scanUrl').value = items[Number(button.dataset.recentIndex)].url;
        document.getElementById('scanForm').requestSubmit();
      });
    });
  } catch (error) {
    container.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

document.querySelectorAll('[data-scan-mode]').forEach(button => {
  button.addEventListener('click', () => {
    const mode = button.dataset.scanMode;
    document.querySelectorAll('[data-scan-mode]').forEach(item => item.setAttribute('aria-selected', String(item === button)));
    document.getElementById('singleScanPanel').hidden = mode !== 'single';
    document.getElementById('batchScanPanel').hidden = mode !== 'batch';
    document.getElementById(mode === 'single' ? 'scanUrl' : 'batchUrls').focus();
  });
});

function parseBatchUrls(value) {
  const urls = value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
  if (!urls.length) throw new Error('Enter at least one URL.');
  if (urls.length > 50) throw new Error('Enter no more than 50 URLs.');
  if (new Set(urls).size !== urls.length) throw new Error('Remove duplicate URLs before scanning.');
  return urls;
}

function attachSourceContext(results, sourceUrl) {
  return results.map(item => ({...item, source_url: sourceUrl}));
}

function flattenBatchResults(results) {
  return Object.entries(results).flatMap(([sourceUrl, items]) => attachSourceContext(items, sourceUrl));
}

function populateSourceFilter(results) {
  const select = document.getElementById('sourceFilter');
  const previous = select.value;
  const sources = [...new Set(results.map(item => item.source_url).filter(Boolean))].sort();
  select.innerHTML = '<option value="">All source pages</option>'
    + sources.map(source => `<option value="${escapeHtml(source)}">${escapeHtml(source)}</option>`).join('');
  select.value = sources.includes(previous) ? previous : '';
}

function showScanResults(results) {
  latestScanResults = results;
  activeResultFilter = 'all';
  document.getElementById('resultSearch').value = '';
  populateSourceFilter(results);
  document.querySelectorAll('[data-result-filter]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.resultFilter === 'all'));
  });
  document.getElementById('resultTools').hidden = results.length === 0;
  applyResultView();
}

async function runBatchScan(event) {
  event.preventDefault();
  const status = document.getElementById('batchStatus');
  const button = document.getElementById('batchScanButton');
  let urls;
  try { urls = parseBatchUrls(document.getElementById('batchUrls').value); }
  catch (error) { status.textContent = error.message; return; }
  const concurrency = Math.min(20, Math.max(1, Number(document.getElementById('batchConcurrency').value) || 10));
  button.disabled = true;
  status.textContent = `Scanning ${urls.length} pages. This may take a moment…`;
  const token = new URLSearchParams(window.location.search).get('token');
  const query = new URLSearchParams();
  if (token) query.set('token', token);
  try {
    const response = await fetch(`/scan-batch?${query}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({urls, concurrency}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Batch scan failed');
    const results = flattenBatchResults(payload.results);
    showScanResults(results);
    status.textContent = `${payload.summary.total_urls} pages scanned. ${payload.summary.broken_count} links need attention.`;
    document.getElementById('scanResults').focus();
    await Promise.all([loadAll(), loadRecentTargets()]);
  } catch (error) { status.textContent = `Unable to scan: ${error.message}`; }
  finally { button.disabled = false; }
}

document.getElementById('batchScanForm').addEventListener('submit', runBatchScan);

document.getElementById('scanForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = document.getElementById('scanUrl');
  const button = document.getElementById('scanButton');
  const status = document.getElementById('scanStatus');
  if (!input.reportValidity()) return;
  button.disabled = true; status.textContent = 'Scanning. This may take a moment…';
  const query = new URLSearchParams({url: input.value.trim()});
  if (window.activeProjectScanId) { query.set('project_id', window.activeProjectScanId); window.activeProjectScanId = null; }
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) query.set('token', token);
  try {
    const response = await fetch(`/scan?${query}`); const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Scan failed');
    const broken = payload.filter(needsAttention);
    status.textContent = `${payload.length} links checked. ${broken.length} need attention.`;
    showScanResults(attachSourceContext(payload, input.value.trim()));
    document.getElementById('scanResults').focus(); await Promise.all([loadAll(), loadRecentTargets()]);
  } catch (error) { status.textContent = `Unable to scan: ${error.message}`; }
  finally { button.disabled = false; }
});
function needsAttention(item) {
  return item.status === null || item.status >= 400;
}

function applyResultView() {
  const query = document.getElementById('resultSearch').value.trim().toLowerCase();
  const source = document.getElementById('sourceFilter').value;
  visibleScanResults = latestScanResults.filter(item => {
    const attention = needsAttention(item);
    const categoryMatches = activeResultFilter === 'all'
      || (activeResultFilter === 'attention' && attention)
      || (activeResultFilter === 'healthy' && !attention);
    const text = `${item.source_url || ''} ${item.url} ${item.reason || ''} ${item.status ?? ''}`.toLowerCase();
    const sourceMatches = !source || item.source_url === source;
    return categoryMatches && sourceMatches && (!query || text.includes(query));
  });
  const rows = visibleScanResults.map(item => {
    const failed = needsAttention(item);
    const value = item.status === null ? 'No response' : String(item.status);
    return `<tr><td>${escapeHtml(item.source_url || '')}</td><td>${escapeHtml(item.url)}</td><td><span class="badge ${failed ? 'bad' : 'good'}">${escapeHtml(value)}</span></td><td>${escapeHtml(item.reason || '')}</td></tr>`;
  }).join('');
  document.getElementById('visibleResultCount').textContent = `${visibleScanResults.length} of ${latestScanResults.length} results shown`;
  document.getElementById('exportResults').disabled = visibleScanResults.length === 0;
  document.getElementById('scanResults').innerHTML = visibleScanResults.length
    ? `<table><caption>Latest scan results</caption><thead><tr><th scope="col">Source page</th><th scope="col">Link</th><th scope="col">Status</th><th scope="col">Reason</th></tr></thead><tbody>${rows}</tbody></table>`
    : '<p>No results match the selected filter and search.</p>';
}

function escapeCsvCell(value) {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+@\t\r-]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function exportVisibleResults() {
  if (!visibleScanResults.length) return;
  const rows = [['source_url', 'url', 'status', 'reason', 'location'], ...visibleScanResults.map(item => [item.source_url, item.url, item.status, item.reason, item.location])];
  const csv = rows.map(row => row.map(escapeCsvCell).join(',')).join('\n') + '\n';
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'brokenlinkbrief-visible-results.csv';
  link.click();
  URL.revokeObjectURL(link.href);
}

document.querySelectorAll('[data-result-filter]').forEach(button => {
  button.addEventListener('click', () => {
    activeResultFilter = button.dataset.resultFilter;
    document.querySelectorAll('[data-result-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    applyResultView();
  });
});
document.getElementById('resultSearch').addEventListener('input', applyResultView);
document.getElementById('sourceFilter').addEventListener('change', applyResultView);
document.getElementById('exportResults').addEventListener('click', exportVisibleResults);

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function loadAll() {
  const daysParam = currentDays > 0 ? `days=${currentDays}` : '';
  const token = getToken();
  const sep = token ? (daysParam ? '&' : '?') : '';
  const suffix = daysParam || token ? `?${daysParam}${sep}${token}` : '';

  try {
    const [summaryRes, trendsRes, severityRes, domainsRes]
      = await Promise.all([
        fetch(`/api/dashboard/summary${suffix}`),
        fetch(`/api/dashboard/trends${suffix}`),
        fetch(`/api/dashboard/severity${suffix}`),
        fetch(`/api/dashboard/domains${suffix}`),
      ]);
    if (
      !summaryRes.ok || !trendsRes.ok
      || !severityRes.ok || !domainsRes.ok
    ) {
      document.querySelector('.charts').innerHTML
        = '<div class="error">Failed to load dashboard data.'
        + ' Check server logs.</div>';
      return;
    }
    const summary = await summaryRes.json();
    const trends = await trendsRes.json();
    const severity = await severityRes.json();
    const domains = await domainsRes.json();

    // Update summary cards
    document.getElementById('totalScans').textContent
      = summary.total_scans ?? '-';
    document.getElementById('totalBroken').textContent
      = summary.total_broken ?? '-';
    document.getElementById('totalLinks').textContent
      = summary.total_links ?? '-';
    document.getElementById('lastScan').textContent
      = summary.last_scan_timestamp
        ? new Date(summary.last_scan_timestamp).toLocaleDateString()
        : '-';

    // Trend chart
    if (trendChartInstance) trendChartInstance.destroy();
    const trendCtx = document.getElementById('trendChart').getContext('2d');
    trendChartInstance = new Chart(trendCtx, {
      type: 'line',
      data: {
        labels: trends.map(d => d.date),
        datasets: [
          {
            label: 'Total links',
            data: trends.map(d => d.total),
            borderColor: '#0f3460',
            backgroundColor: 'rgba(15,52,96,0.1)',
            fill: true, tension: 0.3,
          },
          {
            label: 'Broken links',
            data: trends.map(d => d.broken),
            borderColor: '#e94560',
            backgroundColor: 'rgba(233,69,96,0.1)',
            fill: true, tension: 0.3,
          },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8892b0' } } },
        scales: {
          x: { ticks: { color: '#8892b0' } },
          y: { ticks: { color: '#8892b0' } },
        },
      },
    });

    // Severity pie chart
    if (severityChartInstance) severityChartInstance.destroy();
    const sevCtx = document.getElementById('severityChart').getContext('2d');
    severityChartInstance = new Chart(sevCtx, {
      type: 'pie',
      data: {
        labels: ['Critical (5xx)', 'Warning (4xx)', 'Info (other)'],
        datasets: [{
          data: [
            severity.critical || 0,
            severity.warning || 0,
            severity.info || 0,
          ],
          backgroundColor: ['#e94560', '#f5a623', '#0f3460'],
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8892b0' } } },
      },
    });

    // Domain bar chart
    if (domainChartInstance) domainChartInstance.destroy();
    const domCtx = document.getElementById('domainChart').getContext('2d');
    const topDomains = domains.slice(0, 10);
    domainChartInstance = new Chart(domCtx, {
      type: 'bar',
      data: {
        labels: topDomains.map(d => d.domain),
        datasets: [{
          label: 'Broken links',
          data: topDomains.map(d => d.count),
          backgroundColor: '#e94560',
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8892b0' } },
          y: { ticks: { color: '#8892b0' } },
        },
      },
    });
  } catch (e) {
    document.querySelector('.charts').innerHTML
      = `<div class="error">Error loading data: ${e.message}</div>`;
  }
}

let portfolioDays = 30;
let portfolioProjects = [];
let portfolioTrendChart = null;

function setPortfolioDays(days) {
  portfolioDays = days;
  document.querySelectorAll('#portfolioDays button').forEach(
    b => b.classList.remove('active')
  );
  const btn = document.querySelector(`#portfolioDays button[data-portfolio-days="${days}"]`);
  if (btn) btn.classList.add('active');
  loadPortfolio();
}

async function loadPortfolio() {
  const section = document.getElementById('portfolioSection');
  if (!section) return; // presence guard
  const cards = document.getElementById('portfolioCards');
  const canvas = document.getElementById('portfolioTrendCanvas');
  cards.innerHTML = '<p class="muted">Loading portfolio…</p>';
  try {
    const [portfolioRes, trendRes] = await Promise.all([
      fetch(`/api/portfolio${apiTokenQuery()}`),
      fetch(`/api/portfolio/summary?days=${portfolioDays}${apiTokenQuery()}`),
    ]);
    if (!portfolioRes.ok || !trendRes.ok) {
      let detail = `Could not load portfolio (HTTP ${portfolioRes.status})`;
      try {
        const err = await portfolioRes.json();
        if (err && err.detail) detail = err.detail;
      } catch (_) { /* non-JSON body */ }
      throw new Error(detail);
    }
    const data = await portfolioRes.json();
    const trendData = await trendRes.json();
    const summary = data.summary || {};
    const projects = data.projects || [];
    portfolioProjects = projects;
    if (!projects.length && !(summary.projects > 0)) {
      renderPortfolioEmpty();
      renderPortfolioTrend(null);
      return;
    }
    renderPortfolioCards(summary);
    renderPortfolioRows(projects);
    renderPortfolioTrend(trendData.trend || []);
  } catch (e) {
    renderPortfolioError(e.message || 'Could not load portfolio');
  }
}

function renderPortfolioTrend(trend) {
  const canvas = document.getElementById('portfolioTrendCanvas');
  if (!canvas) return;
  if (portfolioTrendChart) portfolioTrendChart.destroy();
  if (!trend || !trend.length) return;
  portfolioTrendChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: trend.map(d => d.date),
      datasets: [
        {
          label: 'Total links',
          data: trend.map(d => d.total_links),
          borderColor: '#0f3460',
          backgroundColor: 'rgba(15,52,96,0.1)',
          fill: true, tension: 0.3,
        },
        {
          label: 'Broken links',
          data: trend.map(d => d.broken_count),
          borderColor: '#e94560',
          backgroundColor: 'rgba(233,69,96,0.1)',
          fill: true, tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892b0' } } },
      scales: {
        x: { ticks: { color: '#8892b0' } },
        y: { ticks: { color: '#8892b0' } },
      },
    },
  });
}

function renderPortfolioCards(summary) {
  const cards = document.getElementById('portfolioCards');
  if (!cards) return;
  const broken = summary.broken_count ?? 0;
  const fixed = summary.resolved_findings ?? 0;
  const total = summary.total_links ?? 0;
  const health = (typeof summary.health_score === 'number') ? summary.health_score : 100;
  const healthTone = health >= 90 ? 'good' : (health >= 70 ? 'warn' : 'bad');
  const cardsHtml =
    `<div class="card"><div class="value">${total}</div><div class="label">Total Links</div></div>`
    + `<div class="card"><div class="value">${broken}</div><div class="label">Broken</div></div>`
    + `<div class="card"><div class="value">${fixed}</div><div class="label">Fixed</div></div>`
    + `<div class="card"><div class="value health-${healthTone}">${health}/100</div><div class="label">Health Score</div></div>`;
  cards.innerHTML = cardsHtml;
}

function renderPortfolioRows(projects) {
  const container = document.getElementById('portfolioRows');
  if (!container) return;
  if (!projects.length) {
    container.innerHTML = '<p class="muted">No saved projects yet. Save your recurring targets above.</p>';
    return;
  }
  container.innerHTML = projects.map((p) => {
    const statusTone = p.last_scan_status === 'completed' ? 'good'
      : (p.last_scan_status === 'failed' ? 'bad' : 'warn');
    const lastScan = p.last_scan_timestamp
      ? new Date(p.last_scan_timestamp).toLocaleString() : 'Never scanned';
    return `<article class="project-item"><div><strong>${escapeHtml(p.project_name)}</strong>`
      + `<span class="muted">${p.total_links} links · ${p.broken_count} broken · ${p.resolved_findings} fixed</span></div>`
      + `<div class="recent-actions"><span class="badge ${statusTone}">${escapeHtml(p.last_scan_status)}</span>`
      + `<span class="muted">last scan ${lastScan}</span></div></article>`;
  }).join('');
}

function renderPortfolioEmpty() {
  const cards = document.getElementById('portfolioCards');
  if (cards) cards.innerHTML = '<p class="muted">No saved projects yet. Save your recurring targets above.</p>';
  const rows = document.getElementById('portfolioRows');
  if (rows) rows.innerHTML = '';
  if (portfolioTrendChart) {
    portfolioTrendChart.destroy();
    portfolioTrendChart = null;
  }
}

function renderPortfolioError(detail) {
  const cards = document.getElementById('portfolioCards');
  if (!cards) return;
  cards.innerHTML = `<div class="error">Portfolio data could not be loaded: ${escapeHtml(detail)}</div>`
    + '<button type="button" class="secondary" id="portfolioRetry">Retry</button>';
  const retry = document.getElementById('portfolioRetry');
  if (retry) retry.onclick = () => { loadPortfolio(); };
}

function exportPortfolioCsv() {
  const header = 'project_name,total_links,broken_count,open_findings,resolved_findings,last_scan_timestamp';
  const rows = [header.split(',')];
  portfolioProjects.forEach((p) => {
    rows.push([
      p.project_name, p.total_links, p.broken_count,
      p.open_findings, p.resolved_findings, p.last_scan_timestamp || '',
    ]);
  });
  const csv = rows.map(row => row.map(escapeCsvCell).join(',')).join('\n') + '\n';
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'portfolio-export.csv';
  link.click();
  URL.revokeObjectURL(link.href);
}

const exportPortfolioBtn = document.getElementById('exportPortfolio');
if (exportPortfolioBtn) {
  exportPortfolioBtn.addEventListener('click', exportPortfolioCsv);
}

document.querySelectorAll('#portfolioDays button').forEach(btn => {
  btn.addEventListener('click', () => {
    const days = parseInt(btn.dataset.portfolioDays, 10);
    setPortfolioDays(days);
  });
});

let activeFinding = null; let findingTrigger = null;

async function loadJobs(){const status=document.getElementById('jobsStatus');const list=document.getElementById('jobsList');status.textContent='Loading scan jobs.';try{const r=await fetch(`/api/jobs${apiTokenQuery()}`);const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not load jobs');status.textContent=d.total?`${d.total} scan jobs`:'No project scans yet. Run a saved project to create one.';list.innerHTML=d.items.map(j=>`<li><article class="finding-card"><h3>${escapeHtml(j.project_name)} · ${escapeHtml(j.state)}</h3><p>${j.completed_count} of ${j.target_count} sources completed; ${j.failed_count} failed.</p><progress max="${j.target_count}" value="${j.completed_count+j.failed_count+j.cancelled_count}" aria-label="Job progress"></progress><p class="muted">Policy v${j.policy_version} · ${escapeHtml(j.id.slice(0,8))}</p></article></li>`).join('');}catch(e){status.textContent=`Updates paused: ${e.message}`;list.innerHTML='<li><button class="secondary" id="retryJobs">Retry</button></li>';document.getElementById('retryJobs').onclick=loadJobs;}}
async function loadFindingProjects() { const res=await fetch(`/api/projects${apiTokenQuery()}`); if(!res.ok)return; const projects=await res.json(); const select=document.getElementById('findingProject'); select.innerHTML='<option value="">Choose a project</option>'+projects.map(p=>`<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join(''); }
async function loadFindings(){ const project=document.getElementById('findingProject').value; const list=document.getElementById('findingList'); const status=document.getElementById('findingStatus'); if(!project){list.innerHTML='';status.textContent='Choose a saved project to review findings.';return;} status.textContent='Loading findings…'; const q=new URLSearchParams({project_id:project}); const state=document.getElementById('findingState').value; if(state)q.set('state',state); const classification=document.getElementById('findingClassification').value;if(classification)q.set('classification',classification);const search=document.getElementById('findingSearch').value.trim(); if(search)q.set('q',search); const token=new URLSearchParams(location.search).get('token');if(token)q.set('token',token); try{const r=await fetch(`/api/findings?${q}`);const data=await r.json();if(!r.ok)throw new Error(data.detail||'Could not load findings');status.textContent=`${data.total} findings`;list.innerHTML=data.items.length?data.items.map(f=>`<article class="finding-card"><strong>${escapeHtml(f.target_url)}</strong><p><span class="badge bad">${escapeHtml(f.state)}</span> ${escapeHtml(f.classification)} · ${escapeHtml(f.assignee||'Unassigned')}</p><button class="secondary" data-finding="${escapeHtml(f.id)}">View details</button></article>`).join(''):'<p class="muted">No confirmed broken links match these filters.</p>';list.querySelectorAll('[data-finding]').forEach(b=>b.onclick=()=>openFinding(b.dataset.finding,b));}catch(e){status.textContent=`Unable to load findings: ${e.message}`;list.innerHTML='<button class="secondary" onclick="loadFindings()">Retry</button>';}}
async function openFinding(id,trigger){findingTrigger=trigger;const token=new URLSearchParams(location.search).get('token');const r=await fetch(`/api/findings/${encodeURIComponent(id)}${token?'?token='+encodeURIComponent(token):''}`);activeFinding=await r.json();if(!r.ok)return;renderFinding();const d=document.getElementById('findingDialog');d.showModal();document.getElementById('verifyFinding').focus();}
function renderFinding(){const f=activeFinding;document.getElementById('findingDialogTitle').textContent=f.target_url;document.getElementById('findingDetail').innerHTML=`<p><strong>${escapeHtml(f.state)}</strong> · ${escapeHtml(f.classification)} · status ${escapeHtml(f.latest_status??'No response')}</p><p>${escapeHtml(f.reason)}</p><button id="verifyFinding" class="primary">Verify fix</button> <button id="ackFinding" class="secondary">Acknowledge</button> <button id="reopenFinding" class="secondary">Reopen</button><p><label for="findingAssignee">Assignee</label> <input id="findingAssignee" maxlength="120" value="${escapeHtml(f.assignee||'')}"> <button id="assignFinding" class="secondary">Save assignment</button></p><p><label for="findingIgnoreReason">Ignore reason</label> <input id="findingIgnoreReason" maxlength="500"> <label for="findingIgnoreExpiry">Expiry</label> <input id="findingIgnoreExpiry" type="date"> <button id="ignoreFinding" class="secondary">Ignore</button></p><h3>Source occurrences</h3><ul>${f.occurrences.map(o=>`<li><a target="_blank" rel="noopener noreferrer" href="${escapeHtml(o.source_url)}">${escapeHtml(o.source_url)} (opens in new tab)</a><br>${escapeHtml(o.anchor_text)} · ${escapeHtml(o.context)}</li>`).join('')}</ul><details><summary>Evidence (${f.evidence.length})</summary><ol>${f.evidence.map(e=>`<li>${escapeHtml(e.method)} ${escapeHtml(e.status??e.error)} · ${escapeHtml(e.classification)}</li>`).join('')}</ol></details><details><summary>Verification history (${f.verifications.length})</summary><ol>${f.verifications.map(v=>`<li>${escapeHtml(v.outcome)} · ${escapeHtml(v.completed_at)}</li>`).join('')}</ol></details><details><summary>Audit history (${f.audit.length})</summary><ol>${f.audit.map(a=>`<li>${escapeHtml(a.event_type)} · ${escapeHtml(a.created_at)}</li>`).join('')}</ol></details>`;document.getElementById('verifyFinding').onclick=()=>findingAction('verify');document.getElementById('ackFinding').onclick=()=>findingAction('acknowledge');document.getElementById('reopenFinding').onclick=()=>findingAction('reopen');document.getElementById('assignFinding').onclick=()=>findingAction('assignment',{assignee:document.getElementById('findingAssignee').value});document.getElementById('ignoreFinding').onclick=()=>findingAction('ignore',{reason:document.getElementById('findingIgnoreReason').value,expiry:document.getElementById('findingIgnoreExpiry').value||null});}
async function findingAction(action,extra={}){const status=document.getElementById('findingActionStatus');status.textContent=action==='verify'?'Verifying target and source pages…':'Saving…';const token=new URLSearchParams(location.search).get('token');const r=await fetch(`/api/findings/${encodeURIComponent(activeFinding.id)}/${action}${token?'?token='+encodeURIComponent(token):''}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:activeFinding.version,...extra})});const data=await r.json();if(!r.ok){status.textContent=data.detail||'Action failed';return;}activeFinding=data.finding||await (await fetch(`/api/findings/${activeFinding.id}${token?'?token='+encodeURIComponent(token):''}`)).json();const labels={acknowledge:'Finding acknowledged.',assignment:'Assignment saved.',ignore:'Finding ignored.',reopen:'Finding reopened.'};status.textContent=data.outcome?`Verification: ${data.outcome}. ${activeFinding.state==='RESOLVED'?'Finding resolved.':'State unchanged.'}`:(labels[action]||'Finding updated.');renderFinding();loadFindings();}
document.getElementById('findingProject').addEventListener('change',loadFindings);document.getElementById('findingState').addEventListener('change',loadFindings);document.getElementById('findingClassification').addEventListener('change',loadFindings);document.getElementById('findingSearch').addEventListener('input',loadFindings);document.getElementById('refreshFindings').addEventListener('click',loadFindings);document.getElementById('closeFinding').addEventListener('click',()=>{document.getElementById('findingDialog').close();if(findingTrigger)findingTrigger.focus();});

loadAll();
loadRecentTargets();
loadProjects();
loadFindingProjects();
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = _parse_query(self.path)

        if path == "/health":
            health = run_health_checks()
            status_code = 200 if health.status == "healthy" else 503
            _write_json(self, status_code, asdict(health))
            return

        if path == "/api/jobs" or path.startswith("/api/jobs/"):
            _handle_jobs_get(self, path, params)
            return

        if path.startswith("/api/projects/") and path.endswith("/scan-policy"):
            project_id = path.removeprefix("/api/projects/").removesuffix(
                "/scan-policy"
            )
            try:
                ProjectStore().get(project_id)
            except KeyError:
                _write_json(
                    self,
                    404,
                    {"code": "project_not_found", "detail": "project not found"},
                )
                return
            _write_json(self, 200, ScanPolicyStore().get(project_id))
            return

        if path == "/scan":
            _handle_scan(self, params)
            return

        # HISTORY ENDPOINTS
        if path == "/history":
            _handle_history(self, params)
            return

        if path.startswith("/api/projects/") and path.endswith("/export"):
            project_id = path.removeprefix("/api/projects/").removesuffix("/export")
            if not _require_scan_auth(self, params):
                return
            try:
                payload = ProjectStore().export_configuration(project_id)
            except KeyError:
                _write_json(
                    self,
                    404,
                    {"code": "project_not_found", "detail": "project not found"},
                )
                return
            _write_json(self, 200, payload)
            return

        if path == "/api/projects":
            if not _require_scan_auth(self, params):
                return
            store = ProjectStore()
            selected = (
                store.list_archived()
                if params.get("archived") == "1"
                else store.list_active()
            )
            history_store = HistoryStore()
            projects = []
            for item in selected:
                payload = asdict(item)
                payload["scan_summary"] = store.summarize(item, history_store)
                projects.append(payload)
            _write_json(self, 200, projects)
            return

        # TRUSTED FINDINGS ENDPOINTS
        if path == "/api/findings" or path.startswith("/api/findings/"):
            _handle_findings_get(self, path, params)
            return

        # DASHBOARD ENDPOINTS
        if path.startswith("/api/dashboard/"):
            params["_subpath"] = path[len("/api/dashboard/") :]
            _handle_dashboard(self, params)
            return

        # PORTFOLIO ENDPOINTS
        if path == "/api/portfolio" or path == "/api/portfolio/summary":
            _handle_portfolio(self, path, params)
            return

        # SCHEDULED PROJECTS ENDPOINTS
        if path == "/api/scheduled-projects":
            if not _require_scan_auth(self, params):
                return
            schedule_store = ScheduleStore()
            history_store = ScanHistoryStore()
            project_store = ProjectStore()
            schedules = schedule_store.list_active()
            projects = project_store.list_active()
            views = aggregate_scheduled_projects(
                schedules=schedules,
                projects=projects,
                scan_history_store=history_store,
            )
            _write_json(self, 200, [v.__dict__ for v in views])
            return

        if path == "/dashboard":
            body = _DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        _write_json(self, 404, {"detail": "not found"})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/projects/"):
            _write_json(self, 404, {"detail": "not found"})
            return
        params = _parse_query(self.path)
        if not _require_scan_auth(self, params):
            return
        content_length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(
                self.rfile.read(content_length) if content_length else b""
            )
        except (json.JSONDecodeError, ValueError):
            _write_json(self, 400, {"code": "invalid_json", "detail": "invalid JSON"})
            return
        targets = body.get("targets")
        if not isinstance(targets, list) or not all(
            isinstance(item, str) for item in targets
        ):
            _write_json(
                self,
                400,
                {
                    "code": "invalid_targets",
                    "detail": "targets must be a list of strings",
                },
            )
            return
        for target in targets:
            error = validate_scan_url(target)
            if error is not None:
                _write_json(
                    self,
                    400,
                    {
                        "code": "unsafe_target",
                        "detail": f"Target URL is not allowed: {error}",
                    },
                )
                return
        try:
            project = ProjectStore().update(
                path.removeprefix("/api/projects/"), str(body.get("name", "")), targets
            )
        except KeyError:
            _write_json(
                self, 404, {"code": "project_not_found", "detail": "project not found"}
            )
            return
        except ValueError as exc:
            _write_json(self, 400, {"code": "invalid_project", "detail": str(exc)})
            return
        _write_json(self, 200, asdict(project))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/projects/"):
            params = _parse_query(self.path)
            if not _require_scan_auth(self, params):
                return
            project_id = path.removeprefix("/api/projects/")
            if not project_id or "/" in project_id:
                _write_json(self, 404, {"detail": "not found"})
                return
            try:
                project = ProjectStore().archive(project_id)
            except KeyError:
                _write_json(
                    self,
                    404,
                    {"code": "project_not_found", "detail": "project not found"},
                )
                return
            _write_json(self, 200, asdict(project))
            return
        _write_json(self, 404, {"detail": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/projects/") and path.endswith("/jobs"):
            project_id = path.removeprefix("/api/projects/").removesuffix("/jobs")
            try:
                job = _jobs().create_project_job(
                    project_id, self.headers.get("Idempotency-Key")
                )
            except KeyError:
                _write_json(
                    self,
                    404,
                    {"code": "project_not_found", "detail": "project not found"},
                )
                return
            except ValueError as exc:
                _write_json(self, 400, {"code": "invalid_job", "detail": str(exc)})
                return
            _write_json(self, 202, {"job": job})
            return

        if path.startswith("/api/jobs/"):
            _handle_jobs_post(self, path)
            return

        if path.startswith("/api/projects/") and path.endswith("/scan-policy"):
            project_id = path.removeprefix("/api/projects/").removesuffix(
                "/scan-policy"
            )
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) if length else b"{}")
            try:
                result = ScanPolicyStore().save(
                    project_id,
                    body.get("version"),
                    body.get("defaults", {}),
                    body.get("host_overrides", []),
                )
            except PolicyConflict as exc:
                _write_json(self, 409, {"code": "policy_conflict", "detail": str(exc)})
                return
            except (ValueError, TypeError) as exc:
                _write_json(self, 400, {"code": "invalid_policy", "detail": str(exc)})
                return
            _write_json(self, 200, result)
            return

        if path.startswith("/api/findings/"):
            _handle_findings_post(self, path)
            return

        if path.startswith("/api/projects/") and path.endswith("/pin"):
            _handle_projects_post(self, path, "pin")
            return

        if path.startswith("/api/projects/") and path.endswith("/duplicate"):
            _handle_projects_post(self, path, "duplicate")
            return

        if path == "/api/projects/import":
            _handle_projects_post(self, path, "import")
            return

        if path.startswith("/api/projects/") and path.endswith("/restore"):
            _handle_projects_post(self, path, "restore")
            return

        if path == "/api/projects":
            _handle_projects_post(self, path, "create")
            return

        if path == "/webhooks":
            _handle_webhooks_post(self)
            return

        if path == "/scan-batch":
            _handle_scan_batch(self)
            return

        if path == "/diff":
            _handle_diff(self)
            return

        _write_json(self, 404, {"detail": "not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def _handle_jobs_get(
    handler: BaseHTTPRequestHandler,
    path: str,
    params: dict[str, str],
) -> None:
    """Handle GET /api/jobs and /api/jobs/*."""
    if not _require_scan_auth(handler, params):
        return
    try:
        if path == "/api/jobs":
            items = _jobs().jobs.list(params.get("project_id"))
            _write_json(
                handler,
                200,
                {"items": items, "total": len(items), "limit": 20, "offset": 0},
            )
        else:
            relative = path.removeprefix("/api/jobs/")
            if relative.endswith("/sources"):
                job_id = relative.removesuffix("/sources")
                _write_json(
                    handler,
                    200,
                    {"items": _jobs().jobs.sources(job_id, params.get("state"))},
                )
            else:
                _write_json(
                    handler,
                    200,
                    {
                        "job": _jobs().jobs.get(relative),
                        "sources": _jobs().jobs.sources(relative),
                    },
                )
    except KeyError:
        _write_json(handler, 404, {"code": "job_not_found", "detail": "job not found"})


def _handle_jobs_post(
    handler: BaseHTTPRequestHandler,
    path: str,
) -> None:
    """Handle POST /api/jobs/* actions (cancel, retry-failures)."""
    length = int(handler.headers.get("Content-Length", 0))
    body = json.loads(handler.rfile.read(length) if length else b"{}")
    relative = path.removeprefix("/api/jobs/")
    try:
        if relative.endswith("/cancel"):
            result = _jobs().jobs.cancel(
                relative.removesuffix("/cancel"), body.get("version")
            )
            _write_json(handler, 200, {"job": result})
        elif relative.endswith("/retry-failures"):
            jid = relative.removesuffix("/retry-failures")
            if body.get("preview", False):
                _write_json(handler, 200, _jobs().retry_preview(jid))
            else:
                _write_json(
                    handler,
                    202,
                    {
                        "job": _jobs().retry_failures(
                            jid, handler.headers.get("Idempotency-Key")
                        )
                    },
                )
        else:
            raise KeyError(relative)
    except JobConflict as exc:
        _write_json(handler, 409, {"code": "job_conflict", "detail": str(exc)})
    except KeyError:
        _write_json(handler, 404, {"code": "job_not_found", "detail": "job not found"})
    except (ValueError, TypeError) as exc:
        _write_json(handler, 400, {"code": "invalid_job_action", "detail": str(exc)})


def _handle_findings_get(
    handler: BaseHTTPRequestHandler,
    path: str,
    params: dict[str, str],
) -> None:
    """Handle GET /api/findings and /api/findings/*."""
    if not _require_scan_auth(handler, params):
        return
    store = FindingStore()
    try:
        if path == "/api/findings":
            project_id = params.get("project_id")
            if not project_id:
                raise ValueError("project_id is required")
            result = store.list(
                project_id,
                params.get("state"),
                params.get("classification"),
                params.get("q", ""),
                params.get("limit", 50),
                params.get("offset", 0),
            )
        else:
            finding_id = path.removeprefix("/api/findings/")
            if not finding_id or "/" in finding_id:
                raise KeyError(finding_id)
            result = store.detail(finding_id)
    except ValueError as exc:
        _write_json(handler, 400, {"code": "invalid_finding_query", "detail": str(exc)})
        return
    except KeyError:
        _write_json(
            handler, 404, {"code": "finding_not_found", "detail": "finding not found"}
        )
        return
    _write_json(handler, 200, result)


def _handle_findings_post(
    handler: BaseHTTPRequestHandler,
    path: str,
) -> None:
    """Handle POST /api/findings/* (acknowledge, assign, ignore, reopen, verify)."""
    params = _parse_query(path)
    if not _require_scan_auth(handler, params):
        return
    body = _read_json_body(handler)
    if body is None:
        return
    try:
        if not isinstance(body.get("version"), int):
            raise ValueError("version integer is required")
        relative = path.removeprefix("/api/findings/")
        finding_id, action = relative.rsplit("/", 1)
        store = FindingStore()
        if action == "acknowledge":
            result = store.acknowledge(finding_id, body["version"])
        elif action == "assignment":
            result = store.assign(finding_id, body["version"], body.get("assignee"))
        elif action == "ignore":
            result = store.ignore(
                finding_id,
                body["version"],
                str(body.get("reason", "")),
                body.get("expiry"),
            )
        elif action == "reopen":
            result = store.reopen(finding_id, body["version"])
        elif action == "verify":
            result = _verify_finding(store, finding_id, body["version"])
        else:
            raise KeyError(action)
    except VersionConflictError as exc:
        _write_json(
            handler, 409, {"code": "finding_version_conflict", "detail": str(exc)}
        )
        return
    except KeyError:
        _write_json(
            handler,
            404,
            {"code": "finding_not_found", "detail": "finding or action not found"},
        )
        return
    except (ValueError, TypeError) as exc:
        _write_json(
            handler, 400, {"code": "invalid_finding_action", "detail": str(exc)}
        )
        return
    _write_json(handler, 200, result)


def _verify_finding(
    store: FindingStore,
    finding_id: str,
    version: int,
) -> Any:
    """Re-scan a finding's target and sources, then verify it via the service."""
    detail = store.detail(finding_id)
    project = ProjectStore().get(detail["project_id"])
    if project.archived:
        raise ValueError("archived projects are read-only")
    target_error = validate_scan_url(detail["target_url"])
    if target_error is not None:
        raise ValueError(f"Target URL is not allowed: {target_error}")
    source_bodies = {}
    for item in detail["occurrences"]:
        if not item["active"]:
            continue
        source_error = validate_scan_url(item["source_url"])
        if source_error is not None:
            raise ValueError(f"Source URL is not allowed: {source_error}")
        source_bodies[item["source_url"]] = fetch_html(item["source_url"])
    target = scan_link_detailed(detail["target_url"])
    return FindingService(store).verify(
        finding_id,
        version,
        list(target.attempts),
        source_bodies,
    )


def _handle_portfolio(
    handler: BaseHTTPRequestHandler,
    path: str,
    params: dict[str, str],
) -> None:
    """Handle GET /api/portfolio and /api/portfolio/summary."""
    if not _require_scan_auth(handler, params):
        return

    project_ids: list[str] | None = None
    if params.get("project_ids"):
        project_ids = [
            item.strip() for item in params["project_ids"].split(",") if item.strip()
        ]

    project_store = ProjectStore()
    history_db = sqlite3.connect(project_store.path, timeout=10)
    history_db.row_factory = sqlite3.Row
    try:
        if path == "/api/portfolio":
            rows = get_portfolio_rows(
                project_ids=project_ids,
                project_store=project_store,
                history_db=history_db,
                finding_store=FindingStore(),
            )
            summary = get_portfolio(
                project_ids=project_ids,
                project_store=project_store,
                history_db=history_db,
                finding_store=FindingStore(),
            )
            _write_json(
                handler,
                200,
                {
                    "summary": asdict(summary),
                    "projects": portfolio_rows_to_dicts(rows),
                },
            )
        else:  # /api/portfolio/summary
            try:
                days = int(params.get("days", "30"))
            except (ValueError, TypeError):
                days = 30
            # Clamp to a safe range so an out-of-range day count can't
            # reach timedelta(days=...) and overflow (huge int raises
            # OverflowError -> unhandled 500). days <= 0 -> all history
            # is preserved by get_portfolio_trends.
            days = max(0, min(days, 3650))
            summary = get_portfolio(
                project_ids=project_ids,
                project_store=project_store,
                history_db=history_db,
                finding_store=FindingStore(),
            )
            trend = get_portfolio_trends(
                project_ids=project_ids,
                days=days,
                project_store=project_store,
                history_db=history_db,
            )
            _write_json(
                handler,
                200,
                {
                    "summary": asdict(summary),
                    "trend": [asdict(point) for point in trend],
                },
            )
    finally:
        history_db.close()


def _handle_webhooks_post(handler: BaseHTTPRequestHandler) -> None:
    """Handle POST /webhooks (register a webhook URL)."""
    if not _require_scan_auth(handler, {}):
        return
    body = _read_json_body(handler)
    if body is None:
        return

    url = body.get("url")
    if not url:
        _write_json(handler, 400, {"detail": "missing url field"})
        return

    secret = body.get("secret")

    # Check duplicate
    existing = _webhook_registry.find_by_url(url)
    if existing is not None:
        _write_json(handler, 409, {"detail": "URL already registered"})
        return

    # Register
    try:
        reg = _webhook_registry.register(url, secret=secret)
    except ValueError as exc:
        _write_json(handler, 400, {"detail": str(exc)})
        return

    _write_json(handler, 201, {"id": reg.id, "url": reg.url})


def _handle_scan_batch(handler: BaseHTTPRequestHandler) -> None:
    """Handle POST /scan-batch."""
    params = _parse_query(handler.path)
    if not _require_scan_auth(handler, params):
        return
    body = _read_json_body(handler)
    if body is None:
        return

    urls = body.get("urls")
    if not isinstance(urls, list) or len(urls) == 0:
        _write_json(handler, 400, {"detail": "urls must be a non-empty list"})
        return

    # Reject duplicates
    if len(urls) != len(set(urls)):
        _write_json(handler, 400, {"detail": "duplicate URLs in request"})
        return

    # Reject >50 URLs
    if len(urls) > 50:
        _write_json(handler, 400, {"detail": "maximum 50 URLs per batch request"})
        return

    # SSRF validation
    for url in urls:
        error = validate_scan_url(url)
        if error is not None:
            _write_json(handler, 400, {"detail": f"SSRF blocked: {url} - {error}"})
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
    for url in urls:
        if url in batch_results:
            _record_scan_and_notify(url, batch_results[url])

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
        _write_csv(handler, render_csv(all_results))
        return
    if response_format and response_format.lower() == "markdown":
        _write_markdown(handler, render_markdown(all_results))
        return
    if response_format and response_format.lower() == "jsonl":
        _write_jsonl(handler, render_jsonl(all_results))
        return

    # Default: JSON with results and summary
    serializable = {
        url: [r.__dict__ for r in results] for url, results in batch_results.items()
    }
    summary = {
        "total_urls": len(urls),
        "broken_count": broken_count,
        "latency_seconds": round(latency, 6),
    }
    _write_json(handler, 200, {"results": serializable, "summary": summary})


def _handle_diff(handler: BaseHTTPRequestHandler) -> None:
    """Handle POST /diff."""
    params = _parse_query(handler.path)
    if not _require_scan_auth(handler, params):
        return
    body = _read_json_body(handler)
    if body is None:
        return

    previous = body.get("previous")
    current = body.get("current")
    if not previous or not current:
        _write_json(handler, 400, {"detail": "missing previous or current in request"})
        return

    diff_result = compute_diff(previous, current)
    _write_json(handler, 200, diff_result)


def _handle_projects_post(
    handler: BaseHTTPRequestHandler,
    path: str,
    action: str,
) -> None:
    """Handle POST /api/projects* project-management actions."""
    params = _parse_query(path)
    if not _require_scan_auth(handler, params):
        return
    try:
        if action == "pin":
            body = _read_json_body(handler)
            if body is None:
                return
            if not isinstance(body.get("pinned"), bool):
                _write_json(
                    handler,
                    400,
                    {"code": "invalid_pinned", "detail": "pinned must be a boolean"},
                )
                return
            project_id = path.removeprefix("/api/projects/").removesuffix("/pin")
            project = ProjectStore().set_pinned(project_id, body["pinned"])
            status = 200
        elif action == "duplicate":
            project_id = path.removeprefix("/api/projects/").removesuffix("/duplicate")
            project = ProjectStore().duplicate(project_id)
            status = 201
        elif action == "import":
            body = _read_json_body(handler)
            if body is None:
                return
            if not isinstance(body, dict):
                _write_json(
                    handler,
                    400,
                    {
                        "code": "invalid_project",
                        "detail": "project configuration must be an object",
                    },
                )
                return
            if not _validate_targets(handler, body.get("targets")):
                return
            project = ProjectStore().import_configuration(body)
            status = 201
        elif action == "restore":
            project_id = path.removeprefix("/api/projects/").removesuffix("/restore")
            project = ProjectStore().restore(project_id)
            status = 200
        elif action == "create":
            body = _read_json_body(handler)
            if body is None:
                return
            if not _validate_targets(handler, body.get("targets")):
                return
            project = ProjectStore().create(str(body.get("name", "")), body["targets"])
            status = 201
        else:
            raise KeyError(action)
    except KeyError:
        _write_json(
            handler,
            404,
            {"code": "project_not_found", "detail": "project not found"},
        )
        return
    except ValueError as exc:
        _write_json(handler, 400, {"code": "invalid_project", "detail": str(exc)})
        return
    _write_json(handler, status, asdict(project))


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
