# BrokenLinkBrief 1.0.7
## Product, UX, User-Behavior, and Next-Version Requirements Analysis

**Prepared:** 2026-08-01  
**Analysis basis:** Static inspection of the supplied ZIP archive, including Python source, embedded dashboard HTML/CSS/JavaScript, CLI, HTTP endpoints, persistence modules, deployment files, product documentation, changelog, and tests.  
**Evidence convention:** **Confirmed observation** means directly visible in the supplied application or documentation. **Inference** means a reasoned conclusion about likely user behavior that has not been validated through interviews, telemetry, or usability sessions.

---

## Executive summary

BrokenLinkBrief 1.0.7 is no longer only a compact link-checking API. It now combines single-page and batch scanning, source-aware browser results, filters and exports, recent-page shortcuts, scan history, change details, notifications, analytics, CI gates, and several domain modules for schedules, governance, confidence, and repair triage.

The product's strongest recent improvement is that the browser dashboard now supports the immediate operational journey:

> Scan pages → review results → isolate failures → inspect history → export evidence

The main product gap is that this journey still ends before work is actually managed and completed. Broken links can be detected and investigated, but users cannot yet create durable projects, schedule scans through the UI, convert findings into a shared repair backlog, assign ownership, mark exceptions, verify fixes, or manage notifications and access in-product. Several mature-looking domain modules already model these capabilities, but they remain disconnected from the primary HTTP and dashboard delivery layer.

The next version should therefore prioritize an integrated **project and finding lifecycle**, not another collection of isolated utilities. The highest-value target journey is:

> Project → recurring scan → trusted finding → source context → assignment → repair → targeted verification → closure → recurrence monitoring

---

# 1. Product understanding

## What the application appears to do

BrokenLinkBrief scans one or more public web pages, extracts HTTP and HTTPS links, checks each link's response, records results, identifies failures, and presents or distributes those results through:

- JSON, CSV, Markdown, and JSONL formats.
- A browser dashboard.
- Batch APIs.
- Historical scan records and change calculations.
- Email, Slack, and registered webhooks.
- A CLI baseline and CI quality gate.

The application also contains independent modules for:

- Durable schedules and worker leasing.
- Source-aware link occurrences and repair tasks.
- Evidence-based confidence classification.
- Central outbound crawl policy.
- Organizations, memberships, roles, service credentials, and auditing.

**Confirmed observation:** The product documentation explicitly says these six modules are independent and intentionally separate from the legacy HTTP handler. Their capabilities are therefore present in the codebase but not generally usable through the main browser workflow.

## Likely users

### 1. Developers and CI owners

They are likely to use the CLI, JSON output, baselines, deterministic exit codes, and API automation. Their goals include preventing new broken links from reaching production and understanding why a quality gate failed.

### 2. SEO and content operations specialists

They are likely to use the browser dashboard, batch scanning, source filters, history, and CSV export. Their primary concern is finding where a bad link occurs and organizing the repair work efficiently.

### 3. Website administrators and web operations teams

They are likely to monitor the same sites repeatedly, rely on notifications, compare scans, and need predictable recurring schedules.

### 4. Agencies and multi-site teams

They are likely to need project separation, reusable settings, portfolio visibility, role-based access, and client-ready reporting.

### 5. Engineering or compliance managers

They are likely to care about current backlog, new regressions, recurrence, ownership, and time-to-fix rather than raw scan volume.

## Main workflows and usage scenarios

### Single-page browser scan

1. Open `/dashboard`.
2. Select **Single page**.
3. Enter a public URL.
4. Run the scan.
5. Review results with status filters, source filter, text search, and visible-row count.
6. Export the visible subset to CSV.

**Confirmed observation:** The workflow has progress, success, empty, and error states, keyboard focus transfer, an accessible live count, and SSRF validation.

### Browser batch scan

1. Select **Multiple pages**.
2. Paste up to 50 unique URLs, one per line.
3. Select concurrency from 1 through 20.
4. Run the batch.
5. Review combined results while retaining the originating source page.
6. Filter or export a focused subset.

**Confirmed observation:** Browser validation blocks empty, duplicate, and over-limit input. Server-side validation remains authoritative.

### Repeat scan

1. View the **Recent pages** panel.
2. Choose **Scan again**.
3. The URL is populated and submitted without retyping.

### History and change review

1. Choose **View history** for a recent page.
2. Review scans newest first.
3. Inspect total links, links needing attention, newly broken count, and fixed count.
4. Expand **Change details** to see exact URLs.
5. Export the loaded history as JSON.

### API and export workflow

Developers can call `/scan`, `/scan-batch`, `/history`, `/diff`, and dashboard endpoints. Results can be consumed as JSON, CSV, Markdown, or JSONL.

### Notification workflow

Email and Slack are configured using environment variables. Webhooks are registered through an API and triggered when qualifying changes occur.

### CI workflow

A baseline file is created from confirmed findings. A later CI run compares current confirmed findings with the baseline and exits with a stable pass or fail code.

### Domain workflows that are not integrated

The codebase models schedules, organizations, memberships, service keys, source occurrences, findings, assignments, and confidence assessments, but the main UI and HTTP application do not expose a connected workflow for them.

---

# 2. UI/UX analysis

## Strengths

