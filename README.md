# BrokenLinkBrief

A compact stdlib-based service that scans a page for links, checks their HTTP status, and exports a shareable brief (JSON, CSV, markdown, or JSONL).

## Features

- 🔍 Scan any webpage for broken links
- 📊 Export as JSON, CSV, Markdown, or JSONL
- ⚡ Batch scanning — check up to 50 URLs in parallel in a single request
- 🕐 **SPA scanning** — JavaScript-rendered link detection via Playwright for SPAs and dynamic pages
- 🔗 **Link diff engine** — compare scans to detect new broken, resolved, and status-changed links
- 🔔 **Diff alerts** — email/Slack notifications when link state changes are detected
- 🔔 Webhook notifications when broken links are found
- 📧 Email notifications via SMTP when broken links are detected
- 💬 Slack integration via Incoming Webhooks
- 🕐 **Scheduled scanning** — cron-based recurring scans with SQLite persistence and regression detection
- 🔄 **Regression detection** — compare scans to surface newly broken links
- 🔒 Optional token-based authentication
- 📝 JSONL usage logging for analytics
- 🛡️ SSRF protection for URL validation

## Quick Start

```bash
# Install
pip install -e .

# Optional: SPA scanning (JavaScript-rendered pages)
pip install -e ".[playwright]"
playwright install chromium

# Run
python -m brokenlinkbrief.app

# Scan a page
curl "http://127.0.0.1:8000/scan?url=https://example.com"

# SPA scan (renders JavaScript first)
curl "http://127.0.0.1:8000/scan?url=https://example.com&render_js=true"
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Smoke test |
| GET | `/scan?url=<target>` | Optional | JSON results (default) |
| GET | `/scan?url=<target>&render_js=true` | Optional | SPA scan — render JavaScript before extracting links |
| GET | `/scan?url=<target>&format=csv` | Optional | CSV export |
| GET | `/scan?url=<target>&format=markdown` | Optional | Markdown brief |
| GET | `/scan?url=<target>&format=jsonl` | Optional | JSON Lines |
| POST | `/scan-batch` | Optional | Batch scan up to 50 URLs |
| POST | `/webhooks` | Required | Register a webhook URL |
| GET | `/webhooks` | Required | List registered webhooks |
| DELETE | `/webhooks/<id>` | Required | Remove a webhook |

## Batch Scanning

Scan multiple pages for broken links in a single request. All URLs are checked concurrently using a thread pool, with results returned per-URL and as an aggregated summary.

### Basic Usage

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com", "https://httpstat.us/404"]}'
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `urls` | `list[string]` | Yes | URLs to scan (1–50 unique URLs) |
| `concurrency` | `int` | No | Max parallel workers (default 10, max 20) |
| `format` | `string` | No | Output format: `json` (default), `csv`, `markdown`, `jsonl` |

### Response Format (JSON)

The default JSON response contains per-URL results and an aggregated summary:

```json
{
  "results": {
    "https://example.com": [
      {
        "url": "https://example.com/link1",
        "status": 200,
        "reason": "OK",
        "location": null
      }
    ],
    "https://httpstat.us/404": [
      {
        "url": "https://httpstat.us/404",
        "status": 404,
        "reason": "Not Found",
        "location": null
      }
    ]
  },
  "summary": {
    "total_urls": 2,
    "broken_count": 1,
    "latency_seconds": 1.234
  }
}
```

Each value under `results` is an array of `LinkResult` objects for that URL (one per discovered link on the page).

### Concurrency Control

Control how many URLs are scanned in parallel by setting `concurrency` in the request body:

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "concurrency": 5}'
```

The `concurrency` value is capped at 20. If omitted, defaults to 10.

### Output Formats

Batch scans support the same output formats as single scans. For non-JSON formats, results from all URLs are flattened into a single table:

```bash
# CSV output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "csv"}'

# Markdown output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "markdown"}'

# JSONL output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "jsonl"}'
```

### Authentication

