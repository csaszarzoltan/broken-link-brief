# Changelog

## v1.5.0 (2026-08-12)

### Features
- **Multi-site portfolio dashboard** — `/dashboard/portfolio` page with per-project rows (latest scan time, open/resolved findings), summary cards (projects, open findings, resolved), trend chart with date-range filter, and CSV export
- **Portfolio aggregation API** — `GET /api/portfolio` (project rows with per-project open/resolved counts), `GET /api/portfolio/summary?days=` (aggregate totals + trend); per-project attribution via single indexed `GROUP BY project_id, state` query
- **Evidence-aware repair workflow** — bounded evidence classification, durable source-aware project findings, optimistic lifecycle actions, targeted Verify Fix, additive findings APIs, and an accessible dashboard workspace
- **Durable scan jobs** — persistent saved-project jobs with source progress, idempotent creation, cancellation, and failed-source retry
- **Versioned host policies** — exact-host policy versioning with additive APIs and an accessible job dashboard
- **Recoverable job leases** — worker-owned leases with heartbeat validation, exclusive job claims, and expired-lease recovery that never repeats committed sources
- **Immutable job policy snapshots** — project/policy-scoped caching for eligible evidence, so in-flight jobs keep a consistent policy view
- **Applied scan policies** — effective timeout, attempt-count, temporary-status, and exponential-backoff policies applied to detailed probes; a dedicated heartbeat loop preserves job ownership during blocked source requests

### Fixes
- **SSRF bypass closed** — extracted and stored target/source URLs are validated before project-finding probes and Verify Fix requests
- **Per-project findings attribution** — portfolio rows now show their own project's open/resolved counts instead of the aggregate totals broadcast to every row
- **Project integrity** — foreign-key integrity, project existence checks, and archived-project read-only enforcement
- **Expired ignores** — automatically reopened after successful verification
- **Occurrence search** — by source URL and anchor text; occurrence activation/deactivation reconciliation after successful verification
- **Filter validation** — state and classification filters validated; credential-like values redacted from persisted error evidence
- **Playwright tests** — skip cleanly when Chromium cannot launch instead of producing false failures

### Tests
- **Portfolio API tests** — per-project attribution regression tests (A=1/1, B=1/0), API shape, filters, and edge inputs
- **Dashboard UI tests** — dashboard cards, chart, empty state, error toast, and export contract
- **Verification outcomes coverage** — regression coverage for all four outcomes: RECOVERED, REMOVED_FROM_SOURCE, STILL_BROKEN, INCONCLUSIVE
- Full suite: 911 passed / 42 skipped / 1 xpassed / 0 failures

### Docs
- **Portfolio dashboard analysis brief** — design and API contract for the portfolio dashboard feature

## v1.2.0 (2026-08-03)

### Features
- **SPA scan engine** — JavaScript-rendered link extraction via Playwright; `render_js=true` query parameter on `/scan` renders pages with headless Chromium before extracting links
- **Link diff engine** — `DiffDetector` compares current scan results against persisted `LinkStateStore` to detect new broken, resolved, status-changed, new, and removed links
- **Diff alerts** — `DiffNotificationTemplates` and `DiffNotifier` send email/Slack alerts when link state changes are detected between scans
- **Per-URL link state tracking** — `LinkStateStore` persists individual link states in SQLite with upsert support, `first_seen`/`last_seen` timestamps, and `scan_mode` (`static`/`spa`)
- **Scheduled scanning** — cron-based recurring scans with SQLite persistence and atomic worker leasing (`SchedulerService`, `ScheduleStore`)
- **YAML/JSON schedule configuration** — `load_projects_config` and `validate_project_config` with cron expression parsing and timezone validation
- **Regression detection** — `RegressionDetector` compares current scans against the last successful scan to surface newly broken links; `RegressionNotifier` sends formatted alerts
- **Dashboard single-page scan workflow** — accessible browser-based scan UI with results table, progress feedback, keyboard focus management, and dashboard analytics refresh
- **Recent pages panel** — `GET /api/dashboard/recent-targets` for quick rescans of frequently checked URLs
- **Scan history dialog** — per-target scan timeline with newest-first summaries, change details, and JSON export
- **Result filters and search** — All results / Needs attention / Healthy filters with instant client-side search and visible-result CSV export
- **Browser batch scanning** — Single page and Multiple pages scan modes, multiline batch URL form (up to 50 URLs), configurable concurrency (1-20)
- **Source-aware result review** — source-page URL column in result tables, source-page selector, source-aware search and CSV export
- **Durable saved projects** — SQLite-backed named projects with CRUD, archival, restoration, editing, duplication, and pin/unpin actions
- **Portable project config** — versioned JSON export/import for project configurations with full validation on import
- **Project pinning** — persistent pin/unpin for frequently used projects with backward-compatible schema migration

### Fixes
- **Browser process leak** — try/finally in `spa_scanner.py` ensures Playwright browser cleanup
- **Private import replaced** — `diff_alerts.py` uses local helper instead of private module import
- **first_seen preservation** — `LinkStateStore` upsert preserves original `first_seen` timestamp
- **Dead code removed** — stale regression code cleaned from `app.py`
- **sqlite3.Row iteration** — fixed tuple row handling in `scan_history.py`
- **Code review compliance** — ruff fixes across dashboard and SPA code (E501, N806, import sorting, trailing whitespace)