- The dashboard supports both the initiation and review of scans.
- Single and batch workflows share a consistent result-review model.
- Source-page context survives batch flattening.
- Recent targets reduce repeated URL entry.
- History emphasizes newly broken and fixed links instead of only cumulative totals.
- Progressive disclosure keeps detailed change lists collapsed until needed.
- Result search, source filters, status categories, and focused export support high-volume review.
- Live regions, labels, native dialog/details elements, table headers, skip navigation, and text labels demonstrate meaningful accessibility intent.
- Browser CSV export includes spreadsheet-formula neutralization.
- The dashboard refreshes analytics and recent targets after successful scans.

## Weaknesses

### 2.1 The product lacks durable user context

The browser is still organized around scans and recent URLs, not projects or sites. Users cannot save a named workspace containing targets, crawl rules, schedules, authentication settings, exclusions, notification policies, and ownership.

### 2.2 Detection is not connected to resolution

Results and history are visible, but users cannot:

- Acknowledge a finding.
- Assign an owner.
- Set priority or due date.
- Add a comment.
- Ignore an expected failure with a reason and expiry.
- Mark work in progress.
- Verify a repair.
- Close or reopen a finding.

This is the largest gap in the daily workflow.

### 2.3 Confidence semantics are disconnected

The browser still treats `status >= 400` or no response as needing attention. The independent confidence module distinguishes `TRANSIENT`, `BOT_BLOCKED`, `RECOVERED`, `INCONCLUSIVE`, and `CONFIRMED_BROKEN`, but these distinctions do not drive primary scan results, notifications, or browser triage.

This means users may still spend time investigating temporary outages, bot protection, HEAD behavior, or inconsistent responses.

### 2.4 No global information architecture

The dashboard is a long page containing scanning, recent pages, filters, summary cards, and charts. There is no persistent navigation for:

- Overview
- Projects
- Scans
- Findings
- Schedules
- Integrations
- Team
- Settings

As capabilities grow, the single-page layout will become harder to scan and maintain.

### 2.5 Authentication is not browser-friendly

Dashboard requests can use a token in the query string. Documentation acknowledges that query tokens may appear in logs or browser history. There is no login screen, secure browser session, token expiration, sign-out, recovery, or clear authentication failure flow.

### 2.6 Dashboard errors are still broad

The analytics loader fetches four endpoints together. An error can replace the chart region with a generic failure message. Users get limited help distinguishing expired authentication, unavailable history, malformed data, or one failed widget.

### 2.7 Charts remain passive

Summary cards and charts do not serve as strong workflow entry points. A user seeing a spike in broken links cannot click through to the corresponding source pages or findings.

### 2.8 Batch execution remains synchronous

The browser waits for `/scan-batch` to complete within one HTTP request. There is no durable job ID, resumable progress, cancellation, per-source completion status, or recovery after a browser refresh or server restart.

### 2.9 Configuration remains outside the product

SMTP, Slack, token authentication, logging, and other operational settings are configured through environment variables. Webhook registration is API-based. These are appropriate deployment controls, but they do not support delegated day-to-day administration.

### 2.10 Documentation and version drift exists

Some product documentation still describes the independent capability package as version 1.0.0 while the package metadata and changelog identify version 1.0.7. The general README contains both old dashboard descriptions and newer appended workflow sections, which increases cognitive load and risks contradictory guidance.

## Confusing elements

- “Broken,” “needs attention,” “critical,” “warning,” “confirmed broken,” and workflow priority are not clearly separated concepts.
- 5xx is labeled critical and 4xx warning, but operational impact may be the opposite for a sitewide 404 in primary navigation.
- The first retained scan treats all broken links as newly broken because the baseline is empty. This is logically consistent but may surprise users.
- A recent target is not the same as a saved project, although users may expect it to behave like one.
- The dashboard says “real-time” in documentation, but updates occur on page load, filter changes, and completed scans rather than through live server events.

## Friction points

- Repeatedly selecting the same filters after returning to the page.
- No saved views or remembered user preferences.
- No way to open a target link or source page safely from a result row.
- No bulk selection and bulk action workflow.
- No source anchor text or HTML context in delivered scan results.
- No targeted “verify this link” action.
- No scan cancellation or per-page retry in batch mode.
- One invalid batch URL still causes the server to reject the full request.
- No visible notification delivery history.
- No in-product schedule management despite scheduler code existing.
- No clear data-retention management for append-only history.

## Navigation and workflow observations

The current browser journey is effective for a solo user performing ad hoc inspection. It is not yet an operational workspace for teams managing a recurring backlog.

A scalable information architecture should evolve toward:

- **Overview:** current changes, unresolved confirmed findings, failed jobs, next scheduled scan.
- **Projects:** saved targets, scope, crawl rules, and settings.
- **Scans:** queued, running, completed, failed, and cancelled jobs.
- **Findings:** filterable, assignable, lifecycle-managed problems.
- **Schedules:** recurring scan configuration.
- **Integrations:** email, Slack, webhooks, issue trackers, delivery log.
- **Team:** roles, memberships, service credentials.
- **Settings:** retention, security, and organization policy.

---

# 3. User behavior analysis

## Likely user habits

> **Inference:** These behaviors are derived from the current feature set and common link-quality workflows. They are not confirmed by usage analytics or interviews.

- Users repeatedly scan the same small set of sites or critical pages.
- Users focus first on newly broken links, not unchanged historical failures.
- Users filter by source page, status, or domain, then export a subset for someone else to repair.
- Users re-run scans after a content or code change to check whether the problem disappeared.
- Users learn to ignore recurring false positives caused by bot protection, authentication, rate limits, or temporary outages.
- Developers automate scans and only open the dashboard after an alert or CI failure.
- Content teams need anchor text and page context more than raw network details.
- Managers want unresolved backlog and time-to-fix rather than all-time scan totals.