If `BROKENLINKBRIEF_SCAN_TOKEN` is set, pass the token as an `Authorization` header or a `token` query parameter:

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ***" \
  -d '{"urls": ["https://example.com"]}'
```

### Error Responses

| Status | Condition |
|--------|-----------|
| 400 | Missing `urls` field, empty list, duplicate URLs, >50 URLs, or SSRF-blocked URL |
| 401 | Missing or invalid token (when `BROKENLINKBRIEF_SCAN_TOKEN` is set) |

Example error:

```json
{
  "detail": "duplicate URLs in request"
}
```

## SPA Scanning

For pages that rely on client-side JavaScript to render links (single-page applications, React/Vue/Angular apps), BrokenLinkBrief can use **Playwright** to render the page before extracting links.

### Installation

```bash
pip install -e ".[playwright]"
playwright install chromium
```

### Usage

Add `render_js=true` to any scan request:

```bash
curl "http://127.0.0.1:8000/scan?url=https://your-spa.com&render_js=true"
```

Without Playwright installed, the server falls back to raw HTML extraction (regex-based, no JavaScript rendering).

### How It Works

1. Playwright launches a headless Chromium browser
2. The page is loaded with `wait_until="networkidle"` (30s timeout)
3. Links are extracted from the fully rendered DOM
4. Results are merged with raw-HTML extraction — no duplicates

### When to Use SPA Scanning

| Scenario | `render_js` |
|----------|-------------|
| Static HTML pages | `false` (default) |
| Pages with `<a>` tags in server HTML | `false` (default) |
| React/Vue/Angular apps | `true` |
| Pages using `document.createElement('a')` | `true` |
| JavaScript-injected navigation | `true` |

### Programmatic Usage

```python
from brokenlinkbrief.spa_scanner import SpaScanner

scanner = SpaScanner(headless=True)
results = scanner.scan_page("https://your-spa.com", render_js=True)

for link in results:
    print(f"{link.url} → {link.status}")
```

### Limitations

- Requires Playwright and Chromium (~300 MB disk)
- JavaScript rendering adds 2–10 seconds per page
- Pages with auth walls or CAPTCHAs may not render correctly
- Playwright failures return a single `playwright-error` result (scan does not crash)

See [`docs/spa-scanning.md`](docs/spa-scanning.md) for the full reference.

## Link Diff Engine

The link diff engine compares current scan results against persisted link state to detect changes between scans.

### What It Detects

| Change Type | Description |
|-------------|-------------|
| **New broken** | Links that were previously healthy but now return errors |
| **Resolved** | Links that were broken but are now healthy |
| **Status changes** | Links whose HTTP status changed (e.g. 301 → 200) |
| **New links** | Links discovered in the current scan that weren't in the previous scan |
| **Removed links** | Links present in the previous scan but missing now |

### Configuration

Link state is persisted in SQLite via `LinkStateStore`. Set a persistent database path:

```bash
export BROKENLINKBRIEF_PROJECT_DB=/data/brokenlinkbrief.db
```

### Diff Alerts

When link state changes are detected, BrokenLinkBrief can send alerts via email or Slack. Alerts are triggered automatically during scheduled scans that use the diff engine.

```python
from brokenlinkbrief.diff_detector import DiffDetector
from brokenlinkbrief.diff_alerts import DiffNotificationTemplates

# Compare current scan against stored state
detector = DiffDetector(link_state_store)
report = detector.compare(project_id, target_url, current_links)

if report.has_changes:
    alert_text = DiffNotificationTemplates.render_diff_alert(report)
    print(alert_text)
```

### Programmatic Usage

```python
from brokenlinkbrief.link_state import LinkStateStore
from brokenlinkbrief.diff_detector import DiffDetector

store = LinkStateStore(db_connection)
detector = DiffDetector(store)

# Upsert link state from a scan
store.upsert_links(project_id, target_url, links, scan_mode="static")

# Compare against previous state
report = detector.compare(project_id, target_url, current_links)

