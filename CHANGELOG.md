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

### v1.0.5 (2026-08-01)

#### Faster scan-result review
- Added All results, Needs attention, and Healthy filters to the latest scan results.
- Added instant client-side search across URL, reason, and HTTP status.
- Added an accessible live count showing visible and total result counts.
- Added CSV export for the currently visible result subset.
- Added spreadsheet-formula neutralization to the browser-generated CSV export.
- Export is disabled when no rows are visible, and meaningful empty-search feedback is shown.

#### Tests
- Added TDD acceptance coverage for result filters, search, visible-result export, and live-count accessibility.
- Preserved the embedded JavaScript syntax regression check.

### v1.0.6 (2026-08-01)

#### Browser batch scanning
- Added Single page and Multiple pages scan modes to the dashboard.
- Added a multiline batch URL form supporting up to 50 unique URLs.
- Added configurable browser-side concurrency input constrained to 1 through 20.
- Added duplicate, empty, and over-limit validation before a request is sent.
- Integrated batch responses with the existing result filters, search, visible-count, and CSV export workflow.
- Added accessible scan-mode tabs and live batch progress/outcome feedback.

#### Tests
- Added TDD acceptance coverage for scan modes, bulk input, concurrency controls, duplicate validation, endpoint integration, shared result review, and live status semantics.
- Re-ran embedded JavaScript syntax validation and the complete regression suite.

### v1.0.7 (2026-08-01)

#### Source-aware result review
- Preserved the scanned source-page URL on every browser result row.
- Added a Source page column to single and batch result tables.
- Added a source-page selector populated from the current result set.
- Extended result search to include source-page URLs.
- Added source URL to focused CSV exports.
- Applied the same source-context model to single scans and flattened batch responses.

#### Tests
- Added TDD acceptance coverage for source preservation, source filtering, source-aware search, CSV schema, and single-scan context.
- Re-ran batch, result-review, JavaScript syntax, and full regression suites.

### v1.1.0 (2026-08-01)

#### Durable saved projects
- Added SQLite-backed named projects for recurring single-page and batch targets.
- Added target normalization, stable ordering, deduplication, credential rejection, and a 50-target project limit.
- Added authenticated `GET /api/projects` and `POST /api/projects` endpoints.
- Added authenticated project archival through `DELETE /api/projects/{id}` without deleting scan history.
- Added a dashboard project form, empty/loading/error/success states, project list, one-action target loading, and archival confirmation.
- Loading a one-target project selects Single page; loading a multi-target project selects Multiple pages.

#### Security and reliability
- Project API targets pass the existing SSRF validation before persistence.
- Project state uses SQLite with foreign keys and WAL mode and survives process restarts.
- Project database location is configurable with `BROKENLINKBRIEF_PROJECT_DB`.

#### Tests and documentation
- Added TDD unit, API integration, validation, archive, dashboard contract, and JavaScript syntax tests.
- Added the full product analysis and next-version requirements report to `docs/PRODUCT_ANALYSIS_AND_REQUIREMENTS.md`.
- Added implementation, setup, migration, testing, and packaging documentation.

### v1.1.1 (2026-08-01)

#### Complete project lifecycle
- Added project editing for names and ordered target lists.
- Added archived-project browsing and non-destructive restoration.
- Added authenticated `PUT /api/projects/{id}` and `POST /api/projects/{id}/restore` endpoints.
- Added Edit, Cancel edit, Show archived, Show active, and Restore dashboard actions.
- Project updates retain stable IDs and reapply normalization, deduplication, limits, credential rejection, and SSRF validation.

#### Tests
- Added TDD store, API integration, browser workflow, archive listing, and restore coverage.
- Re-ran the complete regression suite and embedded JavaScript syntax validation.

### v1.1.2 (2026-08-01)

#### One-action project scanning
- Added **Run project scan** for active projects.
- Single-target projects immediately run the single scan workflow.
- Multi-target projects immediately run the batch workflow.
- Project cards now show the latest retained project health summary.
- Added scanned/unscanned target counts, latest link total, failure count, and latest scan time to project API payloads.
- Added `BROKENLINKBRIEF_HISTORY_DIR` so project summaries and scan history can share a configurable persistent location.

#### Tests
- Added failing-first tests for latest-scan aggregation, unscanned projects, API summaries, and one-action browser scanning.
- Re-ran project lifecycle, JavaScript syntax, and full regression suites.

### v1.1.3 (2026-08-01)

#### Portable project configuration
- Added versioned JSON export for active and archived project configurations.
- Added JSON project import with a new stable project identity.
- Added dashboard **Export project** and **Import project** workflows.
- Added authenticated `GET /api/projects/{id}/export` and `POST /api/projects/import` endpoints.
- Imports reapply schema validation, target type checks, normalization, deduplication, project limits, credential rejection, and SSRF validation.
- Runtime scan history, project IDs, archive state, and timestamps are intentionally excluded from portable configuration files.

#### Tests
- Added failing-first store, schema, API, security, and browser contract tests.
- Re-ran project, dashboard JavaScript, and full regression suites.

### v1.1.4 (2026-08-01)

#### Project duplication
- Added one-action duplication for active and archived projects.
- Duplicates receive a new stable identity and always start active.
- Target order and normalized values are preserved without copying history or runtime state.
- Copy names are selected deterministically as `copy`, `copy 2`, and so on.
- Added authenticated `POST /api/projects/{id}/duplicate`.
- Added dashboard **Duplicate** action and accessible success/error feedback.

#### Tests
- Added failing-first store, copy-name, API, missing-project, and browser contract tests.
- Re-ran all project tests, dashboard JavaScript validation, and the full regression suite.

### v1.1.5 (2026-08-01)

#### Pinned projects
- Added persistent pin and unpin actions for frequently used projects.
- Active and archived lists now place pinned projects first, followed by recently updated projects.
- Added authenticated `POST /api/projects/{id}/pin` with strict boolean validation.
- Added a backward-compatible SQLite schema migration for existing 1.1.x project databases.
- Duplicated and imported projects start unpinned so personal prioritization does not leak into new copies.
- Added explicit dashboard guidance and accessible status feedback.

#### Tests
- Added failing-first persistence, ordering, migration, duplication, API, and browser contract tests.
- Re-ran all project tests, dashboard JavaScript validation, and the complete regression suite.

### v1.2.0 (2026-08-01)

#### Scheduled scanning
- Added cron-based recurring scans with SQLite persistence and atomic worker leasing (`SchedulerService`, `ScheduleStore`).
- Added YAML/JSON project configuration with validation (`scheduler_config.py` — `load_projects_config`, `validate_project_config`).
- Added `ScheduledScanExecutor` for running scans with retry logic and result aggregation.
- Added `ScanHistoryStore` for persisting scan results in SQLite with pagination and regression flag tracking.
- Added `RegressionDetector` for comparing current scans against the last successful scan to surface newly broken links.
- Added `RegressionNotifier` for formatting and sending regression/resolution alerts.
- Added `aggregate_scheduled_projects()` for merging schedules with project metadata for dashboard views.
- Added cron expression parsing and timezone validation helpers.
- SSRF validation enforced in both `SlackNotifier.__init__` and `deliver_webhook()`.

#### Documentation
- Added `docs/scheduled-scanning.md` — full reference: config format, cron patterns, deployment guides (systemd, Docker, bare metal, Docker Compose).
- Added `examples/schedule-config.yaml` — annotated 3-project example config.
- Updated README with scheduled scanning features, quick start, and cron reference table.
- Added changelog entry for v1.2.0.
