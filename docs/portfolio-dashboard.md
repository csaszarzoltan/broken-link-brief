# Portfolio Dashboard

The **portfolio dashboard** is the cross-project health view of BrokenLinkBrief. It
aggregates the latest scan results of every saved project into summary cards, a
per-project table, and a daily broken-link trend chart — so you can watch all your
sites from one page instead of opening each project's history individually.

> The portfolio dashboard is part of the single-page dashboard served at
> [`/dashboard`](#access). It was introduced in v1.5.0.

## Access

The portfolio section lives on the main dashboard page:

```
http://127.0.0.1:8000/dashboard
```

If `BROKENLINKBRIEF_SCAN_TOKEN` is set, append it as a query parameter — the
dashboard forwards it to every portfolio API call:

```
http://127.0.0.1:8000/dashboard?token=your-token
```

The page shows the **Portfolio overview** section below the scan panel. It
loads automatically when the page opens and refreshes whenever the date-range
filter changes.

## What's on the page

| Component | Description |
|-----------|-------------|
| **Summary cards** | Total links across all projects, broken count, resolved findings, and a health score (0–100) |
| **Project rows** | One row per saved project: link counts, broken count, fixed findings, last scan status, last scan time |
| **Trend chart** | Daily total-vs-broken link counts across the selected window |
| **Export CSV** | Downloads the project rows as `portfolio-export.csv` |

### Health score

`health_score` is `100 × (1 - broken / total_links)` across the latest scan of
every active project, rounded to one decimal. When no links have been scanned
yet, the score is `100.0`. The card colors the score:

- `>= 90` — green (`good`)
- `>= 70` — amber (`warn`)
- `< 70` — red (`bad`)

## Date range filter

The trend chart respects a lookback window. Use the buttons in the portfolio
section to switch:

| Button | `days` value sent to the API | Meaning |
|--------|------------------------------|---------|
| 7 days | `7` | Last 7 days |
| 30 days | `30` | Last 30 days (default) |
| 90 days | `90` | Last 90 days |
| All time | `0` | Entire scan history |

The filter only affects the **trend chart**. The summary cards and project rows
always aggregate the latest scan per project, independent of the selected
window.

## Empty state

When no saved projects exist yet (or none have been scanned), the portfolio
section shows:

- "No saved projects yet. Save your recurring targets above." in the cards area,
- an empty project list,
- no trend chart.

This is the normal state on a fresh install — save a project and run it at
least once (via the scan panel or a scheduled scan) to populate the portfolio.

## Export

The **Export CSV** button downloads the current project rows as
`portfolio-export.csv` with a stable header:

```
project_name,total_links,broken_count,open_findings,resolved_findings,last_scan_timestamp
```

- The export reflects the projects currently loaded in the dashboard (all
  active projects; the date filter does not change the rows).
- Cells are RFC 4180 quoted. Values that start with a spreadsheet formula
  trigger (`=`, `+`, `-`, `@`, tab, CR) are prefixed with an apostrophe before
  quoting, preventing CSV-injection attacks (CWE-1236) when the file is opened
  in Excel, Google Sheets, or LibreOffice Calc.

## API

The dashboard is backed by two read-only endpoints. Both are auth-gated: when
`BROKENLINKBRIEF_SCAN_TOKEN` is set, they require a `token` query parameter or
an `Authorization: Bearer <token>` header, and return
`401 {"detail": "missing or invalid scan token"}` otherwise.

### `GET /api/portfolio`

Per-project rows plus an aggregate summary of **active** projects. Archived
projects are excluded unless listed explicitly in `project_ids`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_ids` | `string` | — | Comma-separated project ids to restrict the portfolio to (archived projects are included when listed explicitly) |

Example:

```bash
curl "http://127.0.0.1:8000/api/portfolio?token=your-token"
```

Response (verified against a seeded demo database):

```json
{
  "summary": {
    "projects": 3,
    "scanned_projects": 2,
    "unscanned_projects": 1,
    "total_links": 70,
    "broken_count": 13,
    "new_broken_count": 2,
    "open_findings": 0,
    "resolved_findings": 0,
    "health_score": 81.4,
    "last_scan_timestamp": "2026-08-12T12:34:48.485768+00:00"
  },
  "projects": [
    {
      "project_id": "081a9aad23024a57a9423e269f7cea8e",
      "project_name": "Docs site",
      "total_links": 50,
      "broken_count": 5,
      "new_broken_count": 2,
      "open_findings": 0,
      "resolved_findings": 0,
      "last_scan_timestamp": "2026-08-12T12:34:48.484541+00:00",
      "last_scan_status": "completed",
      "pinned": false,
      "archived": false
    }
  ]
}
```

Field reference:

| Field | Meaning |
|-------|---------|
| `summary.projects` | Number of projects included (active by default) |
| `summary.scanned_projects` | Projects that have at least one scan record |
| `summary.unscanned_projects` | Projects with no scan record yet |
| `summary.total_links` / `summary.broken_count` | Sum of the **latest** scan per project |
| `summary.health_score` | `100 × (1 - broken / total_links)`, rounded to 1 decimal; `100.0` when nothing scanned |
| `row.last_scan_status` | `completed`, `failed`, or `never_run` |
| `row.pinned` / `row.archived` | Project flags (archived projects only appear when explicitly requested) |

### `GET /api/portfolio/summary`

Aggregate totals plus the daily broken-link trend for the chart.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | `int` | `30` | Lookback window for the trend; `0` = all history, `days <= 0` = all history |
| `project_ids` | `string` | — | Same filter as `/api/portfolio` |

Example:

```bash
curl "http://127.0.0.1:8000/api/portfolio/summary?days=30&token=your-token"
```

Response:

```json
{
  "summary": {
    "projects": 3,
    "scanned_projects": 2,
    "unscanned_projects": 1,
    "total_links": 70,
    "broken_count": 13,
    "new_broken_count": 2,
    "open_findings": 0,
    "resolved_findings": 0,
    "health_score": 81.4,
    "last_scan_timestamp": "2026-08-12T12:34:48.485768+00:00"
  },
  "trend": [
    {
      "date": "2026-08-12",
      "total_links": 110,
      "broken_count": 16
    }
  ]
}
```

`trend` is an ascending list of `{date, total_links, broken_count}` points
(one per day that has scan records; `date` is `YYYY-MM-DD`). Days without
records are omitted — the chart fills the gaps.

## Data source

Portfolio numbers are computed by `brokenlinkbrief/portfolio.py` directly from
the SQLite project database:

- `projects` table — project names, pinned/archived flags
- `scan_history` table — only the **latest** record per project contributes to
  the summary and rows; the trend aggregates every record inside the window
- `project_findings` table — open/resolved finding counts, attributed per
  project (a single indexed `GROUP BY project_id, state` query; projects
  without the findings tables report zeros)

## TypeScript client example

A runnable client example mirroring the dashboard's portfolio section is in
[`examples/portfolio-example.ts`](../examples/portfolio-example.ts). It shows
`GET /api/portfolio`, `GET /api/portfolio/summary`, and a client-side CSV
export with the same CWE-1236 formula guard as the dashboard.

```bash
# Type-check (Node 18+ has fetch; BROKENLINKBRIEF_SCAN_TOKEN is optional)
npx tsc --noEmit --strict --target es2020 --module es2020 --lib es2020,dom,es2021 examples/portfolio-example.ts
```

## Demo seed

`tools/_seed_portfolio_demo.py` seeds a throwaway project database with two
scanned projects and one unscanned project, then (optionally) probes the API:

```bash
BROKENLINKBRIEF_PROJECT_DB=/tmp/pf.db .venv/bin/python tools/_seed_portfolio_demo.py
```
