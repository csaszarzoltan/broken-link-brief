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
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from brokenlinkbrief import __version__
from brokenlinkbrief.notifications import NotifierConfig, RateLimiter, notify_all
from brokenlinkbrief.package import (
    HistoryStore,
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
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.regression_detector import RegressionDetector
from brokenlinkbrief.scan_history import ScanHistoryStore
from brokenlinkbrief.scheduled_projects import aggregate_scheduled_projects
from brokenlinkbrief.scheduler import ScheduleStore
from brokenlinkbrief.spa_scanner import SpaScanner
from brokenlinkbrief.webhook import WebhookRegistry, trigger_webhooks

_AUTH_DETAIL = "missing or invalid scan token"
_LOG_TOKEN_ENV = "BROKENLINKBRIEF_LOG_FILE"
_webhook_registry = WebhookRegistry()
_notifier_config = NotifierConfig.from_env()
_rate_limiter = RateLimiter(capacity=10, fill_rate=0.1667)  # ~10 per 60s


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

loadAll();
loadRecentTargets();
loadProjects();
</script>
</body>
</html>"""


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

            validation_error = validate_scan_url(target_url)
            if validation_error is not None:
                _write_json(self, 400, {
                    "code": "unsafe_target",
                    "detail": f"Target URL is not allowed: {validation_error}",
                })
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

            # Record scan and trigger webhooks only on changes
            import threading

            # Record this scan in history
            record_scan(scan_results, target_url)

            # Get previous scan for comparison
            history = get_history(target_url, limit=2)
            if len(history) >= 2:
                previous_results = history[1].get("results", [])
                current_results = [
                    {"url": r.url, "status": r.status} for r in scan_results
                ]
                diff = compute_diff(previous_results, current_results)
                # Run regression detection on diffs with new broken links
                if diff.get("added_broken"):
                    regression_detector = RegressionDetector()
                    scan_history_for_detector = [
                        {
                            "scan_id": "prev",
                            "status": "completed",
                            "scan_timestamp": history[1].get("timestamp", ""),
                            "raw_results": {
                                target_url: [
                                    {"url": r.get("url"), "status": r.get("status")}
                                    for r in previous_results
                                ]
                            },
                        }
                    ]
                    regression_report = regression_detector.detect(
                        project_id="default",
                        current_results={
                            target_url: [
                                {"url": r.url, "status": r.status}
                                for r in scan_results
                            ]
                        },
                        scan_history=scan_history_for_detector,
                    )
                    if regression_report.has_regressions:
                        # Log regression detection (notification handled by
                        # the existing notify_all path below)
                        pass
                # Only fire webhooks if there are changes
                if diff.get("added_broken") or diff.get("fixed"):
                    def _fire_webhooks() -> None:
                        trigger_webhooks(_webhook_registry, target_url, scan_results)

                    threading.Thread(target=_fire_webhooks, daemon=True).start()
                    # Notify synchronously after webhook trigger
                    notify_all(
                        _notifier_config, scan_results, target_url, _rate_limiter
                    )
            elif scan_results:
                # First scan with broken links - fire webhooks
                broken = [r for r in scan_results if r.status and r.status >= 400]
                if broken:
                    def _fire_webhooks() -> None:
                        trigger_webhooks(_webhook_registry, target_url, scan_results)

                    threading.Thread(target=_fire_webhooks, daemon=True).start()
                    # Notify synchronously after webhook trigger
                    notify_all(
                        _notifier_config, scan_results, target_url, _rate_limiter
                    )

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

        if path.startswith("/api/projects/") and path.endswith("/export"):
            project_id = path.removeprefix("/api/projects/").removesuffix("/export")
            expected_token = get_configured_scan_token()
            provided_token = params.get("token")
            authorization = self.headers.get("Authorization") or ""
            if provided_token is None and authorization.startswith("Bearer "):
                provided_token = authorization.split(" ", 1)[1]
            if expected_token is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            try:
                payload = ProjectStore().export_configuration(project_id)
            except KeyError:
                _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
                return
            _write_json(self, 200, payload)
            return

        if path == "/api/projects":
            expected_token = get_configured_scan_token()
            provided_token = params.get("token")
            if provided_token is None and "Authorization" in self.headers:
                authorization = self.headers.get("Authorization") or ""
                if authorization.startswith("Bearer "):
                    provided_token = authorization.split(" ", 1)[1]
            if expected_token is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
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

        # DASHBOARD ENDPOINTS
        if path.startswith("/api/dashboard/"):
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

            store = HistoryStore()
            subpath = path[len("/api/dashboard/"):]

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
                _write_json(self, 200, result)
                return

            if subpath == "trends":
                try:
                    days = int(params.get("days", "7"))
                except (ValueError, TypeError):
                    days = 7
                result = store.get_trend_data(days=days)
                _write_json(self, 200, result)
                return

            if subpath == "severity":
                try:
                    days = int(params.get("days", "7"))
                except (ValueError, TypeError):
                    days = 7
                result = store.get_severity_breakdown(days=days)
                _write_json(self, 200, result)
                return

            if subpath == "target-history":
                target_url = params.get("url")
                if not target_url:
                    _write_json(self, 400, {
                        "code": "missing_url",
                        "detail": "missing url query parameter",
                    })
                    return
                try:
                    limit = min(50, max(1, int(params.get("limit", "20"))))
                except (ValueError, TypeError):
                    limit = 20
                result = store.get_target_timeline(target_url, limit=limit)
                _write_json(self, 200, result)
                return

            if subpath == "recent-targets":
                try:
                    limit = min(50, max(1, int(params.get("limit", "10"))))
                except (ValueError, TypeError):
                    limit = 10
                _write_json(self, 200, store.get_recent_targets(limit=limit))
                return

            if subpath == "domains":
                try:
                    days = int(params.get("days", "7"))
                except (ValueError, TypeError):
                    days = 7
                result = store.get_domain_breakdown(days=days)
                _write_json(self, 200, result)
                return

            _write_json(self, 404, {"detail": "not found"})
            return

        # SCHEDULED PROJECTS ENDPOINTS
        if path == "/api/scheduled-projects":
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
            html = _DASHBOARD_HTML
            body = html.encode("utf-8")
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
        params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
        provided_token = params.get("token")
        authorization = self.headers.get("Authorization") or ""
        if provided_token is None and authorization.startswith("Bearer "):
            provided_token = authorization.split(" ", 1)[1]
        if get_configured_scan_token() is not None and not is_scan_authorized(provided_token):
            _write_json(self, 401, {"detail": _AUTH_DETAIL})
            return
        content_length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(content_length) if content_length else b"")
        except (json.JSONDecodeError, ValueError):
            _write_json(self, 400, {"code": "invalid_json", "detail": "invalid JSON"})
            return
        targets = body.get("targets")
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            _write_json(self, 400, {"code": "invalid_targets", "detail": "targets must be a list of strings"})
            return
        for target in targets:
            error = validate_scan_url(target)
            if error is not None:
                _write_json(self, 400, {"code": "unsafe_target", "detail": f"Target URL is not allowed: {error}"})
                return
        try:
            project = ProjectStore().update(path.removeprefix("/api/projects/"), str(body.get("name", "")), targets)
        except KeyError:
            _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
            return
        except ValueError as exc:
            _write_json(self, 400, {"code": "invalid_project", "detail": str(exc)})
            return
        _write_json(self, 200, asdict(project))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/projects/"):
            params = {
                key: values[0]
                for key, values in parse_qs(parsed.query).items()
                if values
            }
            expected_token = get_configured_scan_token()
            provided_token = params.get("token")
            if provided_token is None and "Authorization" in self.headers:
                authorization = self.headers.get("Authorization") or ""
                if authorization.startswith("Bearer "):
                    provided_token = authorization.split(" ", 1)[1]
            if expected_token is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            project_id = path.removeprefix("/api/projects/")
            if not project_id or "/" in project_id:
                _write_json(self, 404, {"detail": "not found"})
                return
            try:
                project = ProjectStore().archive(project_id)
            except KeyError:
                _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
                return
            _write_json(self, 200, asdict(project))
            return
        _write_json(self, 404, {"detail": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/projects/") and path.endswith("/pin"):
            params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            provided_token = params.get("token")
            authorization = self.headers.get("Authorization") or ""
            if provided_token is None and authorization.startswith("Bearer "):
                provided_token = authorization.split(" ", 1)[1]
            if get_configured_scan_token() is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            content_length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(content_length) if content_length else b"")
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"code": "invalid_json", "detail": "invalid JSON"})
                return
            if not isinstance(body, dict) or not isinstance(body.get("pinned"), bool):
                _write_json(self, 400, {"code": "invalid_pinned", "detail": "pinned must be a boolean"})
                return
            project_id = path.removeprefix("/api/projects/").removesuffix("/pin")
            try:
                project = ProjectStore().set_pinned(project_id, body["pinned"])
            except KeyError:
                _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
                return
            _write_json(self, 200, asdict(project))
            return

        if path.startswith("/api/projects/") and path.endswith("/duplicate"):
            params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            provided_token = params.get("token")
            authorization = self.headers.get("Authorization") or ""
            if provided_token is None and authorization.startswith("Bearer "):
                provided_token = authorization.split(" ", 1)[1]
            if get_configured_scan_token() is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            project_id = path.removeprefix("/api/projects/").removesuffix("/duplicate")
            try:
                project = ProjectStore().duplicate(project_id)
            except KeyError:
                _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
                return
            _write_json(self, 201, asdict(project))
            return

        if path == "/api/projects/import":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            provided_token = params.get("token")
            authorization = self.headers.get("Authorization") or ""
            if provided_token is None and authorization.startswith("Bearer "):
                provided_token = authorization.split(" ", 1)[1]
            if get_configured_scan_token() is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            content_length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(content_length) if content_length else b"")
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"code": "invalid_json", "detail": "invalid JSON"})
                return
            if not isinstance(body, dict):
                _write_json(self, 400, {"code": "invalid_project", "detail": "project configuration must be an object"})
                return
            targets = body.get("targets")
            if isinstance(targets, list):
                for target in targets:
                    if not isinstance(target, str):
                        _write_json(self, 400, {"code": "invalid_target", "detail": "every target must be a string"})
                        return
                    error = validate_scan_url(target)
                    if error is not None:
                        _write_json(self, 400, {"code": "unsafe_target", "detail": f"Target URL is not allowed: {error}"})
                        return
            try:
                project = ProjectStore().import_configuration(body)
            except ValueError as exc:
                _write_json(self, 400, {"code": "invalid_project", "detail": str(exc)})
                return
            _write_json(self, 201, asdict(project))
            return

        if path.startswith("/api/projects/") and path.endswith("/restore"):
            params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            provided_token = params.get("token")
            authorization = self.headers.get("Authorization") or ""
            if provided_token is None and authorization.startswith("Bearer "):
                provided_token = authorization.split(" ", 1)[1]
            if get_configured_scan_token() is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            project_id = path.removeprefix("/api/projects/").removesuffix("/restore")
            try:
                project = ProjectStore().restore(project_id)
            except KeyError:
                _write_json(self, 404, {"code": "project_not_found", "detail": "project not found"})
                return
            _write_json(self, 200, asdict(project))
            return

        if path == "/api/projects":
            expected_token = get_configured_scan_token()
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
            if expected_token is not None and not is_scan_authorized(provided_token):
                _write_json(self, 401, {"detail": _AUTH_DETAIL})
                return
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b""
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError):
                _write_json(self, 400, {"code": "invalid_json", "detail": "invalid JSON"})
                return
            targets = body.get("targets")
            if not isinstance(targets, list):
                _write_json(self, 400, {"code": "invalid_targets", "detail": "targets must be a list"})
                return
            for target in targets:
                if not isinstance(target, str):
                    _write_json(self, 400, {"code": "invalid_target", "detail": "every target must be a string"})
                    return
                error = validate_scan_url(target)
                if error is not None:
                    _write_json(self, 400, {"code": "unsafe_target", "detail": f"Target URL is not allowed: {error}"})
                    return
            try:
                project = ProjectStore().create(str(body.get("name", "")), targets)
            except ValueError as exc:
                _write_json(self, 400, {"code": "invalid_project", "detail": str(exc)})
                return
            _write_json(self, 201, asdict(project))
            return

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
                        current_results = [
                            {"url": r.url, "status": r.status}
                            for r in results
                        ]
                        diff = compute_diff(previous_results, current_results)
                        if diff.get("added_broken") or diff.get("fixed"):
                            def _fire_webhooks(u=url, r=results) -> None:
                                trigger_webhooks(_webhook_registry, u, r)

                            threading.Thread(target=_fire_webhooks, daemon=True).start()
                            # Notify synchronously after webhook trigger
                            notify_all(_notifier_config, results, url, _rate_limiter)
                    elif results:
                        # First scan with broken links - fire webhooks
                        broken = [r for r in results if r.status and r.status >= 400]
                        if broken:
                            def _fire_webhooks(u=url, r=results) -> None:
                                trigger_webhooks(_webhook_registry, u, r)

                            threading.Thread(target=_fire_webhooks, daemon=True).start()
                            # Notify synchronously after webhook trigger
                            notify_all(_notifier_config, results, url, _rate_limiter)

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
                _write_json(
                    self, 400,
                    {"detail": "missing previous or current in request"},
                )
                return

            diff_result = compute_diff(previous, current)
            _write_json(self, 200, diff_result)
            return

        _write_json(self, 404, {"detail": "not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
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
