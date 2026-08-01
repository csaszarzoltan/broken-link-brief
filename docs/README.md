# BrokenLinkBrief — micro-feature docs

## `/scan` read-only authentication

### Why this exists
Exposes `/scan` without restriction while still allowing operator-controlled access when needed.

### Configuration
Set the environment variable `BROKENLINKBRIEF_SCAN_TOKEN` to require a matching token on every `/scan` request. When unset or empty, `/scan` remains public for backward compatibility.

### Request shapes
```bash
# Query token
BROKENLINKBRIEF_SCAN_TOKEN=secret python -m apps.brokenlinkbrief.app
curl "http://127.0.0.1:8000/scan?url=https://example.com&token=secret"

# Bearer header
curl -H "Authorization: Bearer ***" "http://127.0.0.1:8000/scan?url=https://example.com"
```

### Responses
- `401` JSON `{"detail": "missing or invalid scan token"}`
- `400` JSON `{"detail": "missing url query parameter"}`
- `200` JSON scan results (default, or `format` omitted / unrecognized)
- `200` CSV with `Content-Type: text/csv; charset=utf-8` (when `format=csv`)
- `200` Markdown with `Content-Type: text/markdown; charset=utf-8` (when `format=markdown`)

### CSV export
Add `format=csv` to `/scan` to receive a comma-separated file with a stable header row (`url,status,reason,location`). This is useful for importing results into spreadsheets or data pipelines.

```bash
curl "http://127.0.0.1:8000/scan?url=https://example.com&format=csv&token=secret"
```

Output:
```csv
url,status,reason,location
https://example.com,200,OK,
```

### Markdown export
Add `format=markdown` to `/scan` to receive a Markdown table brief. This is useful for copy/drop into reports or issue trackers.

```bash
curl "http://127.0.0.1:8000/scan?url=https://example.com&format=markdown&token=secret"
```

Output:
```markdown
# BrokenLinkBrief

| URL | Status | Reason | Location |
| --- | ---: | --- | --- |
| https://example.com | 200 | OK |  |
```

### Formula injection protection
Fields that start with spreadsheet formula triggers (`= + - @ \t \r`) are prefixed with an apostrophe before quoting, preventing CSV-injection attacks (CWE-1236) when the output is opened in Excel, Google Sheets, or LibreOffice Calc.

### Usage logging
Set `BROKENLINKBRIEF_LOG_FILE` to append one JSON log line per successful `/scan` request. When the variable is unset or empty, logs go to `stderr`.

Logged fields:
- `timestamp`: ISO 8601 UTC timestamp
- `target_url`: requested target URL
- `result_count`: number of link results returned
- `broken_count`: results whose status is missing, `>= 400`, or whose reason is not `OK`
- `format`: response format used (`json`, `csv`, or `markdown`)
- `latency_seconds`: elapsed wall time for `scan_page`
- `status`: `ok` when `broken_count == 0`, otherwise `error`

### Dashboard API

The dashboard endpoints provide aggregated historical scan data for the monitoring UI. All endpoints require authentication when `BROKENLINKBRIEF_SCAN_TOKEN` is set.

### `/api/dashboard/summary`

Aggregate statistics across all scanned URLs.

| Method | Auth | Params |
|--------|------|--------|
| GET | Same as `/scan` | `days` (int, default 7, 0 = all time) |

```bash
curl "http://127.0.0.1:8000/api/dashboard/summary?days=30&token=secret"
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

### `/api/dashboard/trends`

Daily-aggregated total vs broken link counts for line charts.

| Method | Auth | Params |
|--------|------|--------|
| GET | Same as `/scan` | `days` (int, default 7) |

```bash
curl "http://127.0.0.1:8000/api/dashboard/trends?days=7&token=secret"
```

Response:
```json
[
  {"date": "2026-07-24", "total": 48, "broken": 3},
  {"date": "2026-07-30", "total": 52, "broken": 1}
]
```

### `/api/dashboard/severity`

Broken links grouped by HTTP status severity.

| Method | Auth | Params |
|--------|------|--------|
| GET | Same as `/scan` | `days` (int, default 7) |

```bash
curl "http://127.0.0.1:8000/api/dashboard/severity?days=90&token=secret"
```

Response:
```json
{
  "critical": 3,
  "warning": 8,
  "info": 6
}
```

| Severity | HTTP Range |
|----------|-----------|
| `critical` | 5xx |
| `warning` | 4xx |
| `info` | Other / fetch-failed |

### `/api/dashboard/domains`

Broken links grouped by domain, sorted descending.

| Method | Auth | Params |
|--------|------|--------|
| GET | Same as `/scan` | `days` (int, default 7) |

```bash
curl "http://127.0.0.1:8000/api/dashboard/domains?days=0&token=secret"
```

Response:
```json
[
  {"domain": "httpstat.us", "count": 12},
  {"domain": "example.com", "count": 5}
]
```

### HTML Dashboard

The `/dashboard` endpoint serves a Chart.js-powered HTML page that consumes all four API endpoints automatically.

```
http://127.0.0.1:8000/dashboard?token=secret
```

- Dark theme with summary cards and interactive charts
- Date range filter: 7 days, 30 days, 90 days, All time
- Charts: trend line, severity pie, domain bar (top 10)

## Notes
- Query-string tokens may appear in access logs. Prefer the `Authorization` header in production.
- `/health` remains public regardless of token configuration.
- Secrets must match exactly; no hashing or expiration is applied.
- Logging only happens after a successful scan and only for valid `/scan` paths. `400`/`401`/`404` responses are not logged.

## Saved Projects API

Projects reduce repeat entry for commonly scanned pages.

- `GET /api/projects` lists active projects.
- `POST /api/projects` creates a project with 1 to 50 targets.
- `DELETE /api/projects/{id}` archives a project.

The endpoints use dashboard authentication. Targets are normalized, deduplicated, rejected if they contain credentials, and checked by the scan SSRF policy before save.