### Tests
- **SPA scanner**: unit tests for import, instantiation, Playwright rendering, fallback; integration tests for JS link discovery, diff detection, notification firing, regression detection
- **Link diff**: DiffDetector compare, LinkStateStore upsert, DiffReport structure, change categories
- **Diff alerts**: template rendering, notification delivery, rate limiting
- **Dashboard**: scan workflow, accessibility semantics, target validation, date filtering, version reporting
- **Project lifecycle**: store, API integration, validation, archive, restore, duplication, pinning, import/export
- **Scan history**: timeline derivation, first-scan baseline, API validation, change details
- **Scheduled scanning**: config parsing, cron validation, executor retry logic, regression detection
- **Regression tests**: sqlite3.Row iteration, Node.js syntax validation, JavaScript regression suite
- Total test count: 838 passed / 0 failed / 34 skipped / 1 xpassed

### Docs
- Updated README with SPA scanning, Playwright installation, `render_js` endpoint, Link Diff Engine, and scheduled scanning sections
- Added `docs/spa-scanning.md` — full reference for SPA scan mode
- Added `docs/scheduled-scanning.md` — config format, cron patterns, deployment guides (systemd, Docker, bare metal, Docker Compose)
- Added `examples/schedule-config.yaml` — annotated 3-project example config
- Updated CHANGELOG with consolidated v1.2.0 entry

## v0.9.0 (2026-07-30)

### Features
- **Monitoring dashboard** — real-time HTML dashboard at `/dashboard` with Chart.js visualizations for historical trends, severity breakdown, and domain distribution
- **Dashboard API endpoints** — four RESTful endpoints (`/api/dashboard/summary`, `/api/dashboard/trends`, `/api/dashboard/severity`, `/api/dashboard/domains`) with full auth protection
- **HistoryStore analytics** — `get_dashboard_summary()`, `get_trend_data()`, `get_severity_breakdown()`, `get_domain_breakdown()` methods for programmatic access to scan analytics
- **Dark theme UI** — sleek dark-themed dashboard with summary cards, date range controls, and empty-history handling
- **Auth-gated dashboard** — all dashboard endpoints require valid scan token authentication

### Fixes
- **Code review compliance** — applied 11+ ruff fixes across dashboard code (E501 line-length, N806 naming, A002 noqa, import sorting, trailing whitespace) ensuring src/ remains lint-clean

### Tests
- Added 17 dashboard tests covering API endpoints, HTML rendering, auth gating, empty history edge cases, Chart.js CDN presence, dark theme CSS, chart canvases, date range controls, and summary cards
- Total test count: 289 (up from 272)
- Coverage: 83% (maintaining ≥80% threshold)

## v0.8.0 (2026-07-27)

### Features
- **Email notification support** — SMTP-based email alerts when broken links are detected; configurable recipients, sender address, and server settings
- **Slack webhook integration** — sends formatted messages to Slack via Incoming Webhook URL with severity-based formatting
- **Notification templates** — customizable plain-text templates with severity-based alerting (INFO, WARNING, CRITICAL)
- **Rate limiting** — token-bucket algorithm prevents notification flood (configurable rate and burst per channel)
- **Environment variable configuration** — all notification settings configurable via `EMAIL_*` and `SLACK_*` environment variables via `NotifierConfig.from_env()`

### Improvements
- **Health check endpoint** — comprehensive `/health` endpoint for monitoring and uptime checks
- **Enhanced SSRF protection** — ported ReceiptLens SSRF guard patterns for more robust URL validation
- **Railway deploy config** — deployment configuration aligned with platform best practices

### Tests
- Added 102 new tests across notification module, health check, SSRF protection, and deployment
- Total test count: 272 (up from 170)
- Coverage: 82% (maintaining ≥80% threshold)

## v0.7.0 (2026-07-22)

### Features
- **Batch scanning** — POST /scan-batch endpoint accepts up to 50 URLs in a single request for parallel link checking
- **Concurrency control** — configurable worker count (max 20) for parallel URL scanning
- **Duplicate URL rejection** — returns HTTP 400 when duplicate URLs are present in a batch request
- **SSRF protection** — per-URL SSRF validation applied to all URLs in the batch
- **Batch JSONL logging** — batch scan results logged with batch_id and latency for traceability

### Tests
- Added 39 new tests across 2 test files (test_batch_endpoint.py: 10/10, test_batch_scan.py: 29/29)
- Total test count: 170 (up from 130)

## v0.6.0 (2026-07-21)

### Features
- **Webhook notifications** — register HTTPS webhook URLs to receive scan results when broken links are detected
- **HMAC-SHA256 signing** — all webhook payloads are signed with an optional secret; verification uses timing-safe comparison
- **Retry with exponential backoff** — failed webhook deliveries retry up to 3 times (1s, 2s, 4s delays)
- **SSRF protection for webhook URLs** — blocks private IPs, loopback addresses, and non-HTTPS schemes
- **POST /webhooks endpoint** — register, list, and remove webhook URLs via HTTP API with token authentication
- **Duplicate URL detection** — returns HTTP 409 when registering an already-registered URL

### Tests
- Added 90 new tests across 3 test files (test_webhook.py, test_webhook_registration.py, test_webhook_ssrf.py)
- Total test count: 130 (up from 41)

### Docs
- Updated README with webhook notification features and API documentation

## v0.5.0 (2026-07-20)

### Features
- Initial release — broken link scanner with JSON/CSV/Markdown/JSONL export
- Token-based authentication
- SSRF protection for scan targets
- Railway deployment support
- JSONL usage logging
