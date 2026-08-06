# Implementation Plan

## Executive Summary

This pass will deliver one coherent vertical slice called **Trusted Finding to Verified Repair**. It contains three integrated features:

1. **Evidence-aware scan outcomes:** normal static scans will retain bounded probe evidence and classify each checked link as `CONFIRMED_BROKEN`, `TRANSIENT`, `BOT_BLOCKED`, `RECOVERED`, or `INCONCLUSIVE` instead of treating every transport failure or HTTP error as equally actionable.
2. **Durable, source-aware findings:** confirmed failures will create or update stable project findings containing all observed source occurrences, anchor text, safe context, evidence, lifecycle state, assignee, and ignore metadata. The dashboard will add a focused Findings workspace without a frontend-framework rewrite.
3. **Targeted Verify Fix:** users will recheck one finding and its affected source pages, receiving an evidence-backed result of recovered, removed from source, still broken, or inconclusive. Successful verification can resolve a finding; later confirmed recurrence reopens it.

The scope directly implements the three P0 research priorities and can be completed in one pass because the repository already contains `confidence.py`, `triage.py`, saved projects, scan/history services, an embedded dashboard, SQLite conventions, security policy primitives, and extensive pytest coverage. The work will expand and integrate these foundations rather than create a new platform.

The pass will preserve existing `/scan`, `/scan-batch`, project, history, export, notification, and CLI behavior. Existing response bodies remain backward-compatible. New evidence and finding behavior will be exposed through additive versioned fields and new `/api/findings` endpoints. Existing raw scan exports remain unchanged unless a new explicit detailed format is requested. No frontend framework, job queue, hosted account system, billing system, or database replacement is included.

## Current-State Validation

The research report matches the supplied 1.2.0 project and is actionable.

- `src/brokenlinkbrief/package.py` implements static link extraction, HEAD/GET checking, batch scans, exports, token helpers, URL validation, and JSONL history.
- `src/brokenlinkbrief/spa_scanner.py` adds optional Playwright rendering.
- `src/brokenlinkbrief/projects.py` provides migration-aware SQLite project storage, target ordering, archive/restore, import/export, duplication, pinning, and scan summaries.
- `src/brokenlinkbrief/confidence.py` already defines probe attempts and deterministic confidence classifications, but the normal scan path does not consume them.
- `src/brokenlinkbrief/triage.py` already parses source occurrences and has a minimal findings/tasks store, but it generates a new finding on every record and is not integrated with projects, scans, APIs, or the dashboard.
- `src/brokenlinkbrief/app.py` delivers the main HTTP API and a large embedded dashboard with scan, batch, projects, recent targets, history, filtering, exports, and charts.
- `src/brokenlinkbrief/policy.py` and `package.validate_scan_url` provide overlapping outbound controls that must not be bypassed.
- The repository uses only standard-library runtime dependencies, SQLite, optional Playwright, pytest, and Ruff. Packaging uses setuptools and deployment uses Docker/Railway.
- Existing tests cover APIs, dashboard JavaScript syntax and contracts, projects, schedules, SSRF, SPA scanning, notifications, history, diffing, and the independent confidence/triage primitives.

The report’s recommended vertical slice is feasible because it can reuse the current scanner and HTTP server while adding a small domain service and additive APIs. It is bounded by excluding asynchronous durable jobs, global navigation, secure sessions, and integrations that would substantially enlarge the architecture.

Known current-state constraints that the implementation must respect:

- Python 3.10 and 3.11 compatibility.
- Existing response shapes and query-token compatibility.
- SQLite migration without destructive reset.
- No mandatory Playwright install for static scans.
- SSRF validation for every new outbound verification request and redirect hop.
- Existing CSV formula-injection protection and HTML escaping.
- Existing tests must remain green.
- The embedded frontend is fragile enough that JavaScript syntax validation and DOM-level contract coverage are mandatory for every UI change.

## Research Priorities

The candidate backlog translated from `research-findings.md` is:

| Candidate | Research priority | Value | Pass feasibility | Decision |
|---|---:|---:|---:|---|
| Evidence-aware classification and retry evidence | P0 | Reduces false positives and alert noise | High because classifier exists | Selected |
| Source occurrence and durable findings | P0 | Turns scan output into repairable work | Medium-high because parser/store exist | Selected |
| Targeted Verify Fix | P0 | Closes the repair loop without full rescans | Medium | Selected |
| Durable asynchronous jobs | P1 | Refresh-safe progress, cancel, retry | Low for this pass; cross-cutting | Deferred |
| Global navigation and overview redesign | P1 | Scalable information architecture | Medium-low before findings validation | Deferred |
| Secure browser sessions and integrated RBAC | P1 | Removes query-token risk | Low; needs identity/session design | Deferred |
| Schedule administration UI | P1 | Makes recurring monitoring accessible | Medium, but unrelated to the selected repair slice | Deferred |
| Exclusion and grace-rule editor | P1 | Controls expected noise | Medium; follows evidence policy | Deferred |
| Notification administration and delivery log | P2 | Easier operations | Low before stable finding events | Deferred |
| Sitemap/repository ingestion | P2 | Faster onboarding and broader use | Medium, but expands crawl scope | Deferred |
| CI-to-hosted finding identity | P2 | Unified developer operations | Low before finding IDs stabilize | Deferred |
| Agency portfolio and white-label reporting | P2 | Commercial expansion | Low before organization delivery | Deferred |
| Issue-tracker integration | P2 | External handoff | Low before internal lifecycle is stable | Deferred |

## Selected Scope for This Pass

### Feature 1: Evidence-aware scan outcomes

The static scan engine will collect a bounded sequence of probe attempts for each target link, apply deterministic confidence classification, and make that assessment available to the finding service. The scanner must avoid broad network-behavior changes: the current HEAD then GET fallback remains the first evidence path. A retry is permitted only for transport errors, HTTP 429, and HTTP 5xx responses, with a default maximum of two total attempts per method path and a bounded backoff that can be configured for tests. Repeated 404/410 evidence may become confirmed; a successful response takes precedence as recovered; contradictory 403 and successful browser/static evidence is bot-blocked; transport-only evidence is transient; all other combinations are inconclusive.

The existing `LinkResult` fields remain unchanged. An internal `ScanObservation` domain value will pair the existing result with attempts and assessment. Existing public `scan_page()` continues returning `list[LinkResult]`. A new internal or explicitly named detailed scanner will return observations for finding processing. This avoids breaking existing callers, JSON, CSV, Markdown, and JSONL output.

### Feature 2: Durable source-aware findings

The project database will be extended with migration-safe finding tables. Findings are unique per project and normalized target URL. Occurrences are unique per finding and source URL plus anchor/context fingerprint. Repeated scans update `last_seen_at`, current evidence, status, and occurrence presence instead of creating duplicates.