print(f"New broken: {len(report.new_broken)}")
print(f"Resolved: {len(report.resolved)}")
print(f"Status changes: {len(report.status_changes)}")
```

## Authentication

Set `BROKENLINKBRIEF_SCAN_TOKEN` to require a matching token on `/scan`, `/scan-batch`, and `/webhooks`.

## Webhook Notifications

Register an HTTPS webhook URL to receive notifications when broken links are detected during scans.

### Register a Webhook

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ***" \
  -d '{"url": "https://your-server.com/webhook", "secret": "optional-hmac-secret"}'
```

Response (201 Created):
```json
{
  "id": "a1b2c3d4e5f6",
  "url": "https://your-server.com/webhook"
}
```

### Payload Schema

When broken links are found, a POST request is sent to your webhook URL with this JSON payload:

```json
{
  "scanned_url": "https://example.com",
  "broken_links": [
    {
      "url": "https://example.com/missing",
      "status": 404,
      "reason": "Not Found"
    }
  ],
  "timestamp": "2026-07-21T12:00:00+00:00",
  "total_links": 42
}
```

### Verifying Signatures

If you provided a `secret` when registering the webhook, every delivery includes an `X-Webhook-Signature` header containing an HMAC-SHA256 hex digest of the payload.

Verify the signature in Python:

```python
import hmac
import hashlib

def verify_webhook_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """Timing-safe verification of webhook signature."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Retry Behavior

Failed webhook deliveries are retried up to 3 times with exponential backoff:
- Attempt 1: immediate
- Attempt 2: 1 second delay
- Attempt 3: 2 seconds delay

If all attempts fail, the error is logged but does not affect the scan result.

### Security

- Only HTTPS webhook URLs are accepted (HTTP is rejected)
- Private IPs, loopback addresses, and link-local addresses are blocked (SSRF protection)
- HMAC signatures use timing-safe comparison (`hmac.compare_digest`)
- Webhook target responses are discarded (not trusted)

## Email / Slack Notifications

BrokenLinkBrief can send scan result notifications via **Email (SMTP)** and/or **Slack (Incoming Webhooks)**. Both channels are configured through environment variables and are automatically triggered after every `/scan` and `/scan-batch` call that finds broken links.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKENLINKBRIEF_SMTP_HOST` | — | SMTP server hostname (required for email) |
| `BROKENLINKBRIEF_SMTP_PORT` | `587` | SMTP port (465 = SSL, 587 = STARTTLS, 25 = plain) |
| `BROKENLINKBRIEF_SMTP_USER` | — | SMTP authentication username (required for email) |
| `BROKENLINKBRIEF_SMTP_PASSWORD` | — | SMTP authentication password (required for email) |
| `BROKENLINKBRIEF_SMTP_FROM` | — | Sender email address (required for email) |
| `BROKENLINKBRIEF_SLACK_WEBHOOK_URL` | — | Slack Incoming Webhook URL (required for Slack) |
| `BROKENLINKBRIEF_NOTIFY_ON` | `critical,warning,info` | Comma-separated severity levels that trigger notifications |
| `BROKENLINKBRIEF_NOTIFY_RATE_LIMIT` | `10` | Max notifications per rate interval per scanned URL |
| `BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL` | `60` | Rate limit window in seconds |

### Email Notification Setup

1. Set SMTP environment variables for your email provider.

   **Gmail (App Password):**
   ```bash
   export BROKENLINKBRIEF_SMTP_HOST=smtp.gmail.com
   export BROKENLINKBRIEF_SMTP_PORT=587
   export BROKENLINKBRIEF_SMTP_USER=your@gmail.com
   export BROKENLINKBRIEF_SMTP_PASSWORD=your-app-password
   export BROKENLINKBRIEF_SMTP_FROM=your@gmail.com
   ```

   **SendGrid:**
   ```bash
   export BROKENLINKBRIEF_SMTP_HOST=smtp.sendgrid.net
   export BROKENLINKBRIEF_SMTP_PORT=587
   export BROKENLINKBRIEF_SMTP_USER=apikey
   export BROKENLINKBRIEF_SMTP_PASSWORD=SG.your-api-key
   export BROKENLINKBRIEF_SMTP_FROM=alerts@yourdomain.com
   ```