## Repeated actions

- Opening the same recent targets.
- Selecting **Needs attention**.
- Filtering to one source page.
- Searching for a status or domain.
- Exporting a subset to CSV.
- Sharing the exported file through another tool.
- Reopening history to compare the latest scan with the previous one.
- Rescanning after a repair.
- Manually reconciling alerts, CI failures, and dashboard records.

## Likely pain points

- Not knowing whether a failure is trustworthy or transient.
- Not seeing the anchor text and exact source context that must be edited.
- Losing ownership once results are exported from the product.
- Repeating scans manually because schedules are not exposed.
- Inability to distinguish acknowledged technical debt from new regressions.
- Inability to document why a result is intentionally ignored.
- No shared state for a team repairing the same website.
- No recovery when a long batch request is interrupted.
- Unclear relationship between analytics severity and business priority.

## Usage bottlenecks

1. **Onboarding bottleneck:** no guided project/site setup.
2. **Trust bottleneck:** confidence classification is not integrated.
3. **Localization bottleneck:** delivered results identify the source page but not anchor text or content context.
4. **Triage bottleneck:** no finding lifecycle, assignment, comments, or bulk actions.
5. **Verification bottleneck:** no targeted recheck and automated closure.
6. **Monitoring bottleneck:** schedules exist only as code-level services.
7. **Administration bottleneck:** notifications and access require environment variables or API calls.
8. **Execution bottleneck:** synchronous scans do not support durable progress, cancellation, or continuation.

## Expected but missing interactions

- Save current sources as a named project.
- Save and share commonly used filters.
- Click a chart or card to open filtered findings.
- Open source page and target link in safe new tabs.
- See anchor text and surrounding context.
- Assign one or many findings.
- Acknowledge, ignore, resolve, reopen, and comment.
- Add an ignore reason with optional expiration.
- Verify one finding without rescanning an entire site.
- Schedule scans and preview the next run in local time.
- Configure and test alerts.
- View alert delivery history.
- Resume or inspect a failed batch job.
- See confidence evidence and retry history.

---

# 4. What should be improved

## Critical improvements

1. **Create a durable project model and project navigation.**
   Recent URLs should evolve into saved workspaces with targets, policies, schedules, integrations, and ownership.

2. **Integrate source occurrences and confidence evidence into the main scan pipeline.**
   Each finding should retain source URL, target URL, anchor text, safe HTML context, attempts, classification, and reason.

3. **Create a finding lifecycle.**
   Users need assignment, status, comments, ignore rules, priority, bulk actions, verification, and audit history.

4. **Move scan execution to durable jobs.**
   Single and batch scans should survive refreshes and restarts, provide progress, and support cancellation and retries.

5. **Replace query-token browser authentication with secure sessions.**
   Integrate the existing governance/RBAC concepts into the delivered app.

6. **Expose schedules in the product.**
   The scheduler exists but does not help users until it is connected to projects, workers, and browser controls.

7. **Unify concepts and metrics.**
   Clearly distinguish HTTP status, confidence classification, severity, business priority, and workflow state.

8. **Make persistence coherent and durable.**
   Consolidate append-only history, independent SQLite stores, and in-memory webhook registrations into an organization-scoped data model.

## Medium-priority improvements

- Saved views and per-user preferences.
- Click-through dashboard metrics and charts.
- Notification configuration, test delivery, and delivery logs.
- Batch partial acceptance instead of full rejection for one invalid URL.
- Sitemap and uploaded URL-list ingestion.
- Crawl exclusions, allowed domains, authentication headers, and scope controls.
- Data retention controls and storage-health visibility.
- Separate liveness, readiness, and diagnostics endpoints.
- API versioning, pagination, correlation IDs, and stable error envelopes.
- Browser end-to-end tests and manual assistive-technology validation.
- Documentation consolidation and automatic version verification.

## Nice-to-have improvements

- Custom portfolio dashboards.
- Client-branded reports.
- Issue tracker integrations after finding lifecycle is established.
- Internationalization.
- Theme preference.
- Suggested replacement links based on redirects or site search, always requiring human review.
- Web-rendered crawling for JavaScript-heavy sites as an opt-in capability.

---

# 5. Requirements

## Business requirements

### BR-01: End-to-end link repair workflow

- **Type:** Business
- **Description:** BrokenLinkBrief shall support the complete lifecycle from project setup and recurring scanning through trusted detection, assignment, verification, and closure.
- **User value:** Teams can finish work without exporting every result into another system.
- **Priority:** Must have
- **Rationale:** The delivered product identifies and investigates problems but stops before ownership and repair completion.
- **Acceptance criteria:**
  - A user can create a project, run or schedule a scan, open a finding, assign it, verify a fix, and close it through the browser.
  - UI, API, alerts, and CI reference the same stable finding identity.
  - Every state transition is recorded with actor and timestamp.

### BR-02: Recurring monitoring as the default operating model

- **Type:** Business
- **Description:** Saved targets, schedules, change-first views, and alert rules shall be first-class project capabilities.
- **User value:** Users stop recreating routine monitoring work.
- **Priority:** Must have
- **Rationale:** Recent pages, history, notifications, and scheduler code all indicate repeated monitoring is central.
- **Acceptance criteria:**
  - Project targets and schedules persist across restarts.
  - The primary post-scan view identifies new regressions and verified fixes.
  - Users can pause and resume monitoring without deleting configuration.