Only `CONFIRMED_BROKEN` observations create or reopen actionable findings by default. `TRANSIENT`, `BOT_BLOCKED`, `RECOVERED`, and `INCONCLUSIVE` observations are retained as evidence when a finding already exists but do not create a new open finding. This rule directly protects users from noise. A later confirmed failure reopens a resolved finding and records an audit event. A recovered result does not automatically resolve an open finding until targeted verification has checked both the target and source occurrence conditions.

The dashboard will gain a Findings section below Saved Projects and above scan controls. It will contain a project selector, state/classification/assignee filters, search, a result count, a responsive table, and an accessible detail dialog. It is intentionally not a full global-navigation redesign.

Minimal lifecycle actions in this pass are:

- Acknowledge an open finding.
- Assign or clear a plain-text assignee.
- Ignore with required reason and optional ISO date expiry.
- Reopen an ignored or resolved finding.
- View evidence and all source occurrences.
- Start Verify Fix.

Comments, labels, due dates, workflow priority, bulk actions, and organization membership are excluded.

### Feature 3: Targeted Verify Fix

Verification is synchronous in this pass and must be bounded. It checks the normalized target using the evidence-aware scanner, then fetches each currently active source page and determines whether the target occurrence remains present. Verification returns one of four outcomes:

- `RECOVERED`: target evidence is successful and at least one source still contains the link. The finding becomes resolved.
- `REMOVED_FROM_SOURCE`: no active source occurrence remains. The finding becomes resolved even if the old target remains broken.
- `STILL_BROKEN`: target is confirmed broken and at least one source still contains it. The finding remains or becomes open.
- `INCONCLUSIVE`: source fetch or target evidence cannot support a safe transition. State is unchanged.

The operation records verification time, outcome, evidence, acting identity if available, and an audit event. It never deletes history. If a source cannot be fetched, it is reported separately and cannot be treated as removal. All target and source URLs pass existing outbound validation before network access.

## Deferred Scope and Rationale

Twelve recommendations are deferred:

1. **Durable asynchronous jobs:** prerequisite is a unified job schema, worker lifecycle, cancellation protocol, and recovery tests. Suggested next phase: Monitoring Operations.
2. **Global application navigation:** defer until the Findings workspace validates the needed sections and terminology. Suggested next phase: UX Scale-up.
3. **Secure browser sessions and integrated RBAC:** requires identity, cookie, CSRF, migration, and deployment decisions beyond this repair slice. Suggested next phase: Security and Multi-user Foundation.
4. **Schedule management UI:** existing scheduler can be surfaced after manual/scheduled scans share stable job and finding events. Suggested next phase: Monitoring Operations.
5. **Project exclusion and grace-rule editor:** evidence policy must stabilize first. Suggested next phase: Noise Controls.
6. **Notification administration and delivery log:** should consume stable finding-transition events rather than raw scan status. Suggested next phase: Integrations.
7. **Sitemap ingestion:** expands crawling scope, recursion, limits, robots behavior, and UX. Suggested next phase: Onboarding and Scale.
8. **Repository-document ingestion:** needs file discovery, line-level source locations, and CI contract design. Suggested future phase: Developer Workflows.
9. **CI-to-dashboard stable identity:** depends on final finding schema and hosted/shared endpoint semantics. Suggested future phase: Developer Workflows.
10. **Issue-tracker integration:** internal lifecycle must be the source of truth first. Suggested future phase: Integrations.
11. **Agency portfolio and branded reporting:** depends on delivered organizations, RBAC, and project isolation. Suggested future phase: Commercial Expansion.
12. **Hosted billing and plan enforcement:** no billing evidence is needed to validate the selected product workflow. Suggested future phase: Commercialization.

## Product Requirements

### PR-1: Evidence collection and classification

**Research problem and evidence:** False positives from transient requests, throttling, bot defenses, and raw status handling are a high-confidence pain point. The repository already has a classifier that the delivered scanner does not use.

**User story:** As a site operator, I want each reported failure to explain the evidence and confidence so that I do not spend time investigating a temporary or crawler-specific failure.

**Functional behavior:**

- Each detailed link check records method, status or sanitized error category, latency, and attempt sequence.
- The evidence classifier returns exactly one supported classification and a human-readable reason.
- Retryable outcomes are transport error, 429, and 5xx. 404 and 410 require repeated terminal evidence but do not receive unbounded retries.
- Retry count, timeout, and backoff are injectable for deterministic tests; production defaults remain bounded.
- Existing `scan_page()` and output renderers retain their current contract.
- New detailed scan paths must use the same URL normalization and SSRF boundary as existing scans.

**Inputs:** normalized HTTP/HTTPS target URL, timeout, retry policy, requester abstraction.

**Outputs:** existing `LinkResult`; detailed observation containing target, attempts, classification, reason, and observed time.

**Validation and business rules:**

- Empty attempt lists classify as `UNVERIFIED` internally and cannot create findings.
- A 2xx or 3xx response is successful evidence.
- Repeated 404 or 410 terminal evidence can classify as `CONFIRMED_BROKEN`.
- Only transport failures classify as `TRANSIENT`.
- Contradictory restricted and successful evidence classifies as `BOT_BLOCKED` where current classifier rules apply.
- Error strings persisted or returned must not contain credentials, authorization headers, cookies, or full exception representations that may expose secrets.
- Maximum attempt count is enforced even if the requester repeatedly fails.

**Edge cases and failure behavior:** malformed URLs and unsafe destinations retain existing 400 behavior; timeout produces evidence rather than crashing the whole scan; one target failure does not abort remaining links; a persistence failure logs an error and preserves the scan response but must not claim a finding was saved.

**Dependencies:** `package.py`, `confidence.py`, `policy.py`, current request helpers, app scan orchestration.

**Backward compatibility:** no removal or renaming of existing result fields, formats, endpoints, status codes, or CLI behavior. Detailed fields are additive and opt-in or confined to findings APIs.

**Acceptance criteria:**

- The existing export and endpoint contract tests pass unchanged.
- Two 404/410 attempts produce `CONFIRMED_BROKEN`; transport-only attempts produce `TRANSIENT`; a successful attempt prevents confirmed-broken state; supported contradictory evidence produces `BOT_BLOCKED`.
- Every detailed observation contains one to the configured maximum number of attempts and a non-empty classification reason.
- A simulated 429 followed by 200 is not actionable and does not create a finding.
- Test-mode backoff introduces no real sleep.
- No persisted evidence field contains test sentinel secret values.

**Non-goals:** adaptive machine learning, content-based soft-404 detection, arbitrary custom classification expressions, distributed rate limiting, or real-browser fallback for every static link.

### PR-2: Stable project findings and occurrences

**Research problem and evidence:** Users need exact source context and persistent repair state. Current source URLs are shown, but anchor text, context, stable identity, assignment, ignore state, and audit history are not integrated.