2. Start the server — notifications are sent automatically when broken links are found.

3. Email recipients are set to the same address as `BROKENLINKBRIEF_SMTP_FROM` (monitoring best practice). The subject line is formatted as `BrokenLinkBrief Report: <scanned_url>`.

### Slack Webhook Setup

1. Create a Slack Incoming Webhook:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → Incoming Webhooks
   - Activate the webhook and copy the URL
   - The URL looks like: `https://hooks.slack.com/services/T00/B00/xxxxx`

2. Set the environment variable:
   ```bash
   export BROKENLINKBRIEF_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx
   ```

3. Start the server — Slack messages are posted automatically when broken links are found.

### Notification Templates & Severity Levels

Severity is automatically assigned based on HTTP status codes:

| Status Range | Severity | Emoji  |
|--------------|----------|--------|
| 5xx          | critical | 🔴     |
| 4xx          | warning  | 🟡     |
| 3xx / 2xx    | info     | 🟢     |

The notification includes:

- URL scanned and timestamp
- Total links checked
- Broken links grouped by severity with details (URL, status code, reason)

Control which severities trigger notifications with `BROKENLINKBRIEF_NOTIFY_ON`:

```bash
# Only critical errors
export BROKENLINKBRIEF_NOTIFY_ON=critical

# Critical and warnings (no info)
export BROKENLINKBRIEF_NOTIFY_ON=critical,warning
```

### Rate Limiting

Notifications use a token-bucket rate limiter per scanned URL to prevent flooding.

- **Default**: 10 notifications per 60 seconds per URL
- Configure via `BROKENLINKBRIEF_NOTIFY_RATE_LIMIT` (burst capacity) and `BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL` (window in seconds)
- When the rate limit is hit, all channels are silently skipped for that URL until tokens refill

### Quick Start with Notifications

```bash
# Start the server with email and Slack configured
export BROKENLINKBRIEF_SMTP_HOST=smtp.gmail.com
export BROKENLINKBRIEF_SMTP_PORT=587
export BROKENLINKBRIEF_SMTP_USER=monitor@gmail.com
export BROKENLINKBRIEF_SMTP_PASSWORD=your-app-password
export BROKENLINKBRIEF_SMTP_FROM=monitor@gmail.com
export BROKENLINKBRIEF_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx

python -m brokenlinkbrief.app

# In another terminal: scan a page — notifications fire automatically
curl "http://127.0.0.1:8000/scan?url=https://example.com"
```

## Scheduled Scanning

BrokenLinkBrief supports **automated recurring scans** through a scheduler that persists schedules in SQLite, leases work atomically, and detects regressions between scan runs.

### Features

- **Cron-based scheduling** — express scan frequency with standard 5-field cron expressions
- **SQLite persistence** — schedules survive process restarts
- **Atomic worker leasing** — prevent duplicate scans when multiple workers run
- **Regression detection** — compare current scan results against the last successful scan to surface newly broken links
- **Notification integration** — send regression alerts via email, Slack, or webhook

### Configuration

Define projects in a YAML or JSON file:

```yaml
version: "1.0"

projects:
  - name: "Main website"
    urls:
      - "https://example.com/"
      - "https://example.com/docs"
    schedule:
      cron: "0 9 * * *"
      timezone: "UTC"
    notifications:
      - type: email
        target: "team@example.com"
      - type: slack
        target: "#broken-links"
    options:
      timeout: 15.0
      max_workers: 10
```

See [`examples/schedule-config.yaml`](examples/schedule-config.yaml) for a complete example and [`docs/scheduled-scanning.md`](docs/scheduled-scanning.md) for the full reference.

### Quick Start