### BR-03: Trustworthy findings

- **Type:** Business
- **Description:** The product shall distinguish confirmed failures from transient, bot-blocked, recovered, and inconclusive outcomes.
- **User value:** Fewer false-positive investigations and more credible alerts.
- **Priority:** Must have
- **Rationale:** Evidence-classification code exists but is not integrated with delivered results.
- **Acceptance criteria:**
  - Dashboard, export, notification, and CI classification use the same documented rules.
  - A transport failure is not labeled confirmed broken without satisfying evidence policy.
  - Users can inspect the evidence supporting a classification.

### BR-04: Multi-user accountability

- **Type:** Business
- **Description:** Organization-scoped roles, ownership, and audit history shall be delivered through the application.
- **User value:** Teams can collaborate safely and demonstrate who changed what.
- **Priority:** Must have
- **Rationale:** Governance and repair-task primitives exist but are disconnected.
- **Acceptance criteria:**
  - Cross-organization access is denied.
  - Viewer, operator, and administrator capabilities are enforced in UI and API.
  - Assignment and finding-state changes are auditable.

## User requirements

### UR-01: Save a project

- **Type:** User
- **Description:** As a site owner, I want to save a named project with source URLs and settings so that I do not rebuild the same scan repeatedly.
- **User value:** Faster setup and clearer organization.
- **Priority:** Must have
- **Rationale:** Recent targets reduce typing but do not retain project intent or settings.
- **Acceptance criteria:**
  - Users can create, rename, archive, and restore a project.
  - Duplicate normalized targets are detected.
  - Project targets, policies, schedule, integrations, and members are visible in one place.

### UR-02: Review a durable finding backlog

- **Type:** User
- **Description:** As an operator, I want a filterable list of unresolved findings rather than only results from the latest scan.
- **User value:** Work persists between sessions and scans.
- **Priority:** Must have
- **Rationale:** Latest-result filtering is useful but does not create a durable backlog.
- **Acceptance criteria:**
  - Users can filter by project, source, target domain, classification, state, priority, owner, and dates.
  - Repeated observations update the existing finding rather than creating uncontrolled duplicates.
  - Direct links to filtered views can be shared.

### UR-03: Understand source occurrence and evidence

- **Type:** User
- **Description:** As a repair owner, I want to see where the link occurs and why it was classified so that I can act without reproducing the scan manually.
- **User value:** Faster diagnosis and repair.
- **Priority:** Must have
- **Rationale:** Source URL is delivered, but anchor text, safe context, attempts, and confidence are not.
- **Acceptance criteria:**
  - Finding details show source URL, target URL, anchor text, safe context, attempts, redirects, timestamps, and classification reason.
  - One target occurring on multiple source pages retains every occurrence.
  - Sensitive headers and credentials are not displayed.

### UR-04: Assign and manage repair work

- **Type:** User
- **Description:** As a team lead, I want to assign findings, set priority, and track status.
- **User value:** Clear accountability and less spreadsheet coordination.
- **Priority:** Must have
- **Rationale:** The existing repair-task model only supports a single assignment event.
- **Acceptance criteria:**
  - Supported states include Open, Acknowledged, In progress, Resolved, Ignored, and Reopened.
  - Users can add comments, labels, priority, and optional due date.
  - Bulk assignment and bulk state changes report partial failures.

### UR-05: Verify a fix

- **Type:** User
- **Description:** As a repair owner, I want to recheck one finding or its affected source pages and close it only when evidence supports recovery.
- **User value:** Reliable completion with fewer full-site rescans.
- **Priority:** Must have
- **Rationale:** Current Scan again operates at the source-page level and does not complete a repair task.
- **Acceptance criteria:**
  - A Verify fix action creates a targeted job.
  - Successful evidence proposes closure and records the verification.
  - Failed verification leaves the finding open and displays new evidence.

### UR-06: Schedule scans in local time

- **Type:** User
- **Description:** As an administrator, I want to configure recurring scans with a timezone and next-run preview.
- **User value:** Predictable monitoring without external cron setup.
- **Priority:** Must have
- **Rationale:** Scheduling code exists but has no delivery workflow.
- **Acceptance criteria:**
  - Users can create, edit, pause, resume, and delete schedules.
  - The UI shows timezone, next run, last run, last outcome, and worker state.
  - Invalid cadence and timezone values are rejected inline.

### UR-07: Manage expected exceptions

- **Type:** User
- **Description:** As an operator, I want to ignore an expected finding with a reason and optional expiry.
- **User value:** Reduces recurring noise without permanently hiding risk.
- **Priority:** Should have
- **Rationale:** Real sites frequently contain authenticated, blocked, or intentionally unavailable destinations.
- **Acceptance criteria:**
  - Ignore requires a reason.
  - Ignore may expire automatically.
  - New evidence after expiry returns the finding to active review.
  - Ignored items remain visible through an explicit filter and audit history.

### UR-08: Configure and test alerts

- **Type:** User
- **Description:** As an administrator, I want to configure notification channels from the product and test them.
- **User value:** Faster setup and confidence that alerts work.
- **Priority:** Should have
- **Rationale:** Current email/Slack settings are environment-based and webhook administration is API-centric.
- **Acceptance criteria:**
  - Users can configure project or organization notification rules.
  - Secrets are masked after save.
  - Test delivery reports success or actionable failure.
  - Delivery attempts are visible in a log.