**User story:** As a content operator, I want one durable finding with every page where the link appears so that I can assign, repair, and track it without exporting a spreadsheet.

**Functional behavior:**

- A confirmed observation associated with a saved project upserts one finding by project and normalized target.
- All matching source occurrences are stored with source URL, anchor text, escaped bounded context, first seen, last seen, and active flag.
- Findings expose ID, project ID, target, latest HTTP status, classification, reason, state, assignee, ignore metadata, first/last seen, latest verification, occurrence count, and version.
- Supported states are `OPEN`, `ACKNOWLEDGED`, `IGNORED`, and `RESOLVED`.
- Assignment is optional trimmed text with a maximum length of 120 characters.
- Ignore requires a trimmed reason from 1 to 500 characters and optional calendar-date expiry. Expired ignores are treated as open on the next list/read/update transaction and record an audit event.
- Every state, assignment, ignore, reopen, verification, and automatic recurrence transition records an immutable audit event.
- API updates require an expected integer version. A stale version returns HTTP 409 and current representation.

**Inputs:** project ID, detailed observations, extracted source HTML occurrences; API list filters and lifecycle action payloads.

**Outputs:** paginated JSON lists, single finding detail, audit events, and dashboard-rendered summaries.

**Validation and business rules:**

- Findings can only be created for existing non-archived projects.
- An archived project’s findings remain readable but cannot be verified or changed until the project is restored.
- Only actionable confirmed evidence creates/reopens a finding.
- Repeated observations update the same finding and do not duplicate occurrences.
- Context is plain escaped text or an escaped bounded anchor representation, maximum 500 characters; scripts, attributes other than safe display text, credentials, and headers are never stored.
- Search matches target URL, source URL, anchor text, and assignee case-insensitively.
- Default list shows active `OPEN` and `ACKNOWLEDGED` findings, ordered by latest confirmed observation descending, then stable ID.
- Limit defaults to 50 and is constrained to 1 through 100; offset defaults to 0 and cannot be negative.

**Edge cases and failure behavior:** invalid project/filter/state yields 400; missing finding yields 404; archived project mutation yields 409; stale expected version yields 409; database write failure returns 500 with a stable public code and logs correlation-safe context; no source occurrence means the evidence is retained but the UI labels location unavailable.

**Dependencies:** expanded finding store, projects database connection conventions, `triage.extract_occurrences`, evidence service, app routing, dashboard rendering.

**Backward compatibility:** current minimal `FindingStore.record()` and `assign()` callers must either remain supported through a compatibility adapter or all internal tests/callers must migrate without changing their externally documented behavior. Existing project database rows are migrated in place.

**Acceptance criteria:**

- Repeating the same confirmed target in the same project returns the same finding ID.
- The same target in two projects has two findings.
- Two source pages for one target appear as two active occurrences under one finding.
- Missing occurrences become inactive only after a successful source scan proves absence; an unreachable source does not deactivate them.
- Lifecycle actions enforce validation, optimistic version checks, and audit entries.
- A later confirmed observation reopens a resolved finding and records `AUTO_REOPENED`.
- No new finding is created from transient, recovered, bot-blocked, inconclusive, or unverified evidence.

**Non-goals:** comments, labels, due dates, bulk actions, organization membership, email invitations, or workflow customization.

### PR-3: Targeted verification

**Research problem and evidence:** Users repeatedly rerun checks to prove fixes; full rescans are slow and can create quota anxiety. Current “Scan again” does not resolve durable work.

**User story:** As a repair owner, I want to verify one finding and close it only when evidence proves the target recovered or the source no longer contains the link.

**Functional behavior:**

- `POST /api/findings/{id}/verify` accepts expected version and starts a bounded synchronous verification.
- The target is checked with the evidence-aware checker.
- Each active source is fetched and parsed for occurrences of the normalized target.
- The service calculates `RECOVERED`, `REMOVED_FROM_SOURCE`, `STILL_BROKEN`, or `INCONCLUSIVE` according to the selected-scope rules.
- The finding state transitions and audit event are committed atomically with the verification record.
- The response includes verification outcome, resulting finding, target assessment, count of sources checked, count still containing the target, and sanitized source failures.

**Validation and business rules:**

- SSRF validation applies independently to target and each source immediately before fetch and to redirect hops.
- Verification is disabled for archived projects and while the selected finding is already being verified in the current process. A second request returns 409.
- A successful target response resolves even when a source still contains the link; the occurrence remains active for historical/source context.
- Complete proven source removal resolves even if target remains broken.
- Any unreachable source prevents a `REMOVED_FROM_SOURCE` conclusion unless at least one successfully checked source still contains the link, in which case the outcome follows target evidence.
- Inconclusive verification never changes workflow state.
- A later confirmed scan reopens a resolved finding.

**Edge cases and failure behavior:** if target validation fails because data became unsafe, verification is inconclusive and logs a security event; source parse errors are isolated; database conflict returns 409; network timeouts are reported as sanitized source failures; the UI remains usable and offers retry.

**Dependencies:** evidence checker, occurrence extraction, finding service, project state, app routing, dashboard detail dialog.

**Backward compatibility:** additive endpoint only; no automatic deletion of scan history or legacy rows.

**Acceptance criteria:**

- Recovered target resolves and records evidence.
- Proven removal from all successfully fetched sources resolves.
- Confirmed broken target plus retained source remains open.
- Any insufficient evidence leaves state unchanged and returns `INCONCLUSIVE`.
- Verification records are durable after reopening the database.
- Duplicate concurrent verification is rejected deterministically.
- UI announces start, success, still-broken, inconclusive, and network-failure outcomes without losing the selected finding.

**Non-goals:** background verification jobs, scheduled per-finding verification, automatic content edits, replacement suggestions, or CAPTCHA/login automation.

## UI and UX Specification

### Personas and primary journey

Primary persona: a content/SEO operator monitoring one or more saved projects. Secondary persona: a developer reviewing credible regressions. The main journey is:

**Open dashboard → choose project findings → identify a confirmed open finding → inspect source and evidence → acknowledge/assign or ignore → repair externally → Verify Fix → see resolved confirmation.**

The friendly failure path is:

**Verify Fix → source timeout or contradictory evidence → state stays unchanged → dialog announces inconclusive outcome, lists affected source failures, and offers Retry verification and Close.**

### Information architecture

Retain the single-page dashboard to avoid a rewrite. Within it, use this order:

1. Page title and compact product status.
2. Saved Projects.
3. Findings workspace.
4. Scan Pages.
5. Recent Pages.
6. Historical analytics.

The Findings workspace is project-scoped. Loading a project from a project card sets the findings project filter as well as scan targets. URL query parameters are not required in this pass; in-memory filter state is acceptable because global navigation and shareable views are deferred.

### Design system decision