```bash
# Load and validate the config
python -c "
from pathlib import Path
from brokenlinkbrief.scheduler_config import load_projects_config

configs = load_projects_config(Path('examples/schedule-config.yaml'))
for c in configs:
    print(f'{c.name}: {c.schedule.cron} ({c.schedule.timezone})')
"

# Run a scan for a project
python -c "
from brokenlinkbrief.scheduled_scan import ScheduledScanExecutor

executor = ScheduledScanExecutor(max_retries=3, retry_delay=1.0)
result = executor.execute_scan({
    'id': 'docs',
    'name': 'Documentation',
    'urls': ['https://example.com/'],
})
print(f'Status: {result.status}, Broken: {result.broken_count}')
"
```

### Cron Examples

| Cron | Frequency |
|------|-----------|
| `0 9 * * *` | Daily at 09:00 |
| `0 */4 * * *` | Every 4 hours |
| `*/15 * * * *` | Every 15 minutes |
| `0 9 * * 1-5` | Weekdays at 09:00 |

### Deployment

Scheduled scanning integrates with standard cron-based deployment:

```bash
# Systemd timer, Docker cron, or bare metal crontab
0 * * * * cd /opt/broken-link-brief && \
  .venv/bin/python -m brokenlinkbrief.app --schedule \
  --config /opt/broken-link-brief/schedule-config.yaml
```

See [`docs/scheduled-scanning.md`](docs/scheduled-scanning.md) for systemd, Docker, and Docker Compose deployment guides.

## Dashboard

BrokenLinkBrief includes a **monitoring dashboard** at `/dashboard` — a self-contained HTML/JS page that visualizes historical scan data with real-time Chart.js charts.

Open it in your browser while the server is running:

```
http://127.0.0.1:8000/dashboard
```

> **Tip**: The dashboard queries its data from the REST API endpoints below. Data comes from the `.history/` JSONL store — scans are automatically recorded by `/scan` and `/scan-batch`.

### What's on the Dashboard

| Component | Description |
|-----------|-------------|
| **Summary Cards** | Total scans, broken link count, links checked, last scan date |
| **Broken Links Trend** | Line chart — total vs broken links over time (daily aggregation) |
| **Severity Breakdown** | Pie chart — critical (5xx) vs warning (4xx) vs info |
| **Domain Breakdown** | Horizontal bar chart — top 10 domains with the most broken links |
| **Date Range Filter** | Buttons for 7 days, 30 days, 90 days, or All time |

### Dashboard API Endpoints

All dashboard endpoints are **auth-gated**: if `BROKENLINKBRIEF_SCAN_TOKEN` is set, requests must include a `token` query parameter or `Authorization: Bearer` header.

Each endpoint accepts an optional `days` query parameter to control the lookback window:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | `int` | `7` | Number of days to look back. `0` = all time |

#### `/api/dashboard/summary` — Aggregate Statistics

```bash
curl "http://127.0.0.1:8000/api/dashboard/summary?days=30"
```

Response:
```json
{
  "total_scans": 42,
  "total_broken": 17,
  "total_links": 1283,
  "unique_urls": 5,
  "last_scan_timestamp": "2026-07-30T01:00:19+00:00"
}
```

#### `/api/dashboard/trends` — Daily Trend Data

```bash
curl "http://127.0.0.1:8000/api/dashboard/trends?days=7"
```

Response:
```json
[
  {"date": "2026-07-24", "total": 48, "broken": 3},
  {"date": "2026-07-25", "total": 52, "broken": 5},
  {"date": "2026-07-26", "total": 44, "broken": 1}
]
```

#### `/api/dashboard/severity` — HTTP Status Severity Breakdown

```bash
curl "http://127.0.0.1:8000/api/dashboard/severity?days=90"
```

Response:
```json
{
  "critical": 3,
  "warning": 8,
  "info": 6
}
```

| Severity | HTTP Range | Meaning |
|----------|-----------|---------|
| `critical` | 5xx | Server errors |
| `warning` | 4xx | Client errors (broken links) |
| `info` | Other / fetch-failed | Timeouts, unreachable, 3xx broken redirects |

#### `/api/dashboard/domains` — Domain Breakdown

```bash
curl "http://127.0.0.1:8000/api/dashboard/domains?days=0"
```