## Functional requirements

### FR-01: Unified domain and persistence model

- **Type:** Functional
- **Description:** The system shall persist organizations, users, projects, targets, jobs, scans, occurrences, findings, evidence, tasks, schedules, integrations, deliveries, and audit events in a coherent model.
- **User value:** Consistent behavior across every workflow.
- **Priority:** Must have
- **Rationale:** Current state is divided among JSONL, multiple independent SQLite stores, and memory.
- **Acceptance criteria:**
  - Stable IDs connect records across UI, API, notifications, and CI.
  - Referential integrity and organization scope are enforced.
  - Existing JSONL history can be imported with repeatable migration tooling.

### FR-02: Durable asynchronous scan jobs

- **Type:** Functional
- **Description:** Single and batch scans shall execute as durable jobs.
- **User value:** Progress, cancellation, retry, and survival across refreshes or restarts.
- **Priority:** Must have
- **Rationale:** Current synchronous requests cannot support resilient long-running work.
- **Acceptance criteria:**
  - Job creation returns an ID promptly.
  - States include Queued, Running, Partially completed, Completed, Failed, and Cancelled.
  - Job state survives restart.
  - Users can retry failed sources and cancel eligible jobs.
  - Idempotency keys prevent duplicate submission.

### FR-03: Integrated occurrence extraction

- **Type:** Functional
- **Description:** The main scan pipeline shall retain every source occurrence with anchor text and safe context.
- **User value:** Users know what content to edit.
- **Priority:** Must have
- **Rationale:** `triage.py` already models occurrences but the main scanner uses a simple href regex and target-level result model.
- **Acceptance criteria:**
  - Single-quoted, double-quoted, and valid parsed anchors are supported.
  - Relative links are resolved against the source page.
  - Multiple occurrences of one target are retained.
  - Display context is escaped and size-limited.

### FR-04: Integrated evidence classification

- **Type:** Functional
- **Description:** The main scanner shall persist probe attempts and apply the evidence classifier before creating or updating findings.
- **User value:** Better signal quality.
- **Priority:** Must have
- **Rationale:** Current “needs attention” is a raw transport/status rule.
- **Acceptance criteria:**
  - Attempts include method, status or error, latency, timestamp, and redirect data.
  - Classification is deterministic for the same evidence.
  - Reclassification history is retained.
  - Alert rules can target confirmed and newly confirmed findings.

### FR-05: Finding lifecycle and bulk operations

- **Type:** Functional
- **Description:** Findings shall support state transitions, assignment, comments, labels, priority, due dates, ignore rules, and bulk operations.
- **User value:** Efficient team triage.
- **Priority:** Must have
- **Rationale:** Current browser tools review rows but cannot manage work.
- **Acceptance criteria:**
  - Invalid transitions return a stable error code.
  - Bulk actions preview the affected count.
  - Partial failures identify failed items and preserve successful changes.
  - Concurrent edits use version checking and return conflict details.

### FR-06: Project scheduling integration

- **Type:** Functional
- **Description:** Project schedules shall create durable scan jobs through the same job service as manual scans.
- **User value:** One consistent execution and history model.
- **Priority:** Must have
- **Rationale:** Scheduler leasing presently operates independently.
- **Acceptance criteria:**
  - Due work is atomically claimed.
  - Expired leases can be safely recovered.
  - A schedule run links to its created scan job.
  - Duplicate schedule execution is prevented.

### FR-07: Partial batch acceptance

- **Type:** Functional
- **Description:** Structurally valid batch requests shall validate source URLs independently and continue with accepted entries.
- **User value:** One invalid URL does not waste the rest of a large batch.
- **Priority:** Should have
- **Rationale:** The current endpoint rejects the entire batch when one input fails SSRF or URL validation.
- **Acceptance criteria:**
  - Response separates accepted and rejected sources.
  - Rejected entries include stable codes and explanations.
  - Users can correct and retry only rejected entries.

### FR-08: Dashboard drill-down

- **Type:** Functional
- **Description:** Summary cards and charts shall open the corresponding filtered finding or scan view.
- **User value:** Analytics becomes actionable.
- **Priority:** Should have
- **Rationale:** Current visualizations are passive.
- **Acceptance criteria:**
  - Selected date range and chart dimension are carried into the destination URL.
  - Browser back restores dashboard state.
  - Every metric documents its timeframe and calculation.

### FR-09: Durable integration registry and delivery log

- **Type:** Functional
- **Description:** Notification configuration and delivery outcomes shall persist across restarts.
- **User value:** Reliable alerts and troubleshooting.
- **Priority:** Should have
- **Rationale:** Webhooks are stored in memory and email/Slack delivery state is not user-visible.
- **Acceptance criteria:**
  - Registrations survive restart.
  - Delivery records include event ID, channel, attempt, timestamp, status, and sanitized error.
  - Safe retries preserve event identity.

### FR-10: Saved views and preferences

- **Type:** Functional
- **Description:** Users shall be able to save common finding filters and preference defaults.
- **User value:** Less repetitive setup.
- **Priority:** Should have
- **Rationale:** Current filters reset with page state.
- **Acceptance criteria:**
  - Users can save, rename, share, and delete views.
  - Last project, view, page size, and sort order are restored per user.
  - Shared views respect recipient permissions.