Use the existing semantic HTML, CSS custom styling, and vanilla JavaScript. Do not add React, Vue, a CSS framework, or a component library. The current application is a single standard-library server with no frontend build pipeline, and the selected workflow can be delivered with reusable CSS classes and small JavaScript modules/functions. New UI patterns must reuse existing colors and controls while introducing CSS custom properties for shared color, spacing, radius, and focus-ring tokens inside the existing stylesheet. Asset extraction is allowed only if required to keep `app.py` maintainable and packaging remains build-free; it is not a pass requirement.

### Visual and component rules

- Base spacing tokens: 4, 8, 12, 16, 24, and 32 CSS pixels.
- Body text minimum 16 CSS pixels; dense table text minimum 14 CSS pixels; line height at least 1.4.
- Interactive controls minimum 44 by 44 CSS pixels where layout permits; compact table actions must have at least 24 by 24 target plus 8-pixel separation, consistent with WCAG 2.2 target-size expectations.
- Visible focus ring: minimum 2 CSS pixels, at least 2-pixel offset, and contrast of at least 3:1 against adjacent colors.
- Text contrast: at least 4.5:1 for normal text and 3:1 for large text and UI boundaries.
- Status never relies on color alone. Every badge includes visible text and an accessible name.
- Motion is limited to optional smooth scrolling. Under `prefers-reduced-motion: reduce`, disable smooth scrolling and transitions.
- Cards use existing dark surfaces and border/elevation rules; no gradient, animation, or decorative redesign is required.

### Findings workspace hierarchy

1. Heading, one-sentence purpose, and live total.
2. Filter bar: project selector, state selector, classification selector, assignee/search input, Refresh.
3. Loading skeleton with three non-interactive rows and an accessible “Loading findings” status.
4. Result table on desktop/tablet; stacked finding cards below 640 pixels.
5. Row primary action: View details. Secondary visible status badges only; lifecycle actions live in detail dialog to avoid crowded tables.
6. Empty state:
   - No project selected: “Choose a saved project to review findings.” CTA focuses project selector.
   - Project has never produced findings: “No confirmed broken links yet.” CTA runs the project scan.
   - Filters have no matches: “No findings match these filters.” CTA clears filters.
7. Error state includes a short sanitized explanation, Retry button, and preserves filters.

### Detail dialog

The dialog title is the target host/path, with a visually secondary full URL. Content order:

1. State, classification, latest status, first/last seen, occurrence count.
2. Primary action: Verify Fix.
3. Workflow controls: Acknowledge, assignment input/save, Ignore form, Reopen where eligible.
4. Evidence timeline, newest first, collapsed after the latest record.
5. Source occurrences with source URL, anchor text, bounded context, first/last seen, and active/inactive label.
6. Audit history, collapsed by default.

Use a native `<dialog>` consistent with the existing history dialog. On open, focus the dialog heading or primary action. On close, return focus to the originating row button. Escape closes only when no verification or save request is pending. While a mutation is pending, disable only related actions, set `aria-busy="true"`, and keep Close available unless closing would discard a local form.

### Form validation and feedback

- Assignment: inline error for more than 120 characters; empty value means clear.
- Ignore: reason is required; expiry must be a valid date not earlier than the current local date.
- API validation errors are announced through an `aria-live="assertive"` region and associated with the relevant control using `aria-describedby`.
- Success messages use a polite live region and name the action: “Finding acknowledged,” “Assigned to Alice,” “Finding ignored until 2026-09-01,” “Fix verified and finding resolved.”
- Conflict response: show “This finding changed in another session,” refresh detail automatically, preserve unsaved form values where safe, and require the user to retry.

### Responsive behavior

- Desktop, 1024 pixels and wider: filter bar in one wrapping row; table columns for Target, State, Classification, Occurrences, Assignee, Last seen, Action.
- Tablet, 640 to 1023 pixels: filters in two rows; hide full target text behind wrapping/truncation with accessible full value; retain all actions.
- Mobile, below 640 pixels: replace table presentation with cards using the same semantic list; show target, state, classification, source count, last seen, and View details. Dialog uses full viewport width minus 16 pixels and no horizontal scrolling.
- At 200% zoom and 320 CSS-pixel viewport, no critical action or text is clipped and horizontal page scrolling is not required.

### Keyboard and screen-reader behavior

- Filter controls follow DOM order and have explicit `<label>` elements.
- Results use a caption and column headers; mobile cards use headings and definition lists.
- Status updates use live regions but do not steal focus.
- Opening detail moves focus inside; closing restores focus.
- Dialog supports Escape and a visible Close button.
- Evidence lists use ordered lists with timestamps in `<time datetime>`.
- Verification progress announces once at start and once at completion, avoiding repeated noisy updates.
- External source/target links open in a new tab with `rel="noopener noreferrer"` and an accessible suffix indicating “opens in new tab.”

### UI verification

The developer must:

- Run the server using the repository-supported module entry point.
- Verify the dashboard loads without JavaScript console syntax/runtime errors.
- Exercise one successful flow and each friendly failure state using deterministic test fixtures or mocked server I/O.
- Run existing Node syntax validation when Node is available.
- Add browser-level tests only if Playwright is already available in the environment; do not make Playwright a mandatory runtime dependency.
- When browser tooling permits, capture desktop at approximately 1440 by 900, tablet at 768 by 1024, and mobile at 390 by 844 for the populated list, empty state, detail dialog, and verification failure. Screenshots are audit artifacts, not committed product assets unless the development environment’s conventions already support them.
- Perform keyboard-only traversal, 200% zoom/reflow, reduced-motion, and one screen-reader smoke test. Record results in `development-report.md`.

## Screen Inventory and User Flows

### Existing screens retained

- Dashboard single-page application.
- Saved Projects panel and project form.
- Single and batch scan forms/results.
- Recent target list and scan-history dialog.
- Analytics cards and charts.
- Existing JSON/CSV/Markdown/JSONL API/CLI experiences.

### New UI surfaces

1. **Findings workspace panel** with filters, count, loading/empty/error states, results, and refresh.
2. **Finding detail dialog** with evidence, occurrences, lifecycle controls, audit trail, and verification.
3. **Verification result state** inside the detail dialog.
4. **Project scan completion message** enhanced with the number of confirmed findings created/reopened when detailed processing is active, without changing existing link-count text.

### End-to-end happy flow

1. User opens `/dashboard` and the Saved Projects and Findings panels load independently.
2. User selects an active project in the Findings project filter.
3. API returns open/acknowledged findings. The live count announces the result.
4. User opens one finding. Focus moves to Verify Fix; evidence and source occurrences are visible.
5. User assigns the finding and receives a success announcement.
6. User repairs the source or destination outside the product.
7. User selects Verify Fix. Button becomes disabled and dialog becomes busy.
8. Target and sources are checked. The API returns `RECOVERED` or `REMOVED_FROM_SOURCE` and state `RESOLVED`.
9. Dialog announces resolution, updates details, and the background list count decreases without losing filter state.
10. User closes the dialog; focus returns to the row location or the next logical result if the row left the active filter.