Response:
```json
[
  {"domain": "httpstat.us", "count": 12},
  {"domain": "example.com", "count": 5},
  {"domain": "old-blog.example.org", "count": 2}
]
```

Results are sorted descending by count. The dashboard shows the top 10.

### Authentication

If `BROKENLINKBRIEF_SCAN_TOKEN` is set, pass it with any dashboard API call:

```bash
curl "http://127.0.0.1:8000/api/dashboard/summary?token=your-token"
# or
curl -H "Authorization: Bearer your-token" \
  "http://127.0.0.1:8000/api/dashboard/summary"
```

For the HTML dashboard, append `?token=your-token` to the URL:

```
http://127.0.0.1:8000/dashboard?token=your-token
```

### Dark Theme

The dashboard uses a dark colour scheme designed for always-on monitoring displays:
- Background: `#1a1a2e` (deep navy)
- Accent: `#e94560` (red for broken-link prominence)
- Cards: `#16213e` with `#0f3460` borders
- Chart.js respects the theme via custom colour configuration

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

The app reads the `PORT` environment variable automatically.

### Docker

```bash
docker build -t brokenlinkbrief .
docker run -p 8000:8000 brokenlinkbrief
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Optional: SPA scanning (for integration tests)
pip install -e ".[playwright]"
playwright install chromium

# Run tests
.venv/bin/python -m pytest

# Lint
ruff check .
```

## License

MIT

## Product workflows added in 1.0

BrokenLinkBrief now exposes six independent, dependency-light building blocks. They use the Python standard library and can be embedded without replacing the existing HTTP API.

### Durable schedules

`ScheduleStore` persists project schedules in SQLite and atomically leases due work so a due slot is not claimed twice after a process restart.

```python
from brokenlinkbrief.scheduler import ScheduleStore

store = ScheduleStore("brokenlinkbrief.db")
store.create("docs", "*/15 * * * *", "Europe/Zurich", next_due_at=0)
due = store.claim_due(now=1, worker_id="worker-1")
```

### Source-aware repair queue

`extract_occurrences()` retains the source page, resolved target, anchor text, and HTML context. `FindingStore` persists findings and prevents conflicting assignments.

### Confidence classification

`classify_evidence()` distinguishes `UNVERIFIED`, `TRANSIENT`, `BOT_BLOCKED`, `RECOVERED`, `INCONCLUSIVE`, and `CONFIRMED_BROKEN`. A terminal 404 or 410 requires repeated evidence before confirmation.

### Secure outbound policy

`validate_target()` rejects unsupported schemes, unapproved ports, private, loopback, link-local, reserved, multicast, and unspecified destinations. `validate_redirect_chain()` revalidates every hop and enforces the redirect budget.

### Organizations and RBAC

`GovernanceStore` supports organizations, `VIEWER`, `OPERATOR`, and `ADMIN` memberships, capability checks, and hashed service credentials. Plaintext credentials are returned once and are never stored.

### CI quality gate

Generate a baseline and evaluate findings with stable exit codes:

```powershell
brokenlinkbrief baseline --findings findings.json --output baseline.json
brokenlinkbrief ci --findings findings.json --baseline baseline.json --max-new 0
```

Exit code `0` means pass, `2` means new confirmed findings exceeded policy, and invalid baseline data is rejected explicitly.

## Architecture

Each capability is isolated in its own module: `scheduler`, `triage`, `confidence`, `policy`, `governance`, and `ci_gate`. Domain models are immutable dataclasses, SQLite adapters own persistence, and the CLI depends only on the CI application API. The existing `app.py`, scan endpoints, renderers, and notification contracts remain available for backward compatibility.

## Testing the 1.0 capabilities

```powershell
$env:PYTHONPATH="src"
python -m pytest -q tests/test_product_features.py
python -m compileall -q src tests
```

## Browser scan workflow

The dashboard is now an operational entry point as well as an analytics view. Open `/dashboard`, enter a public HTTP or HTTPS page in **Scan a page**, and select **Run scan**. The page announces progress, renders an accessible results table, moves keyboard focus to the results, and refreshes the dashboard metrics after completion.