## Non-functional requirements

### NFR-01: Browser security

- **Type:** Non-functional, Security
- **Description:** Browser authentication shall use secure session handling rather than long-lived query tokens.
- **User value:** Lower credential exposure risk.
- **Priority:** Must have
- **Rationale:** Query tokens may leak through logs and browser history.
- **Acceptance criteria:**
  - Sessions use Secure, HttpOnly, and appropriate SameSite cookies or equivalent short-lived credentials.
  - State-changing browser requests include CSRF protection.
  - Logout and expiration are supported.
  - Secrets never appear in rendered HTML, URLs, logs, or audit payloads.

### NFR-02: Outbound security consistency

- **Type:** Non-functional, Security
- **Description:** All outbound requests and redirect hops shall use one centralized crawl policy.
- **User value:** Consistent protection across manual scans, schedules, retries, webhooks, and integrations.
- **Priority:** Must have
- **Rationale:** `validate_scan_url`, `policy.py`, and webhook validation represent overlapping controls.
- **Acceptance criteria:**
  - Target, redirects, DNS results, ports, and response-size limits are enforced.
  - DNS-to-connection rebinding risk is addressed by connecting to validated addresses or equivalent protection.
  - Security tests cover IPv4, IPv6, redirects, alternate numeric forms, and private destinations.

### NFR-03: Reliability and recovery

- **Type:** Non-functional, Reliability
- **Description:** Committed projects, jobs, findings, schedules, and integrations shall survive restart without duplicate execution.
- **User value:** Dependable monitoring.
- **Priority:** Must have
- **Rationale:** Current state includes in-memory webhook registration and synchronous jobs.
- **Acceptance criteria:**
  - Restart tests demonstrate no lost committed state.
  - Workers use leases and idempotent completion.
  - Interrupted jobs become recoverable or explicitly failed.
  - Duplicate notifications are bounded through event idempotency.

### NFR-04: Performance objectives

- **Type:** Non-functional, Performance
- **Description:** The product shall define and monitor user-facing performance targets.
- **User value:** Responsive daily workflows.
- **Priority:** Should have
- **Rationale:** Current logging captures scan latency but does not establish service objectives.
- **Acceptance criteria:**
  - Project and finding list p95 response is under 1 second for the supported reference dataset.
  - Job creation p95 is under 500 ms, excluding execution.
  - Filtering 10,000 server-paginated findings remains interactive.
  - Performance-test data, environment, and limits are documented.

### NFR-05: Accessibility

- **Type:** Non-functional, Accessibility
- **Description:** Delivered browser workflows shall meet WCAG 2.2 AA.
- **User value:** Usable with keyboard, screen readers, magnification, and non-color cues.
- **Priority:** Must have
- **Rationale:** Existing semantics are promising but there is no demonstrated full conformance process.
- **Acceptance criteria:**
  - All workflows are keyboard operable with visible focus.
  - Charts have equivalent textual or tabular summaries.
  - Status is not communicated by color alone.
  - Automated and manual checks are release gates.
  - Critical flows are tested with at least one screen reader.

### NFR-06: Observability and health

- **Type:** Non-functional, Operations
- **Description:** Liveness, readiness, diagnostics, logs, and metrics shall be separated.
- **User value:** Faster incident diagnosis and fewer unnecessary restarts.
- **Priority:** Should have
- **Rationale:** The public health endpoint still performs external HTTP and DNS checks even though only local history affects overall health.
- **Acceptance criteria:**
  - Liveness performs no external calls.
  - Readiness checks required local dependencies with bounded latency.
  - External connectivity appears in a diagnostic endpoint.
  - Jobs, notifications, and API requests share correlation IDs.

### NFR-07: Data retention and privacy

- **Type:** Non-functional, Data
- **Description:** Administrators shall control retention of scan evidence, history, logs, deliveries, and audit data.
- **User value:** Predictable storage and governance.
- **Priority:** Should have
- **Rationale:** JSONL history is append-only and no user-facing retention policy exists.
- **Acceptance criteria:**
  - Retention can be configured by organization within platform bounds.
  - Deletion is auditable and retryable.
  - Export and deletion remain organization-scoped.
  - Storage usage and upcoming cleanup are visible.

### NFR-08: Maintainability and frontend integrity

- **Type:** Non-functional, Maintainability
- **Description:** The embedded dashboard shall be separated into testable frontend assets or components as scope grows.
- **User value:** Fewer regressions and faster improvements.
- **Priority:** Should have
- **Rationale:** A large HTML/CSS/JavaScript string inside `app.py` increases editing risk; a JavaScript syntax defect was already found and corrected during prior increments.
- **Acceptance criteria:**
  - HTML, CSS, and JavaScript are packaged as separate versioned assets or equivalent components.
  - Frontend behavior has automated DOM-level tests.
  - Content Security Policy can be applied without inline script exceptions.
  - Build and packaging remain reproducible.

## UX/UI requirements

### UX-01: Global navigation and project context

- **Type:** UX/UI
- **Description:** Provide persistent navigation and visible organization/project context.
- **User value:** Users can discover capabilities and remain oriented.
- **Priority:** Must have
- **Rationale:** A growing single dashboard page will not scale.
- **Acceptance criteria:**
  - Navigation includes Overview, Scans, Findings, Schedules, Integrations, Team, and Settings.
  - Active organization, project, section, and relevant filter state are visible.
  - Desktop and mobile layouts retain all critical actions.