### Friendly failure recovery flow

1. User starts verification.
2. One source times out and the target evidence is insufficient.
3. API returns `INCONCLUSIVE`, preserves workflow state, and supplies sanitized source failures.
4. Dialog announces that no state changed, displays which source could not be checked, and offers Retry verification.
5. User may retry or close; filters and list state remain intact.

### First-run experience

If there are no saved projects, Findings shows an explanatory empty state and a “Create a project above” button that focuses Project name. After project creation, it becomes selected automatically. If a project has no findings, the panel explains that only confirmed failures become findings and offers Run project scan. No tour, modal onboarding, sample data, or account setup is added.

## Architecture and Technical Design

### Component boundaries

1. **Request/probe layer (`package.py` or new `probing.py`):** performs bounded HEAD/GET requests and emits normalized attempts without persistence.
2. **Evidence domain (`confidence.py`):** owns immutable attempts, classification constants, and deterministic assessment. Extend formatting/validation, not network I/O.
3. **Occurrence extraction (`triage.py` or new `occurrences.py`):** parses source HTML into normalized, bounded occurrences. It must not perform HTTP I/O.
4. **Finding persistence (`findings.py` recommended):** migration, CRUD, upsert, listing, optimistic concurrency, audit and verification records. Keep legacy `triage.FindingStore` as a compatibility wrapper if needed.
5. **Finding application service (`finding_service.py` recommended):** coordinates project lookup, detailed observations, occurrence reconciliation, lifecycle transitions, and verification. It owns business rules but delegates I/O.
6. **HTTP delivery (`app.py`):** authentication, request parsing, stable error mapping, additive endpoints, and dashboard asset delivery.
7. **Dashboard JavaScript:** independent functions for loading list/detail, mutations, verification, rendering, escaping, and focus restoration. Do not embed policy rules that belong on the server.

### Data flow

Normal project scan:

1. Validate source URL.
2. Fetch source HTML through current scanner path.
3. Extract occurrences once.
4. Check unique normalized targets and collect detailed observations.
5. Return existing `LinkResult` response.
6. If a saved project context is available, pass observations and occurrences to FindingService.
7. In one database transaction, upsert actionable findings, update evidence and occurrences, record audit events, and return a processing summary.
8. Notifications may continue current behavior in this pass, but new finding events must be available for a later transition. Do not silently change notification semantics unless tests and documentation explicitly cover the change.

Finding list/detail:

1. Dashboard calls additive API with project/filter parameters.
2. Server validates and queries paginated store.
3. Client renders escaped text only and keeps the latest integer version for mutations.

Verification:

1. API validates token, finding, project state, expected version, and in-process lock.
2. Service validates and probes target.
3. Service fetches active sources, extracts occurrences, and records per-source result.
4. Service determines outcome using server rules.
5. Transaction writes verification, evidence, occurrence active state, finding transition/version, and audit event.
6. Response refreshes detail and list.

### Persistence design

Use the configured `BROKENLINKBRIEF_PROJECT_DB` so project and finding transitions can share referential integrity. Add tables through `CREATE TABLE IF NOT EXISTS` plus explicit schema introspection/migration, following `ProjectStore` conventions.

Required logical tables:

- `findings`: stable ID, project ID, normalized target, latest status, classification, reason, workflow state, assignee, ignore reason/expiry, first/last seen, resolved timestamp, latest verification timestamp/outcome, integer version; unique `(project_id, target_url)`; foreign key to projects.
- `finding_occurrences`: ID, finding ID, source URL, anchor text, bounded context, fingerprint, active flag, first/last seen; unique `(finding_id, source_url, fingerprint)`.
- `finding_evidence`: ID, finding ID, observed time, method, status, error category, latency, sequence, classification snapshot, reason, scan/source context.
- `finding_verifications`: ID, finding ID, started/completed timestamps, outcome, source check counts, sanitized failure summary, version before/after.
- `finding_audit_events`: ID, finding ID, event type, timestamp, actor label, old/new state, sanitized metadata JSON.

Indexes are required on project/state/last_seen, target, assignee, occurrence source, evidence finding/time, and audit finding/time.

Migration rules:

- Never drop or rewrite existing tables.
- Migration is idempotent and runs inside a transaction.
- Existing minimal `triage.py` findings/tasks tables may coexist. Do not silently reinterpret them as project findings because they lack project identity and timestamps.
- If old minimal tables use the same desired names, new tables must use unambiguous prefixed names such as `project_findings`; document the choice.
- A database from 1.1.x/1.2.0 opens without manual intervention and preserves all rows.
- Migration failure aborts the new finding feature with a clear log and stable API error; existing scans/projects remain usable.

### State management

Server state is authoritative. The dashboard stores only current filters, loaded records, selected finding ID, request-in-flight flags, and latest versions in memory. It must not optimistically claim a lifecycle transition before the server succeeds. After mutation, replace the detail record from the response and refresh the current list.

### Logging and errors

- Add structured JSON log events for finding upsert summary, lifecycle transition, verification start/completion, migration failure, and persistence failure.
- Include event name, timestamp, project/finding ID, outcome, counts, latency, and a request correlation ID where available.
- Never log query token, authorization header, cookies, full HTML context, or raw remote response bodies.
- API errors use a stable envelope with `code` and `detail`; validation may include a field name. Internal exceptions are logged but returned as generic details.
- Preserve current scan logging behavior.

### Dependency decision

No new runtime dependency is planned. Standard-library `sqlite3`, `html.parser`, `urllib`, and existing modules are sufficient. No type checker is currently configured, so this pass does not add one. Optional Playwright remains optional and is not required for static finding verification.

### Alternatives considered

- **Rewrite dashboard in React/Vue:** rejected because it adds a build system and deployment complexity without being required for the selected flow.
- **Replace SQLite with PostgreSQL:** rejected for this self-hosted pass; migration and operations would dominate scope.
- **Create findings from every non-2xx result:** rejected because it reproduces the high-confidence false-positive problem.
- **Automatically resolve on any successful scan:** rejected because source removal and transient recovery require explicit evidence and auditability.
- **Implement async jobs now:** rejected because persistence, worker recovery, and cancellation deserve a separate coherent pass.
- **Modify existing `LinkResult` contract:** rejected to protect current endpoints, exports, CLI, and tests.

## Data, API, and Compatibility Changes

### New API endpoints

All use existing optional token authentication and stable JSON errors.

- `GET /api/findings`
  - Parameters: `project_id` required; optional `state`, `classification`, `assignee`, `q`, `limit`, `offset`.
  - Response: `{items, total, limit, offset}`.