Safety and behavior notes:

- Single scans and batch scans apply SSRF validation before fetching a target.
- Private, loopback, link-local, metadata, multicast, and reserved destinations are rejected.
- The selected 7/30/90/all-time range now applies consistently to summary cards and charts.
- If token authentication is enabled, prefer an `Authorization: Bearer` header for API calls. Query tokens remain supported for backward compatibility with the self-contained dashboard, but may appear in browser history or access logs.

### Validate the release

```bash
python -m pytest -q
ruff check src tests
```

### Recent pages and one-click rescanning

The dashboard lists up to eight recently scanned pages below the scan form. Select **Scan again** to populate and submit the scan form without retyping the URL. The list is deduplicated by target URL, ordered by the latest scan, and refreshed after each successful scan.

The supporting authenticated endpoint is:

```text
GET /api/dashboard/recent-targets?limit=10
```

`limit` is constrained to 1 through 50. Each item includes the target URL, latest scan timestamp, number of links checked, and number needing attention.

### Per-page scan history

Each item in **Recent pages** now includes **View history**. The history dialog displays scans newest first and summarizes:

- Links checked
- Links needing attention
- Newly broken links since the preceding scan
- Fixed links since the preceding scan

The supporting authenticated endpoint is:

```text
GET /api/dashboard/target-history?url=https%3A%2F%2Fexample.com&limit=20
```

The `url` parameter is required. `limit` is constrained to 1 through 50. The first retained scan uses an empty baseline, so all broken results in that scan are reported as newly broken.


### Actionable history details and export

Expand **Change details** on any history entry to see the exact URLs that became broken or were fixed, including their current status. Change lists are sorted by URL for deterministic API responses and stable review.

Select **Export history JSON** in the history dialog to download the currently displayed page history. The export contains the target URL, timeline summaries, and the newly broken/fixed link details already loaded in the browser. No additional server-side data is requested.

### Filter, search, and export the latest results

After a browser scan, use the result toolbar to focus on:

- **All results**
- **Needs attention**: HTTP 4xx/5xx responses and links without a response
- **Healthy**: successful and redirect responses below HTTP 400

The search field filters the displayed rows by URL, reason, or status. **Export visible CSV** downloads only the rows currently matching the selected category and search query. The browser-generated CSV neutralizes leading spreadsheet formula characters before download.

### Browser batch scanning

Choose **Multiple pages** in the dashboard to scan several source pages without constructing a JSON request manually.

1. Enter one public HTTP or HTTPS URL per line.
2. Optionally choose 1 through 20 parallel scans.
3. Select **Run batch scan**.
4. Review the combined link results with the same filters, search, count, and visible-CSV export used by single scans.

The browser validates empty input, more than 50 entries, and exact duplicate URLs before submitting to the existing `/scan-batch` endpoint. Server-side SSRF and request validation remain authoritative.

### Source-aware result review

Every browser result now retains the source page that produced the link. This is especially important for batch scans, where the same target link may appear on several pages.

The latest-results table includes a **Source page** column and the toolbar includes an **All source pages** selector. Search also matches source-page URLs. Focused CSV exports now use this schema:

```text
source_url,url,status,reason,location
```

Single-page scans assign the entered target as the source context. Batch scans preserve each key from the per-source API response before flattening rows for review.

## Saved projects in 1.1

The dashboard now supports durable named projects for pages that are scanned repeatedly.

1. Enter a project name.
2. Enter one public HTTP or HTTPS target per line.
3. Select **Save project**.
4. Use **Load targets** to populate the appropriate single-page or multi-page scan form.
5. Use **Archive** to remove a project from the active list without deleting scan history.

Projects are stored in SQLite. The default database is `.brokenlinkbrief.db` in the application working directory. Override it with:

```bash
export BROKENLINKBRIEF_PROJECT_DB=/data/brokenlinkbrief.db
```

For containers, mount a persistent writable volume at the configured database location. Existing 1.0.x history remains in `.history/`; no destructive migration is performed.