### UX-02: Actionable overview

- **Type:** UX/UI
- **Description:** The overview shall focus on current unresolved work and change, not cumulative activity alone.
- **User value:** Users know what needs attention immediately.
- **Priority:** Must have
- **Rationale:** Total scans and total broken links grow indefinitely and do not represent current backlog.
- **Acceptance criteria:**
  - Show open confirmed findings, newly confirmed, recently fixed, failed jobs, and next scheduled run.
  - Every metric has a defined timeframe and drill-down.
  - Empty states provide an appropriate next action.

### UX-03: Findings workspace

- **Type:** UX/UI
- **Description:** Provide a responsive, server-paginated finding table and detail panel that preserves list context.
- **User value:** Efficient high-volume triage.
- **Priority:** Must have
- **Rationale:** Latest-scan tables are not a durable work queue.
- **Acceptance criteria:**
  - Opening and closing details preserves filters, page, sort, selection, and scroll position.
  - Rows support selection and eligible bulk actions.
  - Users can choose visible columns.
  - Mobile view preserves priority, classification, source, target, state, and owner.

### UX-04: Distinct status concepts

- **Type:** UX/UI
- **Description:** HTTP status, confidence, severity, priority, and workflow state shall use distinct labels and explanations.
- **User value:** More accurate decisions.
- **Priority:** Must have
- **Rationale:** Current terminology can conflate transport outcome and business urgency.
- **Acceptance criteria:**
  - The same terminology is used in UI, exports, notifications, and documentation.
  - Contextual help explains each concept.
  - HTTP status remains visible but does not substitute for confidence or priority.

### UX-05: Recoverable system feedback

- **Type:** UX/UI
- **Description:** Long operations and failures shall provide contextual, recoverable feedback.
- **User value:** Less uncertainty and repeated work.
- **Priority:** Must have
- **Rationale:** Durable jobs and distributed integrations introduce more partial states.
- **Acceptance criteria:**
  - Each panel has independent loading, empty, stale, partial, and error states.
  - Retry is offered only when safe.
  - Destructive actions require confirmation and provide undo where feasible.
  - Authentication errors lead to reauthentication without discarding unsaved input.

### UX-06: Safe direct actions

- **Type:** UX/UI
- **Description:** Results and findings shall offer safe links to source and target pages plus targeted verification.
- **User value:** Faster investigation.
- **Priority:** Should have
- **Rationale:** Current rows display URLs as text.
- **Acceptance criteria:**
  - External links open in a new tab with safe `rel` attributes.
  - Copy actions are available for source, target, and finding URL.
  - Verify fix is available from row and detail views.

## Data and integration requirements

### DI-01: Versioned event contracts

- **Type:** Data/Integration
- **Description:** Webhook and notification events shall use versioned schemas and stable event IDs.
- **User value:** Reliable external automation.
- **Priority:** Should have
- **Rationale:** Retries and evolving finding semantics require idempotent contracts.
- **Acceptance criteria:**
  - Events include schema version, event ID, type, organization/project, timestamp, and resource link.
  - Retries preserve the same event ID.
  - HMAC documentation includes verification examples and test vectors.

### DI-02: CI and hosted finding alignment

- **Type:** Data/Integration
- **Description:** CI evaluation shall consume the same confirmed-finding model as the hosted product while retaining offline file support.
- **User value:** CI and dashboard findings agree.
- **Priority:** Should have
- **Rationale:** Current CI operates against independent findings JSON.
- **Acceptance criteria:**
  - A project baseline can be created and downloaded.
  - CI output links to hosted findings when configured.
  - Offline behavior remains deterministic.

### DI-03: Sitemap and URL-list ingestion

- **Type:** Data/Integration
- **Description:** Projects shall accept manual URLs, sitemap URLs, and uploaded URL lists with a validation preview.
- **User value:** Faster onboarding of real websites.
- **Priority:** Should have
- **Rationale:** Manual batch entry is limited to 50 URLs and does not scale to site setup.
- **Acceptance criteria:**
  - Preview separates accepted, normalized, duplicate, and rejected targets.
  - Sitemap indexes can be followed within configured bounds.
  - Users see expected scope and limits before starting.

### DI-04: Issue tracker handoff

- **Type:** Data/Integration
- **Description:** After the internal finding lifecycle is stable, findings may be linked or synchronized with issue trackers.
- **User value:** Fits established engineering workflows.
- **Priority:** Could have
- **Rationale:** Current CSV and JSON exports indicate a real handoff need, but integration should not substitute for the internal source of truth.
- **Acceptance criteria:**
  - Creation is explicit and previewed.
  - External issue ID and synchronization status are retained.
  - Duplicate issue creation is prevented.

## MoSCoW summary

### Must have

- BR-01 through BR-04.
- UR-01 through UR-06.
- FR-01 through FR-06.
- NFR-01 through NFR-03 and NFR-05.
- UX-01 through UX-05.

### Should have

- UR-07 and UR-08.
- FR-07 through FR-10.
- NFR-04 and NFR-06 through NFR-08.
- UX-06.
- DI-01 through DI-03.

### Could have

- DI-04 issue tracker integration.
- Portfolio dashboards and client-branded reports.
- Internationalization and theme preferences.
- Human-reviewed replacement-link suggestions.
- Opt-in browser-rendered crawling.

### Won't have for now