- `GET /api/findings/{finding_id}`
  - Response: complete finding, active/inactive occurrences, latest evidence, verification history, and audit history with bounded default limits.
- `POST /api/findings/{finding_id}/acknowledge`
  - Body: expected version.
- `POST /api/findings/{finding_id}/assignment`
  - Body: expected version and assignee string or null.
- `POST /api/findings/{finding_id}/ignore`
  - Body: expected version, reason, optional expiry date.
- `POST /api/findings/{finding_id}/reopen`
  - Body: expected version.
- `POST /api/findings/{finding_id}/verify`
  - Body: expected version.

Methods are intentionally action-specific to simplify the existing standard-library router and explicit tests. Generic PATCH is not required.

### Additive existing API behavior

- Project scan orchestration may include an optional `finding_summary` object in JSON responses when invoked with an identifiable saved project. Existing fields and status codes remain unchanged.
- `/scan` without project context does not create project findings.
- Browser “Run project scan” must send project identity through a validated server parameter or project-specific action route; the server must verify that every submitted source belongs to that project. The client cannot assert arbitrary project ownership.
- CSV, Markdown, and JSONL renderers remain unchanged in this pass.

### Compatibility contract

- Existing tests demonstrating exact output headers and core JSON result fields remain valid.
- Existing clients that ignore additive JSON fields continue working.
- Existing database files open without reset.
- Existing project import schema version remains 1; findings are runtime state and are never included in portable project configuration.
- Archive/restore, duplicate, and import semantics do not copy or delete findings. Duplicated/imported projects start with no findings.
- Existing history remains separate and readable.
- Query token support remains but documentation continues to discourage it for production.

## Security and Privacy Considerations

- Validate every source and target before each outbound request, including verification. Revalidate redirects with centralized policy wherever the request path exposes redirect hops.
- Do not permit stored findings to become an SSRF bypass. Database content is untrusted input at verification time.
- Persist sanitized error categories, not uncontrolled exception strings.
- Bound source HTML download and stored context size. If the current fetcher has no response-size cap in the selected path, add a bounded read for detailed scanning and verification; document the limit and test truncation.
- Escape all target/source/anchor/context/assignee/reason data before HTML insertion. Prefer DOM `textContent`; any template string must pass the existing escape helper.
- Validate all action payload types, lengths, states, dates, IDs, pagination, and expected versions server-side.
- Require existing authentication on every findings endpoint when configured.
- Use optimistic concurrency to prevent lost updates.
- Add in-process duplicate-verification protection, while documenting that cross-process exclusion is deferred with durable jobs.
- Do not store headers, cookies, URL credentials, response bodies, or secrets in evidence/audit tables.
- Findings remain project-scoped. This pass does not claim organization-level authorization because current delivered API does not integrate governance.
- Ignore does not delete evidence. Retention controls are deferred and must be called out in documentation.
- New external links use `noopener noreferrer`.
- No new CDN or third-party telemetry is introduced.

## Test Strategy

Development is test-first. For every behavior below, add failing RED tests, run them to prove failure, implement the minimum coherent behavior, then rerun targeted and full suites.

### Feature 1 RED and unit tests

- Detailed checker emits ordered attempts and exactly one assessment.
- Repeated 404/410 becomes confirmed.
- 429 then 200 becomes recovered/non-actionable.
- Transport-only failures become transient.
- 403 plus success becomes bot-blocked.
- Max attempts is enforced.
- Backoff and requester are injectable; unit tests make no real network request or sleep.
- Sanitization removes credentials and sentinel secrets.
- Existing `scan_page()` return type/shape is unchanged.

Suggested test modules: `tests/test_evidence_scanning.py` plus additions to `test_product_features.py`, `test_batch_scan.py`, and export endpoint regression tests.

### Feature 1 integration tests

- Use a local HTTP server fixture to produce 200, repeated 404, 429-then-200, redirect, timeout/connection-close, and 500-then-200 behavior.
- Verify real urllib request flow, latency presence, bounded attempts, and no whole-scan abort.
- Do not rely on public internet services.

### Feature 2 RED and unit tests

- Idempotent finding upsert by project/target.
- Project isolation.
- Occurrence deduplication and active/inactive reconciliation.
- Non-actionable evidence does not create findings.
- Resolved recurrence reopens.
- State transition table and invalid transition rejection.
- Assignment and ignore field validation.
- Ignore expiry behavior.
- Integer version increments and stale conflict.
- Audit event for every transition.
- Migration is idempotent and preserves an earlier project database fixture.
- Context bounding/escaping and secret sentinels.

Suggested modules: `tests/test_findings_store.py`, `tests/test_finding_service.py`, `tests/test_findings_migration.py`.

### Feature 2 API integration tests

- Auth gate on all endpoints.
- List pagination/filter/search/default ordering.
- Detail shape and bounded child collections.
- 400, 404, 409, and sanitized 500 paths.
- Archived-project mutation rejection.
- Project-run scan creates or updates findings only for project-owned sources.
- Duplicate/imported projects contain no copied findings.

Suggested module: `tests/test_findings_api.py` and focused additions to project lifecycle/quick-scan tests.

### Feature 2 UI tests

- Dashboard contains semantic Findings region, labeled filters, live count, empty/loading/error states, and detail dialog.
- Dynamic text uses escaping/text content.
- Filter requests and action payloads include expected version.
- Dialog focus is moved and restored.
- Mobile CSS/card contract exists; table remains semantically labeled.
- Reduced-motion rule and visible focus style exist.
- Existing JavaScript extraction plus `node --check` passes.

Suggested modules: `tests/test_findings_ui.py` and additions to `test_dashboard_javascript.py`.

### Feature 3 RED and unit tests

- Recovered outcome resolves.
- Proven removal from every successfully fetched source resolves.
- Confirmed broken plus retained occurrence stays open.
- Unreachable source prevents removal conclusion.
- Inconclusive leaves state/version unchanged except verification/audit evidence as explicitly designed.
- Recurrence after resolution reopens.
- Duplicate in-process verification returns conflict.
- SSRF rejection for stored source and target.
- Verification transaction is atomic under injected persistence failure.

Suggested module: `tests/test_finding_verification.py`.

### Feature 3 real-I/O integration tests

Use a local HTTP fixture whose source HTML and target status can change during a test:

1. First source contains target and target returns repeated 404.
2. Scan creates confirmed finding.
3. Change target to 200 and verify resolution.
4. Reset, remove link from source while target remains 404 and verify removal resolution.
5. Simulate unreachable source and verify inconclusive state retention.

This is mandatory meaningful real integration coverage.

### Accessibility verification

Automated contract checks must cover labels, roles, captions, live regions, dialog naming, focus hooks, error associations, non-color status text, reduced-motion rules, and external-link rel attributes. If an accessibility browser tool is available, run it and record results; adding a new runtime dependency is not required. Manual keyboard, zoom/reflow, contrast calculation, reduced motion, and one screen-reader smoke test are required and documented.

