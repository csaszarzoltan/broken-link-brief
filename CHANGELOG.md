# Changelog

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

### v1.0.0 (2026-07-30)

#### Product capabilities
- Added durable SQLite-backed project schedules with atomic worker leasing and timezone validation.
- Added source-aware link occurrence extraction and an assignable repair queue.
- Added evidence-based confidence classification for transient, bot-blocked, recovered, and confirmed broken links.
- Added a centralized outbound crawl policy for scheme, port, DNS/IP, redirect, and resource controls.
- Added organization membership, RBAC, hashed service credentials, and an audit-ready persistence model.
- Added a deterministic CI baseline evaluator and `brokenlinkbrief` CLI with stable exit codes.

#### Quality
- Added isolated tests for all six product capabilities, including negative and security cases.
- Preserved the existing HTTP and export contracts.

### v1.0.1 (2026-08-01)

#### User experience
- Added an accessible browser-based single-page scan workflow to the monitoring dashboard.
- Added responsive results table, progress feedback, empty/error states, keyboard focus management, and skip navigation.
- Dashboard refreshes analytics after a successful scan.

#### Correctness and security
- Applied SSRF target validation to single scans, matching batch behavior.
- Fixed dashboard summary cards so the selected date range is applied consistently.
- Health metadata now reports the installed package version.
- Deployment health now treats external network diagnostics as informational rather than restart-triggering dependencies.

#### Tests
- Added acceptance coverage for the dashboard workflow, accessibility semantics, target validation, date filtering, and version consistency.

### v1.0.2 (2026-08-01)

#### Repeat-user workflow
- Added a recent-pages panel to the dashboard so frequently scanned targets can be scanned again with one action.
- Added `GET /api/dashboard/recent-targets` with bounded result limits and existing dashboard authentication protection.
- Added `HistoryStore.get_recent_targets()` to return the latest unique targets with compact link and failure summaries.
- Recent targets refresh automatically after a successful scan and include accessible loading, empty, error, and action states.

#### Tests
- Added TDD coverage for unique target ordering, aggregate summaries, API response behavior, bounded input, and dashboard rescan affordances.

### v1.0.3 (2026-08-01)

#### Change-focused scan history
- Added a dashboard history dialog for every recent target.
- Added newest-first scan timeline summaries with total links, links needing attention, newly broken links, and fixed links.
- Added `GET /api/dashboard/target-history` with required URL validation, bounded history limits, and existing dashboard authentication.
- Added `HistoryStore.get_target_timeline()` to derive per-scan changes from retained history.
- Added accessible dialog semantics, loading/empty/error states, explicit close behavior, and a non-color textual representation of changes.

#### Tests
- Added TDD acceptance coverage for timeline derivation, first-scan baseline behavior, API validation, API responses, and dashboard history interactions.


### v1.0.4 (2026-08-01)

#### Actionable history details
- Added deterministic URL-level detail lists for newly broken and fixed links in every scan timeline record.
- Added expandable Change details sections to the dashboard history dialog.
- Added client-side history JSON export for handoff, issue creation, and offline review.
- Added empty states for scans with no new failures or fixes.

#### Quality
- Repaired a malformed embedded dashboard JavaScript sequence discovered by syntax validation.
- Added a Node.js-backed regression test that extracts the embedded script and runs `node --check` when Node.js is available.
- Added TDD tests for change-detail payloads, deterministic ordering, expandable UI details, and export affordance.