- Autonomous modification of customer websites.
- Automatic link replacement without human approval.
- Unlimited crawling or unrestricted private-network access.
- Full digital-experience monitoring beyond link quality.
- AI-generated repair decisions treated as authoritative evidence.

---

# 6. New opportunities

## 6.1 Change-first operations workspace

**Opportunity:** Make newly confirmed, reopened, and recently fixed findings the primary overview.

**Why users may want it:** Repeated scans produce large volumes of unchanged data. Users care most about regressions and proof that repairs worked.

**Evidence:** The product already invests in recent targets, history, newly broken/fixed calculations, and change-triggered notifications.

## 6.2 Evidence-aware false-positive reduction

**Opportunity:** Integrate retries, confidence classifications, domain exceptions, and temporary suppression into finding triage.

**Why users may want it:** Bot protection, temporary outages, and request-method differences create costly noise.

**Evidence:** The independent confidence module already models these exact states, showing the need was recognized in the architecture.

## 6.3 Team repair hub

**Opportunity:** Turn findings into a lightweight shared repair queue with ownership, activity, verification, and audit history.

**Why users may want it:** Detection has limited business value unless someone completes and verifies the repair.

**Evidence:** The code already includes findings, tasks, organizations, roles, and audit-oriented storage primitives.

## 6.4 Scheduled project monitoring

**Opportunity:** Connect saved projects, timezone-aware schedules, durable jobs, and change-based alerts.

**Why users may want it:** The most likely repeated behavior is monitoring the same sites, not continuously entering new ad hoc pages.

**Evidence:** Recent pages, history, notification systems, and a durable scheduler all support this direction.

## 6.5 Agency and portfolio workspace

**Opportunity:** Organization-scoped projects, reusable policies, portfolio summaries, and client-ready exports.

**Why users may want it:** Agencies and central web teams manage many properties and need both separation and aggregate oversight.

**Evidence:** Governance already models organizations and RBAC, while batch scanning and exports support multi-site operation.

## 6.6 CI-to-operations bridge

**Opportunity:** Link a CI failure directly to the same hosted finding, source occurrence, owner, and evidence displayed in the dashboard.

**Why users may want it:** Developers should not reconcile independent CI and browser result models.

**Evidence:** CI baseline evaluation and hosted history/finding primitives both exist but remain disconnected.

## 6.7 Guided onboarding and diagnostics

**Opportunity:** Provide a setup checklist for first project, first scan, schedule, and tested notification channel.

**Why users may want it:** Current setup spans environment variables, APIs, documentation, and deployment configuration.

**Evidence:** The breadth of capability is high, while discoverability and administration remain fragmented.

---

# 7. Final recommendation

## What should be built first and why

The next release should build one complete vertical slice around **trusted findings and repair completion** instead of adding another isolated endpoint or dashboard utility.

### Phase 1: Unified project and finding foundation

1. Introduce the organization-scoped project, scan-job, occurrence, evidence, finding, and task persistence model.
2. Migrate or import existing JSONL history.
3. Integrate source occurrence extraction, centralized crawl policy, and confidence classification into the primary scan path.
4. Add secure browser authentication and apply existing RBAC concepts.

**Why first:** A repair workflow built on raw, binary status results would preserve false-positive and identity problems. The trustworthy domain foundation must come first.

### Phase 2: Findings workspace and verification

1. Add global navigation and project context.
2. Deliver the finding list, filters, detail panel, assignment, workflow states, comments, ignore rules, and bulk operations.
3. Add targeted verification and evidence-backed closure.
4. Turn dashboard metrics into drill-down links.

**Why second:** This is the phase most likely to improve daily effectiveness, adoption, and team collaboration.

### Phase 3: Durable monitoring operations

1. Replace synchronous scan requests with durable jobs and progress.
2. Expose schedules with timezone-aware previews.
3. Add notification administration, test delivery, and delivery logs.
4. Add saved views, retention controls, and operational diagnostics.

### Phase 4: Growth and ecosystem

1. Sitemap and URL-list ingestion.
2. CI-to-hosted-finding linkage.
3. Portfolio dashboards.
4. Issue tracker integrations based on validated demand.

## UI and workflow improvements to prioritize immediately

- Introduce persistent navigation and named projects.
- Replace cumulative totals with current unresolved, newly confirmed, recently fixed, and failed-job metrics.
- Add a durable findings workspace.
- Show anchor text, source context, probe evidence, and confidence.
- Add assignment, ignore, resolve, reopen, and verify actions.
- Preserve list state when opening details.
- Add independent widget loading and errors.
- Replace query-token browser authentication.

## Requirements with the highest adoption and efficiency impact

1. **BR-01:** End-to-end link repair workflow.
2. **BR-03:** Trustworthy findings.
3. **UR-01:** Save a project.
4. **UR-02:** Durable finding backlog.
5. **UR-03:** Source occurrence and evidence.
6. **UR-04:** Assignment and repair management.
7. **UR-05:** Verify a fix.
8. **FR-02:** Durable asynchronous scan jobs.
9. **FR-04:** Integrated evidence classification.
10. **UX-03:** Findings workspace.
11. **NFR-01:** Secure browser authentication.
12. **NFR-05:** WCAG 2.2 AA accessibility.

## Final product direction

BrokenLinkBrief 1.0.7 has become a capable investigation interface. The next version should make it an operational repair product. Its strongest market position will not come from checking more URLs than generic link scanners. It will come from reducing the time and uncertainty between discovering a credible problem and proving that a team repaired it.