### Supported commands

During development, use the repository’s existing commands and environment conventions:

- Targeted tests: `python -m pytest -q tests/test_evidence_scanning.py tests/test_findings_store.py tests/test_finding_service.py tests/test_findings_api.py tests/test_findings_ui.py tests/test_finding_verification.py`
- Related regression tests: `python -m pytest -q tests/test_product_features.py tests/test_batch_scan.py tests/test_projects.py tests/test_project_quick_scan.py tests/test_dashboard_javascript.py tests/test_ssrf_enhanced.py`
- Full regression: `python -m pytest -q --disable-warnings`
- Lint: `ruff check src tests`
- Compile: `python -m compileall -q src tests`
- Package build, using the declared build backend: `python -m build` only if the `build` frontend is available; otherwise `python -m pip wheel . --no-deps -w dist-test` and remove the temporary output before packaging.
- Startup smoke: start `python -m brokenlinkbrief.app` with temporary project/history paths, request `/health` and `/dashboard`, then stop the process.
- JavaScript syntax: use the existing repository helper/test path, including `node --check` when Node is available.

No mypy/type-check command is required because the repository has no configured type checker. The development report must state “not configured” rather than claim a pass.

### Coverage and pass/fail criteria

- New/changed evidence, finding store, finding service, and verification logic must have at least 90% statement coverage when measured by an available coverage tool. If no coverage plugin is installed, use branch-oriented test enumeration and report the limitation; do not add coverage as a runtime dependency.
- Every planned acceptance criterion has at least one named automated test except manual assistive-technology checks.
- Zero failing targeted or full regression tests.
- Zero Ruff violations in `src` and `tests`.
- Compileall succeeds.
- Package wheel builds and imports in an isolated temporary environment when tooling permits.
- Startup smoke returns HTTP 200 from `/health` and `/dashboard`.
- No real public-network dependency in automated tests.

## Documentation Deliverables

The development pass must update or create the following. These changes are planned for development, not this planning phase.

### `README.md`

- Add “Trusted Findings” overview and primary project-to-repair journey.
- Document classification meanings and the rule that only confirmed failures create findings.
- Document all new findings endpoints with request/response examples and conflict behavior.
- Document verification outcomes and limitations.
- Add migration/upgrade notes, database location, backup warning, and privacy note for stored source context.
- Preserve all existing setup and endpoint documentation; consolidate contradictory version text encountered during editing.

### `CHANGELOG.md`

Add one release section with:

- Evidence-aware scan internals and compatibility statement.
- Stable project findings and lifecycle actions.
- Targeted verification outcomes.
- SQLite migration details.
- Security/privacy changes.
- Test counts and validation commands from the actual final run. Do not predict counts.

### API documentation

Update `docs/README.md` or create `docs/findings.md` as the canonical detailed reference, covering schemas, filters, pagination, state transitions, optimistic version conflicts, verification logic, stable error codes, authentication, and examples. README links to it.

### `FEATURES-DONE.md`

Create at project root. Include:

- Date/version.
- Requirement IDs PR-1 through PR-3.
- Exact delivered behavior and explicit exclusions.
- Implemented endpoints, tables/migrations, and UI surfaces.
- Test evidence mapping by test module/name.
- Known limitations and deferred items.
- No aspirational or unimplemented claims.

### `development-report.md`

Create at project root. Include:

- Original problem and selected scope.
- Architecture decisions and alternatives.
- Schema migration and compatibility validation.
- RED/GREEN chronology with commands and observed results.
- Real-I/O integration evidence.
- Full regression, Ruff, compile, packaging, startup, and JavaScript checks.
- UI verification at desktop/tablet/mobile, keyboard, zoom, reduced motion, contrast, and screen-reader smoke test.
- Coverage result or explicit tooling limitation.
- Changed-file inventory.
- Security/privacy review and artifact/secret scan.
- Remaining risks and deferred recommendations.

## Expected File Changes

Expected additions:

- `src/brokenlinkbrief/findings.py` for durable schema/store.
- `src/brokenlinkbrief/finding_service.py` for orchestration and verification.
- `tests/test_evidence_scanning.py`.
- `tests/test_findings_store.py`.
- `tests/test_finding_service.py`.
- `tests/test_findings_migration.py`.
- `tests/test_findings_api.py`.
- `tests/test_findings_ui.py`.
- `tests/test_finding_verification.py`.
- `docs/findings.md`.
- `FEATURES-DONE.md`.
- `development-report.md`.

Expected modifications:

- `src/brokenlinkbrief/confidence.py`: formalize constants/value validation while retaining current behavior.
- `src/brokenlinkbrief/package.py`: add detailed probing path without changing legacy return/output contracts.
- `src/brokenlinkbrief/triage.py`: bound/normalize extraction and provide compatibility with the new occurrence model.
- `src/brokenlinkbrief/app.py`: findings endpoints, project-context scan integration, dashboard panel/dialog/scripts/styles.
- `src/brokenlinkbrief/projects.py`: expose shared connection/schema migration hook only if necessary; preserve current public methods.
- `tests/test_product_features.py`, `tests/test_project_quick_scan.py`, `tests/test_dashboard_javascript.py`, `tests/test_ssrf_enhanced.py`: integration/regression additions.
- `README.md`, `CHANGELOG.md`, `docs/README.md`.
- `src/brokenlinkbrief/__init__.py` and `pyproject.toml` only if the development pass assigns a new release version; both must remain synchronized.

Files not expected to change include deployment configuration, schedule implementation, notifications, governance, CI gate, SPA scanner, and existing historical reports unless a concrete compatibility issue requires a narrowly documented edit.

## Traceability Matrix