### Project API

```text
GET    /api/projects
POST   /api/projects
DELETE /api/projects/{project_id}
```

Create request:

```json
{
  "name": "Main website",
  "targets": [
    "https://example.com/",
    "https://example.com/docs"
  ]
}
```

Project APIs use the same optional token authentication as scan and dashboard APIs. Targets are SSRF-validated before persistence.

### Edit and restore projects

Active projects now include **Edit**, **Load targets**, and **Archive** actions. Editing reuses the project form and preserves the project's stable ID. Select **Show archived** to review archived projects and use **Restore** to return a project to the active list.

Additional API operations:

```text
PUT  /api/projects/{project_id}
POST /api/projects/{project_id}/restore
GET  /api/projects?archived=1
```

Updates use the same target normalization, project limits, credential rejection, SSRF validation, and authentication rules as project creation.

### Run and assess a project quickly

Active project cards now include **Run project scan**. A single-target project immediately uses the single-page workflow; a multi-target project immediately uses the batch workflow. This removes the previous load-then-submit step.

Project cards and `GET /api/projects` now expose a compact summary based on the latest retained scan for each target:

- scanned and unscanned target counts
- total links in the latest target snapshots
- links needing attention
- latest scan timestamp

Configure persistent history independently when needed:

```bash
export BROKENLINKBRIEF_HISTORY_DIR=/data/history
```

Use persistent writable storage for both `BROKENLINKBRIEF_PROJECT_DB` and `BROKENLINKBRIEF_HISTORY_DIR` in production.

### Export and import project configuration

Use **Export project** to download a portable JSON configuration containing only the schema version, project name, and normalized targets. Runtime IDs, timestamps, archive state, scan history, findings, and secrets are not exported.

Use **Import project** to select a supported JSON configuration. Import creates a new project identity and applies the same validation and SSRF rules as manual creation.

Portable schema version 1:

```json
{
  "schema_version": 1,
  "name": "Main website",
  "targets": [
    "https://example.com/",
    "https://example.com/docs"
  ]
}
```

API operations:

```text
GET  /api/projects/{project_id}/export
POST /api/projects/import
```

### Duplicate a project

Use **Duplicate** to create an active project with the same ordered target list and a new identity. This is useful when creating an environment-specific or client-specific variant without editing the source project.

Copy names are allocated predictably:

```text
Main website copy
Main website copy 2
Main website copy 3
```

History, timestamps, archive state, findings, and other runtime state are not copied.

API:

```text
POST /api/projects/{project_id}/duplicate
```

### Pin frequently used projects

Use **Pin** on an active or archived project to keep it at the top of its list. Use **Unpin** to return it to normal recently-updated ordering.

Pin state is stored in the project database and survives restarts. Existing 1.1.x databases are migrated automatically by adding a non-breaking `pinned` column with a false default.

New duplicates and imported projects begin unpinned. This keeps prioritization intentional and prevents a source project's personal ordering choice from propagating to copies.

API:

```text
POST /api/projects/{project_id}/pin
```

Request body:

```json
{
  "pinned": true
}
```

## Trusted Findings and Verify Fix

Version 1.3.1 adds an evidence-aware repair workflow for saved projects. Run a saved single-page project scan, open **Trusted findings** in the dashboard, inspect the exact source occurrence and bounded probe evidence, acknowledge the work, and select **Verify fix** after repair. Only repeated confirmed failures create findings; transient, bot-blocked, recovered, and inconclusive observations do not create noise.

Findings are stored in the configured `BROKENLINKBRIEF_PROJECT_DB` with optimistic versions, immutable audit events, source occurrences, evidence, and verification history. Existing `/scan` result fields and CSV, Markdown, and JSONL exports are unchanged. See [docs/findings.md](docs/findings.md) for API examples, classifications, migration, privacy, and troubleshooting.

If verification is inconclusive, the finding remains unchanged and the dashboard offers a safe retry. Back up the SQLite project database before upgrading. Query-string tokens remain supported for compatibility, but bearer headers are recommended for API clients.