| Research need | Research evidence | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|
| Reduce false positives from throttling, transient failures, and bot defenses | Multiple public issue threads; Lychee retry/rate-limit guidance; current classifier is disconnected | PR-1 evidence collection and classification | 429 then 200 creates no finding; transport-only is transient; repeated 404/410 is confirmed; attempts are bounded | `confidence.py`, `package.py` or `probing.py`, scan orchestration | `test_evidence_scanning.py`; local HTTP integration | P0 |
| Explain why a result is actionable | Research identifies trust as a primary value; current UI shows only status/reason | PR-1 detailed observations and PR-2 evidence history | Every finding exposes non-empty classification reason and ordered sanitized attempts | `confidence.py`, `findings.py`, findings detail API/UI | Evidence unit tests; API detail tests; UI contract tests | P0 |
| Show exactly where a link occurs | Screaming Frog Inlinks workflow; user reviews praise “what and where”; `extract_occurrences` exists | PR-2 source-aware occurrences | Two source pages appear under one finding; anchor/context retained, bounded, escaped | `triage.py`, `findings.py`, `finding_service.py`, detail dialog | Occurrence parser/store tests; HTML fixture integration; UI detail tests | P0 |
| Preserve repair work across scans | Research identifies export handoff and missing lifecycle as the main product gap | PR-2 stable project findings | Repeated scan returns same finding ID; project isolation; state and audit survive database reopen | `findings.py`, `finding_service.py`, `/api/findings` | Store persistence, API, migration tests | P0 |
| Avoid creating work from weak evidence | Research recommends only stable evidence drive alerts/work; current raw counting is noisy | PR-2 creation rule | No finding from transient, recovered, bot-blocked, inconclusive, or unverified evidence | `finding_service.py` | Parameterized service tests and project-scan integration | P0 |
| Assign or explicitly suppress known work | User workflow needs ownership and expected-exception handling | PR-2 lifecycle actions | Assignment validates length; ignore requires reason; stale versions conflict; all transitions audit | `findings.py`, API actions, detail dialog | Store transition tests, API 400/409 tests, UI validation tests | P0 |
| Verify repairs without rescanning everything | Vendor pricing change and user feedback show repeated verification demand | PR-3 targeted Verify Fix | Recovered or proven removed resolves; still broken remains open; inconclusive changes no state | `finding_service.py`, verify API, detail dialog | `test_finding_verification.py`; local mutable HTTP fixture | P0 |
| Prevent false “removed” results when sources are unreachable | Research emphasizes trustworthy findings and failure recovery | PR-3 source verification rule | Any unverified source prevents removal conclusion; source failure is sanitized and visible | Verification service and API/UI | Network-failure integration and friendly failure UI test | P0 |
| Protect existing users and interfaces | Project maturity and extensive tests make regressions costly | Compatibility contract | Existing endpoint/export/project tests pass unchanged; old DB opens without data loss | Legacy adapters and additive APIs | Full regression; migration fixture; exact output tests | P0 |
| Provide a polished but bounded business UI | Research calls for actionable findings, states, responsiveness, accessibility, and progressive disclosure | UI/UX specification | Complete happy/failure flows, keyboard focus, live status, mobile cards, reduced motion, contrast and zoom checks | `app.py` dashboard or extracted static assets | UI contract tests, JS syntax, manual/browser audit in report | P0 |

## Risks and Mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| Evidence retries increase scan duration | Project scans may become noticeably slower | Strict attempt cap, retry only selected outcomes, deduplicate targets, record latency, defer adaptive concurrency |
| Classification hides a real failure | User misses actionable work | Preserve raw evidence, use conservative `INCONCLUSIVE`, document policy, add regression fixtures for contradictory cases |
| Existing minimal findings tables conflict with new schema | Migration failure or data ambiguity | Use prefixed new tables, introspect schema, never reinterpret/drop legacy tables, test 1.2.0 database fixture |
| Large `app.py` becomes harder to edit | JavaScript or HTML regressions | Keep changes modular, preserve syntax extraction tests, optionally extract package assets without adding a build pipeline |
| SQLite write contention | Failed scan-to-finding updates | Short transactions, WAL, timeout, atomic writes, deterministic error handling; durable multi-worker jobs deferred |
| Source context stores sensitive text | Privacy/security exposure | Store only anchor and bounded escaped context, redact credentials, no response bodies/headers, document retention limitation |
| Verification makes outbound requests from stored data | SSRF bypass | Treat stored URLs as untrusted and revalidate every request and redirect |
| Synchronous verification blocks request thread | Timeout and poor UX | Strict source count/timeout bounds, busy state, isolated failures; async jobs are next-phase prerequisite |
| Existing notifications remain raw-status based | Temporary semantic inconsistency | Do not claim unified notification semantics; expose stable events and document notification migration as deferred unless safely included |
| No configured browser E2E/a11y tooling | UI regressions may escape automation | Strong contract tests, Node syntax, optional Playwright browser checks, mandatory documented manual keyboard/zoom/screen-reader audit |
| Optimistic conflicts confuse users | Lost edits or repeated actions | Return current version, automatically refresh, preserve safe local input, explain conflict in live region |
| Archived/duplicated project semantics become unclear | Findings copied or mutated unexpectedly | Archived findings read-only; duplicates/imports start clean; explicit integration tests and docs |

## Definition of Done

- [ ] PR-1, PR-2, and PR-3 are fully implemented with no facade, placeholder, simulated persistence, or unimplemented UI action.
- [ ] Existing scans and exports retain their documented response fields and formats.
- [ ] Evidence attempts are bounded, sanitized, deterministic under tests, and classified consistently.
- [ ] Only confirmed evidence creates or automatically reopens actionable findings.
- [ ] Findings are stable by project/target, persist occurrences and audit history, and enforce optimistic concurrency.
- [ ] Acknowledge, assign/clear, ignore with reason/expiry, reopen, and Verify Fix work end to end.
- [ ] Verify Fix distinguishes recovered, removed from source, still broken, and inconclusive without unsafe closure.
- [ ] Stored source and target URLs are revalidated before outbound verification.
- [ ] Database migration is idempotent and an earlier project database opens with all pre-existing rows byte/logically preserved.
- [ ] Saved-project archive, restore, duplicate, import/export, quick scan, and pinning behaviors still pass regression tests.
- [ ] Findings workspace includes complete loading, skeleton, empty, validation, disabled, error, success, conflict, and recovery states.
- [ ] Desktop, tablet, mobile, 200% zoom/reflow, reduced-motion, visible focus, keyboard, and screen-reader smoke checks are completed and recorded.
- [ ] Dynamic UI data is escaped, external links use safe attributes, and no secret sentinel appears in database, API, UI, or logs.
- [ ] RED tests were observed failing before implementation and their names/results are recorded.
- [ ] Unit, API integration, real local-HTTP integration, UI contract, boundary, security, migration, and regression tests pass.
- [ ] `python -m pytest -q --disable-warnings` passes with zero failures.
- [ ] `ruff check src tests` and `python -m compileall -q src tests` pass.
- [ ] JavaScript syntax validation passes when Node is available.
- [ ] Wheel/package build and import smoke pass using available repository-compatible tooling.
- [ ] Startup smoke confirms `/health` and `/dashboard` return HTTP 200 using temporary state paths.
- [ ] README, CHANGELOG, API docs, `FEATURES-DONE.md`, and `development-report.md` match actual delivered behavior and actual test results.
- [ ] Every selected research need is traceable to requirement, implementation location, acceptance criterion, and named test evidence.
- [ ] Deferred items remain absent and are not implied by documentation.
- [ ] No credentials, runtime databases, caches, virtual environments, coverage output, build output, editor state, or scratch files are included.
- [ ] The complete project, not a patch, is packaged; archive integrity, content listing, clean extraction, required-file presence, and no-extra-enclosing-directory checks pass.
