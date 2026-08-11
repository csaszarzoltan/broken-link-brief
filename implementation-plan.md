# Implementation Plan

## Executive Summary

This pass will deliver a single coherent vertical slice named **Reliable Monitoring Operations** with two integrated features:

1. **Durable scan jobs** satisfying US-001, US-002, and US-003. Manual saved-project scans and scheduled scans will use one SQLite-backed job model with stable IDs, leases, restart recovery, per-source progress, cancellation, partial completion, and retry of eligible failed sources.
2. **Project and host noise-control policies** satisfying US-004, US-005, and US-006. Projects will gain versioned defaults and optional exact-host overrides for timeout, concurrency, bounded retries, backoff, `Retry-After`, cache reuse, and temporary-status treatment. Every detailed observation will identify the applied policy version. Existing finding ignore/expiry and evidence views will be completed and regression-tested as part of this feature, not reimplemented.

The pass deliberately excludes issue-tracker handoff, browser sessions/RBAC integration, global navigation, billing, and a frontend rewrite. Durable jobs and evidence-linked policy controls are the highest-value, mutually reinforcing research priorities: jobs make monitoring recoverable, while host policies reduce false actionable findings from timeouts and HTTP 429 responses. The existing trusted-finding and Verify Fix workflow remains the product core and must continue to consume the same evidence model without breaking existing APIs or exports.

No mandatory runtime dependency will be added. The implementation will use `sqlite3`, `threading`, `queue`, `urllib`, existing project/scheduler/finding services, and the embedded vanilla-JavaScript dashboard. Existing synchronous `/scan` and `/scan-batch` contracts remain compatible. New project-job APIs are additive.

## Current-State Validation

The supplied project matches `research-findings.md` and the recommendations are actionable:

- `src/brokenlinkbrief/package.py` implements static scanning, batch scanning, URL validation, history, `ScanObservation`, and `scan_link_detailed`.
- `src/brokenlinkbrief/app.py` delivers the standard-library HTTP server and embedded dashboard, including projects, single/batch scans, history, analytics, and trusted findings.
- `src/brokenlinkbrief/projects.py` supplies migration-aware SQLite project persistence and the configured database path.
- `src/brokenlinkbrief/scheduler.py`, `scheduled_scan.py`, and `scheduled_projects.py` provide schedule persistence, leasing, and scheduled execution, but do not share a durable user-visible job model with manual scans.
- `src/brokenlinkbrief/confidence.py`, `findings.py`, and `finding_service.py` already retain bounded attempts, confidence assessment, lifecycle state, ignore expiry, evidence, source occurrences, and verification.
- `src/brokenlinkbrief/app.py` still starts browser single and batch scans as request-bound operations. There is no stable job ID, restart-safe progress, cancellation, or failed-source retry.
- Existing retry behavior is scanner-level and not exposed as a versioned project/host policy. Evidence does not identify the policy revision that produced it.
- The archive contains 98 files, 26 source modules, 43 Python test modules, and 251 statically discoverable top-level test functions. The latest development report records a prior full regression of 838 passed, 45 skipped, one xpassed, and zero failed. Those figures are historical evidence, not a result claimed by this planning phase.
- `pyproject.toml` configures pytest-compatible packaging and Ruff but no type checker, formatter, coverage plugin, or lab gate scripts.
- The required lab gates (`tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh`, `ui-gate.sh`, and `git-push-verify.sh`) are not present in the supplied tree. The development phase must invoke them from the Micro-SaaS Lab environment if available. It must not fabricate pass results or add placeholder gate scripts merely to pass the names. If unavailable, completion is blocked under the lab policy until the external gate toolchain is mounted or supplied.

The research BDD section contains nine complete stories across three epics. This plan selects the six stories belonging to the two P0 epics. Their GUI flows and measurable criteria are retained below and refined by the requirements, UI, API, and test contracts.

## Research Priorities

| Candidate | Research priority | Evidence-backed value | One-pass feasibility | Decision |
|---|---:|---|---|---|
| Durable asynchronous scan jobs | P0 | Prevents refresh/process loss; enables cancel and failed-source retry | High-medium using existing SQLite leases and scan services | Selected |
| Project/host noise-control policies | P0 | Reduces timeout/429 false positives and makes evidence tunable | High-medium because detailed probing already exists | Selected |
| Repair handoff and issue tracker | P1 | Reduces CSV/manual transfer | Medium, but depends on stable job/finding events and secret management | Deferred |
| Schedule administration UI | P1 | Makes recurring monitoring accessible | Medium; selected scope only routes schedule execution through jobs | Deferred UI |
| Secure browser sessions | P1 | Removes query-token exposure | Low for this pass because identity, cookies, CSRF, and migration are cross-cutting | Deferred |
| Integration registry/delivery log | P2 | Improves alert troubleshooting | Medium-low before stable job events | Deferred |
| Portfolio overview | P2 | Helps agencies triage across projects | Medium after job metrics stabilize | Deferred |
| Frontend extraction/global navigation | P2 | Improves maintainability and information architecture | Medium, but unrelated to reliability core | Deferred |
| Hosted packaging/billing | P2 | Monetization | Low without hosted demand validation | Deferred |

Scope boundary: this pass supports scans of **saved active projects** as durable jobs. Ad-hoc `/scan` and `/scan-batch` remain synchronous for backward compatibility and do not create durable jobs. Scheduled project execution will create the same job records, but complete schedule-management UI is deferred.

## Selected Scope for This Pass

### Feature A: Durable Scan Jobs

A new durable job service will accept an active saved project, snapshot its ordered normalized target list and selected scan options, commit a `QUEUED` job, and return a stable job representation immediately. A background worker in the application process will lease queued work, scan one source at a time within the job's configured project concurrency, persist per-source states and sanitized results, and finalize the job exactly once.

Supported job states are `QUEUED`, `RUNNING`, `PARTIALLY_COMPLETED`, `COMPLETED`, `FAILED`, `CANCEL_REQUESTED`, and `CANCELLED`. Source states are `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, and `EXCLUDED`. Terminal job states are immutable. Cancellation is cooperative: once `CANCEL_REQUESTED` is observed, no new source starts; in-flight source requests complete within their configured timeout; remaining pending sources become `CANCELLED`.

A partial or failed job can create one child retry job containing exactly the currently eligible failed sources. Eligibility requires that the source still belongs to the active project and passes URL policy at retry creation. Removed sources are reported as exclusions. Unsafe sources generate per-source validation errors and prevent retry creation when no eligible source remains. Idempotency keys prevent duplicate create, cancel, and retry effects.

### Feature B: Project and Host Noise-Control Policies

Each project will have one active versioned scan policy and zero or more exact-host overrides. Wildcard host rules are intentionally excluded to avoid ambiguous precedence and deceptive breadth. Policy fields:

- `timeout_seconds`: decimal, minimum 1.0, maximum 60.0, default 10.0.
- `max_concurrency`: integer, 1 to 20, default 5 for durable jobs.
- `max_attempts`: integer, 1 to 3 total probe attempts, default 2.
- `backoff_seconds`: decimal, 0 to 10.0, default 0.5; tests inject a no-sleep clock.
- `respect_retry_after`: boolean, default true; numeric `Retry-After` values are capped at 30 seconds. HTTP-date values are supported only when they resolve to 0 through 30 seconds.
- `cache_ttl_seconds`: integer, 0 to 86400, default 0; only successful or terminal 404/410 detailed observations may be reused, never security failures or inconclusive transport errors.
- `temporary_statuses`: fixed selectable subset of 408, 425, 429, 500, 502, 503, and 504, default 408/429/500/502/503/504. These remain retryable/non-actionable until attempt policy is exhausted.

Exact-host override wins over project default; project default wins over built-in defaults. Scheme, port, path, query, and subdomain do not participate in override matching beyond the normalized lowercase ASCII hostname. The effective immutable policy snapshot and policy version are stored on every job and detailed evidence record to keep old results reproducible.

The existing finding Ignore action remains the only finding-level suppression mechanism. This pass completes its UI wording and expiry/recurrence contract but does not add a second suppression table. Expired ignores return to active review only when fresh confirmed evidence is processed, matching US-005 and preventing time-only state churn.

## Deferred Scope and Rationale

1. **Issue-tracker handoff and synchronization.** Prerequisites: stable job/finding event IDs, secret-reference model, integration registry, idempotent delivery log. Suggested phase: Repair Integrations.
2. **Full schedule administration UI.** This pass unifies execution records only. CRUD, timezone preview, pause/resume, and DST UX follow after job reliability is proven. Suggested phase: Monitoring Administration.
3. **Secure browser sessions and delivered RBAC.** Requires identity provisioning, cookie/CSRF policy, logout/expiry, recovery, and deployment migration. Suggested phase: Security and Multi-user Foundation.
4. **Notification administration and delivery log.** Should subscribe to stable job/finding transitions rather than raw scan responses. Suggested phase: Integrations and Delivery.
5. **Global navigation and extracted frontend assets.** Defer until Jobs and Findings establish the final information architecture. Suggested phase: UX Scale-up.
6. **Portfolio dashboard and branded reports.** Depends on organization delivery, project isolation, and stable job metrics. Suggested phase: Agency Operations.
7. **Hosted billing, quotas, and plan enforcement.** Requires hosted product validation and infrastructure economics. Suggested phase: Commercialization.
8. **Wildcard or regex host policies.** Exact-host rules are safer and sufficient for the initial validation. Suggested phase: Advanced Noise Controls.
9. **Credential storage or authenticated browser crawling.** This pass accepts no plaintext secrets and adds no secret vault. Suggested phase: Authenticated Targets.
10. **Distributed worker cluster or external queue.** SQLite single-deployment leasing is the selected architecture. Suggested phase: Scale-out Operations if telemetry proves need.
11. **Ad-hoc scan jobs.** Existing ad-hoc APIs remain synchronous; durable jobs require saved project identity. Suggested phase: Jobs Generalization.
12. **Comments, labels, due dates, and bulk finding actions.** Valuable but unrelated to reliability foundation. Suggested phase: Team Repair Workflow.

## User Stories (BDD)

```json
[
  {
    "id": "US-001",
    "epic": "Durable Scan Jobs",
    "role": "site operator",
    "action": "start a saved-project scan that continues after I leave the page",
    "benefit": "I can monitor large sites without keeping one request open",
    "story": "As a site operator, I want to start a saved-project scan that continues after I leave the page, so that I can monitor large sites without keeping one request open.",
    "gui_flow": [
      "User opens Saved Projects -> sees each active project and its latest health summary",
      "User clicks Run project scan -> sees a queued job card with a stable job ID",
      "User opens the Jobs panel -> sees queued or running state and completed-source count",
      "User refreshes the browser -> sees the same job and preserved progress",
      "Job completes -> user sees completed, partial, failed, or cancelled outcome with a View results action"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "an active project with valid targets",
        "when": "the user starts a scan",
        "then": "the API returns a job ID within 500 ms in the reference test and the job reaches a terminal state without requiring the initiating request to remain open"
      },
      {
        "type": "given",
        "text": "a project containing 10 targets and one target fails",
        "when": "the job finishes",
        "then": "the job is marked PARTIALLY_COMPLETED and reports 9 completed and 1 failed source"
      },
      {
        "type": "given",
        "text": "the job store cannot commit the new job",
        "when": "the user starts a scan",
        "then": "the UI shows a retryable error, creates no phantom job card, and logs no credential-bearing request data"
      }
    ]
  },
  {
    "id": "US-002",
    "epic": "Durable Scan Jobs",
    "role": "site operator",
    "action": "cancel a queued or running scan",
    "benefit": "I can stop work that is no longer useful",
    "story": "As a site operator, I want to cancel a queued or running scan, so that I can stop work that is no longer useful.",
    "gui_flow": [
      "User opens Jobs -> sees a queued or running job",
      "User opens the job actions menu -> sees Cancel only for cancellable states",
      "User clicks Cancel -> sees a confirmation dialog naming the project",
      "User confirms -> sees Cancelling and disabled duplicate action",
      "Worker acknowledges cancellation -> job becomes Cancelled and completed results remain inspectable"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a queued job",
        "when": "the user confirms cancellation",
        "then": "the job becomes CANCELLED before any source begins and no scan notification is sent"
      },
      {
        "type": "given",
        "text": "a running job with 3 of 10 sources complete",
        "when": "the user cancels",
        "then": "no new source starts after cancellation is observed and the 3 completed source results remain available"
      },
      {
        "type": "given",
        "text": "a completed job",
        "when": "the user requests cancellation through the API",
        "then": "the server returns 409 with current state and the UI leaves the job unchanged"
      }
    ]
  },
  {
    "id": "US-003",
    "epic": "Durable Scan Jobs",
    "role": "site operator",
    "action": "retry only failed sources from a partial job",
    "benefit": "I avoid repeating successful network work",
    "story": "As a site operator, I want to retry only failed sources from a partial job, so that I avoid repeating successful network work.",
    "gui_flow": [
      "User opens a partially completed job -> sees successful and failed source groups",
      "User expands Failed sources -> sees sanitized failure reasons",
      "User clicks Retry failed sources -> sees a preview with the failed-source count",
      "User confirms -> a linked retry job is created",
      "Retry finishes -> the parent view shows the latest outcome without duplicating successful source results"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a partial job with 2 failed sources",
        "when": "the user retries failures",
        "then": "the new job contains exactly those 2 normalized sources and references the parent job ID"
      },
      {
        "type": "given",
        "text": "one failed source is no longer in the project",
        "when": "the user opens retry preview",
        "then": "the removed source is excluded and the preview explains the exclusion"
      },
      {
        "type": "given",
        "text": "all failed sources now violate URL policy",
        "when": "the user confirms retry",
        "then": "the server creates no job and returns per-source validation errors without making outbound requests"
      }
    ]
  },
  {
    "id": "US-004",
    "epic": "Noise-Control Policies",
    "role": "SEO operator",
    "action": "apply a domain-specific retry and concurrency policy",
    "benefit": "I can reduce false positives without hiding genuine failures",
    "story": "As a SEO operator, I want to apply a domain-specific retry and concurrency policy, so that I can reduce false positives without hiding genuine failures.",
    "gui_flow": [
      "User opens Project Settings -> selects Noise controls",
      "User adds a hostname rule -> sees retry count, backoff, concurrency, and accepted temporary-status fields",
      "User enters bounded values -> sees an immediate policy summary",
      "User saves -> sees a versioned success message",
      "Next scan -> finding evidence identifies the applied policy and every attempt"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a hostname rule with max concurrency 2 and two retries",
        "when": "the scanner checks six links on that host",
        "then": "no more than two requests are in flight and each link records no more than three total attempts"
      },
      {
        "type": "given",
        "text": "a rule overlaps a broader wildcard rule",
        "when": "the user saves",
        "then": "the UI previews the deterministic precedence and the most specific rule is applied in the policy test"
      },
      {
        "type": "given",
        "text": "retry count exceeds the configured platform maximum",
        "when": "the user saves",
        "then": "the API returns 400 with the retry field identified and no policy version is created"
      }
    ]
  },
  {
    "id": "US-005",
    "epic": "Noise-Control Policies",
    "role": "content operator",
    "action": "ignore a known exception with an expiry and reason",
    "benefit": "expected failures stop obscuring new regressions",
    "story": "As a content operator, I want to ignore a known exception with an expiry and reason, so that expected failures stop obscuring new regressions.",
    "gui_flow": [
      "User opens a finding detail dialog -> sees current classification and evidence",
      "User clicks Ignore -> sees required reason and optional expiry fields",
      "User enters a reason and future date -> sees the effect on alerts and active counts",
      "User saves -> finding is labelled Ignored with expiry and audit entry",
      "Expiry passes and confirmed evidence recurs -> finding returns to Open and appears in active filters"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "an open finding and a valid future expiry",
        "when": "the user ignores it",
        "then": "state becomes IGNORED, version increments by one, and an immutable audit event stores reason and expiry"
      },
      {
        "type": "given",
        "text": "an ignored finding reaches its expiry without new evidence",
        "when": "the user lists active findings",
        "then": "the item remains auditable and is not counted active until a new confirmed observation arrives"
      },
      {
        "type": "given",
        "text": "the reason is blank or over 500 characters",
        "when": "the user submits",
        "then": "the UI announces a field error and the server makes no state change"
      }
    ]
  },
  {
    "id": "US-006",
    "epic": "Noise-Control Policies",
    "role": "developer",
    "action": "see why a result is transient, bot-blocked, inconclusive, or confirmed",
    "benefit": "I can trust automation and tune it with evidence",
    "story": "As a developer, I want to see why a result is transient, bot-blocked, inconclusive, or confirmed, so that I can trust automation and tune it with evidence.",
    "gui_flow": [
      "User opens Findings -> sees classification as text, not color alone",
      "User opens a finding -> sees latest assessment reason",
      "User expands Probe evidence -> sees ordered method, status/error category, latency, and timestamp",
      "User opens Policy applied -> sees the rule version used",
      "User copies a sanitized evidence summary -> receives no headers, credentials, cookies, or response body"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "two terminal 404 or 410 observations under the active policy",
        "when": "classification runs",
        "then": "the assessment is CONFIRMED_BROKEN with ordered bounded attempts"
      },
      {
        "type": "given",
        "text": "a 429 is followed by a 200 response",
        "when": "classification runs",
        "then": "the assessment is RECOVERED or non-actionable and no new finding is created"
      },
      {
        "type": "given",
        "text": "an exception includes a credential sentinel",
        "when": "evidence is persisted and displayed",
        "then": "the sentinel is absent from the database, API response, UI text, and structured log"
      }
    ]
  }
]
```

## Product Requirements

### PR-1: Durable project scan creation and restart-safe execution

**Research problem and evidence:** Request-bound scans cannot survive refreshes or process interruptions. Competitors expose scheduled/controlled crawls, and the research recommends durable jobs as P0.

**Stories:** US-001.

**Behavior:**
- `POST /api/projects/{project_id}/jobs` validates the active project, snapshots ordered targets and effective policy, commits a queued job, wakes the worker, and returns HTTP 202.
- The request returns after the database commit, not after scanning.
- On application startup, expired `RUNNING` leases become `QUEUED` if they have pending sources; a source previously marked `RUNNING` becomes `PENDING` unless its result was committed atomically.
- The worker claims jobs with `BEGIN IMMEDIATE`, a worker ID, lease expiry, and heartbeat. One job can be leased by only one worker at a time.
- Per-source results are committed independently, so already completed source work survives restart.
- Job counts are derived from source rows and returned consistently.

**Inputs:** project ID; optional idempotency key header; optional `render_js` boolean only when every project target uses the same mode. Default is static mode.

**Outputs:** stable job representation with ID, project ID/name snapshot, state, source counts, timestamps, policy version, parent job ID, and links to detail/results.

**Validation/business rules:** project must exist, be active, and contain 1 to 50 targets; every snapshotted target is revalidated before job commit and again before network use; idempotency key length 1 to 128 ASCII characters per authenticated token scope; same key and same request returns original job, same key and different request returns 409.

**Failures:** database commit failure returns 500 with `JOB_CREATE_FAILED`; no phantom job is exposed. Unsafe target returns 400 with per-source details and no job. Worker failure leaves lease recovery possible. A completed source is never rescanned after recovery.

**Compatibility:** no existing endpoint or output field changes. Existing Run project scan button migrates to job creation but ad-hoc scan buttons keep current behavior.

**Acceptance:**
- Reference integration test measures API response under 500 ms with a scanner blocked for at least 1 second, proving request/execution separation.
- Restart fixture preserves job ID and completed-source count and reaches exactly one terminal state.
- Ten-source fixture with one source failure ends `PARTIALLY_COMPLETED` with 9 completed and 1 failed.
- Duplicate idempotent submission creates one database job.

**Non-goals:** distributed queue, priorities, arbitrary uploaded URL jobs, cross-project jobs, livestreaming response bodies.

### PR-2: Job cancellation and terminal-state integrity

**Research problem and evidence:** Long-running monitoring must be controllable and recoverable.

**Stories:** US-002.

**Behavior:** `POST /api/jobs/{job_id}/cancel` changes `QUEUED` or `RUNNING` to `CANCEL_REQUESTED`; the worker acknowledges cancellation and finalizes `CANCELLED`. Cancelling queued work marks all pending sources cancelled without network calls. In-flight calls are not force-killed.

**Inputs:** expected integer version and optional idempotency key.

**Outputs:** updated job plus `cancellation_requested_at` and terminal timestamp when acknowledged.

**Rules:** only `QUEUED` and `RUNNING` are cancellable; `CANCEL_REQUESTED` is idempotent; terminal-state cancellation returns 409 with current representation; expected-version mismatch returns 409.

**Acceptance:** queued cancellation makes zero scanner calls; running cancellation allows the active source to finish but starts zero later sources after acknowledgement; terminal cancel leaves state/data unchanged; completed results remain queryable.

**Non-goals:** OS-level thread termination, partial result deletion, undo cancellation.

### PR-3: Failed-source retry jobs

**Research problem and evidence:** Repeating successful network work wastes time and increases rate-limit exposure.

**Stories:** US-003.

**Behavior:** `POST /api/jobs/{job_id}/retry-failures` previews and then creates one linked child job from eligible failed sources. Request field `preview=true` returns eligibility without mutation; `preview=false` creates the job.

**Inputs:** expected version, preview boolean, idempotency key.

**Outputs:** preview with eligible/excluded/invalid sources, or HTTP 202 child job representation.

**Rules:** parent must be `PARTIALLY_COMPLETED` or `FAILED`; source must have parent state `FAILED`, still belong to the active project, and pass current URL policy. Child snapshots the **current** effective project policy and points to `parent_job_id`. Successful parent sources are never copied.

**Acceptance:** two failed sources create a two-source child; removed source is excluded with `NOT_IN_PROJECT`; all-invalid preview reports each error and creation returns 400/no job; repeated idempotent create returns the same child.

**Non-goals:** retrying individual link results within a successful source, arbitrary manual source selection, recursive automatic retry-job creation.

### PR-4: Versioned project and exact-host scan policies

**Research problem and evidence:** Timeouts and 429 responses produce recurring false positives; official open-source guidance requires retry, concurrency, cache, and authentication tuning.

**Stories:** US-004.

**Behavior:** dashboard and API expose a project default and exact-host overrides. Saving any semantic change creates a new immutable policy version. Jobs snapshot the active version. Policy preview resolves one URL to its effective fields and source rule.

**Inputs:** policy fields defined in Selected Scope; exact hostname in IDNA-normalized lowercase; expected version.

**Outputs:** policy document with active version, project defaults, sorted host overrides, created timestamp, and preview response.

**Rules:** host overrides are exact only; contradictory/duplicate host entries rejected; temporary statuses limited to the fixed allowed set; integers are not accepted as booleans; unknown fields rejected; stale save returns 409 and current representation.

**Acceptance:** six links to one exact host with concurrency 2 never exceed two active requester calls; max attempts 3 produces no fourth attempt; exact host wins over default; invalid retry count makes no policy version; evidence identifies applied version and rule.

**Non-goals:** wildcard rules, regex, per-path policy, plaintext credentials, user script hooks.

### PR-5: Ignore expiry and fresh-evidence recurrence contract

**Research problem and evidence:** Expected failures must not obscure regressions, but suppression must remain visible and reversible.

**Stories:** US-005.

**Behavior:** retain the existing Ignore API and schema. Clarify UI summary and ensure expiry alone does not mutate a finding. On the next fresh `CONFIRMED_BROKEN` observation after expiry, the finding becomes `OPEN`, clears active ignore metadata while preserving it in audit, increments version once, and records `IGNORE_EXPIRED_REOPENED`.

**Inputs:** reason 1 to 500 trimmed characters; optional ISO date not before current local date at submission; expected version.

**Outputs:** finding detail and audit event.

**Rules:** listing an expired ignored finding never silently writes; it is labelled `Expired, awaiting fresh evidence`. Ignored items remain available under `IGNORED` filter. Non-confirmed evidence after expiry does not reopen.

**Acceptance:** valid ignore persists reason/expiry and one audit event; list after expiry does not count it active or change version; fresh confirmed evidence reopens once; blank/long reason returns 400 and creates no event.

**Non-goals:** project-wide ignore expressions, automatic deletion, hidden ignored records.

### PR-6: Evidence explanation and policy provenance

**Research problem and evidence:** Users cannot safely tune policies unless they can see why classification occurred and which rule produced it.

**Stories:** US-006.

**Behavior:** every detailed observation/evidence group stores policy version, rule kind (`PROJECT_DEFAULT` or `HOST_OVERRIDE`), hostname, ordered attempts, and sanitized classification reason. Finding detail displays the latest policy provenance and ordered attempts. Copy evidence creates a text summary client-side from already loaded sanitized fields.

**Inputs:** scanner attempts and immutable policy snapshot.

**Outputs:** additive finding detail fields; no changes to legacy scan JSON/CSV/Markdown/JSONL.

**Rules:** persisted/displayed fields exclude headers, cookies, credential-bearing URLs, response bodies, and uncontrolled exception text. 404/410 confirmation and 429-then-200 behavior remain deterministic under current classifier rules.

**Acceptance:** repeated terminal 404/410 is confirmed; 429 then 200 creates no new finding; sentinel secrets are absent from DB/API/HTML/logs; evidence order equals attempt sequence; copied summary includes policy version and no sensitive fields.

**Non-goals:** raw response inspector, AI-generated diagnosis, policy editing from finding detail.

## UI and UX Specification

### Personas and primary journey

Primary persona: site administrator monitoring one or more saved projects. Secondary persona: SEO/content operator tuning noisy hosts and reviewing trusted findings. Primary journey:

**Dashboard -> Saved project -> Run project scan -> Jobs panel -> observe progress -> partial result -> inspect failed sources -> retry failures -> completed results -> open trusted finding -> inspect applied policy/evidence.**

Friendly failure journey:

**Run project scan -> unsafe target or storage failure -> project action shows a specific error and no job -> user corrects project or retries; filters and existing jobs remain unchanged.**

### Information architecture

Retain the single-page dashboard and current stack. Page order becomes:

1. Product header and health summary.
2. Saved Projects.
3. **Scan Jobs** new section.
4. Trusted Findings.
5. Ad-hoc Scan Pages.
6. Recent Pages.
7. Historical Analytics.

No global navigation is added. Saved projects remain the entry point. “Run project scan” creates a job and scrolls/focuses the matching job card. Findings remain project-scoped.

### Design-system decision and tokens

Use existing semantic HTML, CSS custom properties, dark surfaces, and vanilla JavaScript. No React/Vue/framework/build pipeline. Add/reuse tokens:

- Spacing: `--space-1:4px`, `--space-2:8px`, `--space-3:12px`, `--space-4:16px`, `--space-6:24px`, `--space-8:32px`.
- Radius: 6px controls, 10px cards/dialogs.
- Type: body 16px/1.5, dense metadata 14px/1.45, page heading 32px, section heading 24px.
- Focus: 2px solid focus color with 2px offset and at least 3:1 contrast.
- Text contrast: 4.5:1 normal, 3:1 large/UI boundaries.
- State colors: each badge has visible text and icon/symbol; color is supplemental.
- Controls: 44x44px minimum for primary actions; compact icon-free table actions at least 24x24px with 8px separation.
- Motion: no progress animation required; under `prefers-reduced-motion: reduce`, disable smooth scrolling and transitions.
- Elevation: border plus one subtle shadow only for dialogs; no gradients or decorative motion.

### Component behavior

- Job states use exact labels: Queued, Running, Partial, Completed, Failed, Cancelling, Cancelled.
- Source counts use text such as “4 of 10 sources completed; 1 failed.”
- Primary button labels: `Run project scan`, `View job`, `Cancel scan`, `Retry failed sources`, `Save policy`.
- Secondary labels: `Preview retry`, `Refresh jobs`, `Edit scan policy`, `Reset to defaults`, `Close`.
- All asynchronous controls set `aria-busy` on their region, disable only conflicting actions, and retain Close/navigation controls.

### Accessibility

- `section` elements have headings and `aria-labelledby`.
- Job collection is an ordered list; each job uses an article with heading containing project and short job ID.
- Progress is exposed as text and `<progress max="..." value="...">`, with a polite live summary. Do not announce every polling tick; announce state transitions and completion only.
- Dialogs use native `<dialog>`, labelled headings, visible Close, Escape when no save is pending, initial focus on heading or primary action, and focus restoration.
- Forms use explicit labels, instructions, field-level errors linked by `aria-describedby`, and an assertive summary for failed saves.
- Tables use captions and column headers; mobile layout uses semantic lists/definition lists rather than CSS-breaking table semantics.
- Polling updates never replace focused controls. If a job card disappears due to filter change, focus moves to the Jobs heading and an announcement explains why.

### Responsive behavior

- Desktop `>=1024px`: Jobs list is two-column cards; policy dialog uses two-column field groups and a full-width host-rule table.
- Tablet `640-1023px`: one-column jobs; policy fields in two columns; source detail table scrolls only within its labelled container.
- Mobile `<640px`: full-width cards; all actions stack; policy fields single column; host overrides render as cards; dialogs use viewport width minus 16px and max-height with internal vertical scrolling.
- At 320 CSS pixels and 200% zoom, no page-level horizontal scrolling, clipped labels, or unreachable actions.

## Screen Inventory and User Flows

### Screen 1: Saved Projects section, enhanced job entry

**Purpose:** Start a durable project scan and reach project policy.

**Layout:** Existing project card header and summary remain. Action row order: primary `Run project scan`; secondary `Edit scan policy`, `Load targets`, existing lifecycle actions. A compact line shows `Scan policy vN · X host overrides`.

**States:**
- Loading: existing project skeleton/feedback.
- Disabled: Run disabled for archived project or while create request is pending; reason is visible.
- Validation error: inline banner names unsafe/missing target and links to Edit project.
- Storage/network error: “Could not create scan job. No scan was started.” with Retry.
- Success: “Scan queued as JOB-XXXXXXXX” live message; Jobs section receives focus at matching card.
- First run: card explains that project scans continue if the page is refreshed.

**Click path:** Dashboard -> Saved Projects -> project card -> Run project scan -> queued job appears -> focus moves to job heading.

### Screen 2: Scan Jobs section

**Purpose:** Review current/recent jobs, progress, terminal outcome, and actions.

**Header block:** `Scan Jobs`, one-sentence explanation, project filter, state filter, `Refresh jobs`. Default shows all active and the 20 latest terminal jobs; API pagination remains available.

**Body:**
- Loading: three noninteractive skeleton cards plus “Loading scan jobs.”
- Empty: “No project scans yet.” CTA `Run a saved project` focuses Saved Projects heading.
- Card header: project name, state badge, created time, short job ID.
- Progress block: text and `<progress>`; counts for pending/running/completed/failed/cancelled.
- Metadata: source count, static/SPA mode, policy version, parent retry link when applicable.
- Actions: `View job`; `Cancel scan` only for eligible states; `Retry failed sources` only for partial/failed terminal state.
- Error: preserve filters and existing cards; show Retry.
- Stale: after two consecutive poll failures, retain data with “Updates paused” and manual Retry.
- Success transition: announce once, update badge and actions without stealing focus.

Polling is every 2 seconds while any visible job is nonterminal, 10 seconds otherwise, paused when document is hidden, and immediately refreshed on visibility return.

### Screen 3: Job Detail dialog

**Purpose:** Inspect source-level outcomes and perform cancellation/retry.

**Header:** project name, full state text, job ID copy button, Close.

**Summary:** created/started/completed timestamps, policy version, parent/child links, progress counts.

**Source sections:** filter tabs All, Failed, Completed, Pending/Cancelled. Each row/card shows source URL, state, attempts count, sanitized reason, start/end time. Results are capped to summary fields; existing scan results can open in current result review if available.

**Actions:** primary is state-dependent: `Cancel scan` for active job, `Retry failed sources` for partial/failed, otherwise `Close`. Secondary `Copy job ID`.

**Cancellation flow:** View job -> Cancel scan -> confirmation names remaining source count -> Confirm cancellation -> dialog shows Cancelling -> final state Cancelled; Close remains available.

**Retry flow:** View partial job -> Retry failed sources -> preview panel lists eligible/excluded/invalid -> `Create retry job` -> new child job link appears -> dialog can switch to child.

**Failure states:** 409 refreshes current job and explains state changed; 500 preserves dialog and offers Retry; invalid sources remain visible but cannot be selected.

### Screen 4: Scan Policy dialog

**Purpose:** Configure project defaults and exact-host overrides with deterministic preview.

**Header:** `Scan policy for the selected project`, active version, Close.

**Project defaults block:** labelled fields for timeout, max concurrency, max attempts, backoff, respect Retry-After, cache TTL, and temporary statuses. Inline min/max hints always visible.

**Host overrides block:** existing rules sorted hostname; each card/row shows hostname and only overridden fields. Actions `Edit` and `Remove`. `Add host override` opens an inline subform. Hostname is exact-match and helper text states subdomains do not inherit.

**Preview block:** URL field and `Preview effective policy`; result names project/default or exact host rule and resolved values. Preview never saves.

**Footer:** primary `Save policy`, secondary `Reset to built-in defaults`, `Cancel`.

**States:**
- Loading: form skeleton; Save disabled.
- Validation: field-specific errors and summary; first invalid field focused.
- Conflict: “Policy changed in another session”; server version reloads, locally typed values are retained in a compare panel, user explicitly reapplies.
- Success: “Scan policy vN saved”; project card updates; dialog remains open.
- Error: no version created; form remains editable.
- Empty host state: “No host overrides. Project defaults apply to every host.”

### Screen 5: Trusted Finding detail, policy provenance enhancement

**Purpose:** Explain result trust and suppression state.

**Added block:** `Policy applied` directly above Probe evidence. Shows policy version, Project default or Host override, exact hostname, max attempts, timeout, and observation timestamp. `Copy evidence summary` copies sanitized text and announces success.

**Ignore state:** active ignore displays reason and expiry. Expired ignore displays `Expired, awaiting fresh confirmed evidence`; it does not claim the finding is open. On recurrence, detail updates to Open with audit event.

**States:** existing loading/error/mutation feedback retained. Missing historical policy fields show `Legacy observation, policy provenance unavailable`, not fabricated defaults.

### End-to-end successful flow

1. User opens dashboard; projects and jobs load independently.
2. User selects Run project scan on an active project.
3. HTTP 202 returns; a queued job card is shown and focused.
4. Worker leases job; progress updates without a page refresh.
5. One source fails and the job becomes Partial.
6. User opens job detail, selects Retry failed sources, reviews exactly one eligible source, and creates child job.
7. Child completes; user opens trusted finding and sees the applied policy version with ordered sanitized attempts.

### Friendly failure recovery flow

1. User clicks Run project scan.
2. Server revalidation finds a now-unsafe target.
3. No job is committed; project card shows the specific source and safe error code.
4. User edits project, removes/corrects target, and retries.
5. A queued job appears; previous jobs and filters were never cleared.

### UI verification contract

Developer must start the supported server, exercise deterministic fixtures, and verify desktop 1440x900, tablet 768x1024, and mobile 390x844 for empty, running, partial, job detail, policy validation, and friendly failure states. When Playwright/Chromium is available, capture screenshots to a temporary audit directory excluded from packaging and run browser E2E. Otherwise perform semantic DOM tests plus manual browser checks and document the limitation. Keyboard-only traversal, 200% zoom/reflow, reduced motion, contrast calculations, and one screen-reader smoke test are mandatory and recorded in `development-report.md`.

## Architecture and Technical Design

### Component boundaries

- `src/brokenlinkbrief/scan_jobs.py` new: immutable job/source models, schema migration, CRUD, leases, optimistic versions, idempotency, counts, cancellation, retry eligibility.
- `src/brokenlinkbrief/job_service.py` new: project validation, policy snapshot, job creation, cancellation, retry preview/create, worker orchestration, source execution, finding/history handoff.
- `src/brokenlinkbrief/scan_policy.py` new: policy models, validation, exact-host resolution, schema/store, versioning, effective snapshot.
- `src/brokenlinkbrief/package.py` modified narrowly: detailed scanner accepts an explicit immutable effective policy and injectable wait/cache/requester; legacy functions retain signatures and defaults.
- `src/brokenlinkbrief/scheduled_scan.py` modified: scheduled execution creates or waits on the shared job service rather than maintaining a divergent durable state. Existing public `ScheduledScanExecutor` remains compatible through an adapter.
- `src/brokenlinkbrief/app.py` modified: APIs, one process-local worker lifecycle, dashboard Jobs and policy UI, polling, focus management.
- `src/brokenlinkbrief/finding_service.py` and `findings.py` modified: persist policy provenance and implement fresh-evidence ignore-expiry transition exactly once.
- `projects.py` may expose shared configured DB/common connection helper without changing public project semantics.

### Job data flow

Create request -> auth -> project lookup -> target revalidation -> policy snapshot -> transaction inserts job and source rows plus idempotency record -> HTTP 202 -> worker wake -> atomic lease -> per-source URL revalidation -> scan with effective exact-host policies -> persist result/evidence/history/finding summary -> update counts/heartbeat -> observe cancellation -> terminal finalize.

Scheduled due work calls the same `JobService.create_project_job` with origin `SCHEDULED` and deterministic idempotency key `schedule:<schedule_id>:<due_slot>`. Manual origin is `MANUAL`; retry is `RETRY`.

### State management

Server database is authoritative. Dashboard memory contains filters, open job ID, latest versions, polling timer, and pending action flags only. No optimistic terminal-state claim. API mutation responses replace local records. Polling uses `updated_after` where possible to reduce payload.

### Persistence schema

Use `BROKENLINKBRIEF_PROJECT_DB` and migration conventions already used by projects/findings. New logical tables:

- `scan_jobs`: id, project_id, project_name_snapshot, origin, state, scan_mode, parent_job_id, policy_version_id, target_count, timestamps, worker_id, lease_expires_at, heartbeat_at, cancel_requested_at, version, sanitized terminal error.
- `scan_job_sources`: id, job_id, ordinal, source_url, state, started/completed timestamps, result_summary_json, sanitized_error_code/detail, attempts_count, version; unique(job_id, source_url).
- `scan_job_idempotency`: scope_hash, idempotency_key_hash, request_hash, job_id, created_at; unique(scope_hash, idempotency_key_hash).
- `scan_policy_versions`: id, project_id, version_number, project_defaults_json, created_at; unique(project_id, version_number).
- `scan_policy_host_overrides`: policy_version_id, normalized_hostname, override_json; unique(policy_version_id, normalized_hostname).
- `scan_observation_cache`: project_id, normalized_url, policy_fingerprint, observed_at, expires_at, observation_json; bounded cleanup on writes.

Add indexes on jobs by project/state/created, lease expiry, sources by job/state/ordinal, policy project/version, and cache expiry. Foreign keys point to projects and parent jobs where compatible. Migration is idempotent, transactional, and never drops or rewrites existing tables.

Result summary JSON contains counts and link-result references needed by current result/history integration, not raw bodies. Policy JSON uses sorted keys and validated primitive fields. Policy fingerprint is SHA-256 of canonical effective fields, excluding version metadata.

### Worker model

One daemon worker coordinator starts with the HTTP application. It maintains a bounded `ThreadPoolExecutor` only for sources within the currently leased job. Global simultaneous source requests are capped at 20. Job-level concurrency is the policy's project default; exact-host concurrency is additionally enforced by per-host semaphores. Worker heartbeat every 5 seconds; lease duration 30 seconds; startup recovery claims leases expired by more than 30 seconds. Tests inject clock, sleeper, worker ID, and scanner.

Shutdown stops claiming new jobs, requests no implicit cancellation, allows up to 10 seconds for in-flight commits, then exits. Remaining lease recovers on next startup.

### Decision rationale and alternatives

- **SQLite over Redis/Celery:** preserves self-hosted dependency-light architecture and is adequate for one application deployment. Distributed queues are deferred.
- **One process-local worker over subprocesses:** easiest compatibility with current server and injectable scanner. Cooperative cancellation is explicit.
- **Exact-host overrides over wildcard:** deterministic, safer, and sufficient to validate demand.
- **Immutable policy versions over mutable JSON:** historic evidence remains explainable.
- **Additive job APIs over changing `/scan`:** protects clients and exports.
- **Embedded UI over framework rewrite:** current stack can deliver the bounded screens with lower risk.

## Data, API, and Compatibility Changes

All new endpoints use existing optional scan-token authorization and JSON error mapping. Error envelope for new APIs is `{"code":"STABLE_CODE","detail":"Human-readable detail","field":null,"current":null}`; existing endpoint envelopes do not change.

### Job APIs

- `POST /api/projects/{project_id}/jobs`
  - Header: optional `Idempotency-Key`.
  - Body: `{"render_js": false}`.
  - Response 202: `{"job": {"id":"job-id","state":"QUEUED","project_id":"project-id"}}`.
- `GET /api/jobs?project_id=&state=&limit=20&offset=0&updated_after=`
  - Limit 1 to 100; state may repeat or be comma-separated as documented, one representation selected in implementation: comma-separated uppercase values.
  - Response: `{"items":[],"total":0,"limit":20,"offset":0}`.
- `GET /api/jobs/{job_id}`
  - Response includes job and paginated first 100 source summaries. Additional source page: `GET /api/jobs/{id}/sources?state=&limit=&offset=`.
- `POST /api/jobs/{job_id}/cancel`
  - Body: `{"version": 3}`.
- `POST /api/jobs/{job_id}/retry-failures`
  - Body preview: `{"version":3,"preview":true}`.
  - Body create: `{"version":3,"preview":false}`, optional Idempotency-Key.

Job summary exact fields: `id`, `project_id`, `project_name`, `origin`, `state`, `scan_mode`, `parent_job_id`, `policy_version`, `target_count`, `pending_count`, `running_count`, `completed_count`, `failed_count`, `cancelled_count`, `created_at`, `started_at`, `completed_at`, `updated_at`, `cancel_requested_at`, `version`.

### Policy APIs

- `GET /api/projects/{project_id}/scan-policy` returns active version or synthesized built-in defaults with version 0 and no host overrides.
- `PUT /api/projects/{project_id}/scan-policy` body: `{"version":N,"defaults":{...},"host_overrides":[{"hostname":"api.example.com","overrides":{...}}]}`.
- `POST /api/projects/{project_id}/scan-policy/preview` body: `{"url":"https://api.example.com/path","draft":<optional unsaved policy document>}`; response identifies effective values and rule source.

### Additive finding detail fields

Latest evidence gains `policy_version`, `policy_rule`, `policy_hostname`, and `policy_fingerprint`. Legacy rows return null for these fields. No existing field is renamed or removed.

### Compatibility

- `/scan`, `/scan-batch`, all formats, project CRUD/import/export/duplicate/pin, findings endpoints, notifications, CLI, and CI remain compatible.
- Portable project configuration remains schema version 1 and excludes runtime policy/job state. A future schema version will be required before exporting policy; this pass does not silently extend it.
- Duplicated/imported projects receive built-in policy version 0 and no jobs.
- Archiving a project prevents new jobs/retries/policy mutation but preserves readable history/jobs/policies.
- Existing schedules retain configuration; their execution adapter creates jobs without changing their public configuration schema.

## Security and Privacy Considerations

- Revalidate every project source and discovered target immediately before network use. Stored job/source URLs are untrusted.
- Respect existing redirect and private-network safeguards on every attempt.
- Never persist headers, cookies, authorization values, response bodies, URLs containing credentials, raw exceptions, or plaintext idempotency keys. Store scoped hashes.
- Policy supports no secret values. Authenticated-target support is deferred.
- Cap timeout, attempts, concurrency, Retry-After, body reads, cache lifetime, pagination, and source counts to prevent resource exhaustion.
- Exact-host matching uses parsed normalized hostname, not string suffix matching, preventing `example.com.attacker.test` confusion.
- Cache key includes project, normalized URL, and policy fingerprint; do not share observations across projects.
- Cancellation and retry require authorization and optimistic version to prevent lost updates.
- HTML rendering uses textContent/escaping helper; no dynamic inline event handlers for untrusted data.
- Logs include event, job/project IDs, state, counts, latency, and correlation ID. They exclude query token, authorization header, idempotency key, full result body, evidence context, and secrets.
- Structured security events: unsafe job source, unsafe retry source, lease recovery, policy validation rejection, and evidence sanitization failure.
- Job retention defaults to existing history retention behavior; no automatic deletion in this pass. Document storage implications.

## Test Strategy (TDD)

Implementation is failing-test first. For each RED test, record test name and initial failure in `development-report.md`, then implement the minimum coherent behavior.

### Feature A RED tests

New modules:
- `tests/test_scan_jobs_store.py`: schema migration, create, counts, state transitions, lease exclusivity, heartbeat/recovery, idempotency, terminal immutability, cancellation, retry eligibility.
- `tests/test_job_service.py`: project validation, target snapshot, under-500-ms create separation, partial outcome, no rescan after recovery, finding/history handoff.
- `tests/test_jobs_api.py`: auth, shapes, pagination, 202, 400, 404, 409, 500 sanitization, idempotency.
- `tests/test_jobs_ui.py`: semantic region/cards/dialog, polling, progress, focus, cancel/retry flows, empty/loading/stale/error states, mobile rules.
- `tests/test_job_restart_integration.py`: real temporary SQLite reopen and local HTTP fixture; completed source survives coordinator restart.

Required named coverage:
- US-001 happy: `test_job_create_returns_before_blocked_scanner_and_completes_later`.
- US-001 edge: `test_ten_source_job_with_one_failure_is_partial_with_exact_counts`.
- US-001 error: `test_create_commit_failure_exposes_no_job`.
- US-002 happy: `test_queued_cancel_makes_zero_scanner_calls`.
- US-002 edge: `test_running_cancel_finishes_active_source_and_starts_no_next_source`.
- US-002 error: `test_terminal_cancel_returns_conflict_without_mutation`.
- US-003 happy: `test_retry_child_contains_only_failed_sources`.
- US-003 edge: `test_retry_preview_excludes_source_removed_from_project`.
- US-003 error: `test_all_unsafe_retry_sources_create_no_job`.

Real-I/O coverage uses a local HTTP server with one delayed, one 200, and one failing source. No public network in automated tests.

### Feature B RED tests

New modules:
- `tests/test_scan_policy.py`: validation boundaries, canonical serialization, exact-host resolution, versioning, stale conflicts, policy fingerprint.
- `tests/test_policy_scanning.py`: per-host semaphore, attempts cap, Retry-After cap, temporary statuses, cache eligibility/isolation, classifier outcomes.
- `tests/test_policy_api.py`: auth, GET/PUT/preview, unknown fields, archived project, malformed hostname, 409.
- `tests/test_policy_ui.py`: labelled form, host cards, validation/focus, preview, conflict recovery, success, provenance display/copy.
- Focused additions to `tests/test_trusted_findings.py`: expiry only on fresh confirmed evidence and provenance/sanitization.

Required named coverage:
- US-004 happy: `test_exact_host_policy_limits_concurrency_and_attempt_count`.
- US-004 edge: `test_exact_host_override_wins_over_project_default`.
- US-004 error: `test_invalid_attempt_limit_creates_no_policy_version`.
- US-005 happy: `test_ignore_with_reason_and_expiry_audits_once`.
- US-005 edge: `test_expired_ignore_listing_does_not_reopen_without_fresh_evidence`.
- US-005 error: `test_blank_or_excessive_ignore_reason_does_not_mutate`.
- US-006 happy: `test_repeated_404_410_evidence_includes_policy_provenance`.
- US-006 edge: `test_429_then_200_is_non_actionable_and_creates_no_finding`.
- US-006 error: `test_secret_sentinel_absent_from_db_api_ui_and_logs`.

### Regression, boundary, and accessibility

- Boundary values for all numeric policy fields, limits, offsets, idempotency key length, 50 targets, zero eligible retries, and lease expiry.
- Existing SSRF tests extended to stored job sources, retry jobs, cached observations, and policy preview.
- Existing project archive/restore, duplicate/import, schedule, findings, exports, notifications, SPA, and CLI tests remain green.
- Node JavaScript syntax validation via existing `tests/test_dashboard_javascript.py` and `node --check` path when Node exists.
- Accessibility contract tests for headings, labels, live regions, progress naming, dialog naming/focus restoration, error associations, non-color labels, reduced motion, and focus styles.
- Browser E2E only when Playwright and Chromium are already available; do not make Playwright mandatory runtime dependency.

### Commands

Targeted development commands:

```bash
python -m pytest -q tests/test_scan_jobs_store.py tests/test_job_service.py tests/test_jobs_api.py tests/test_jobs_ui.py tests/test_job_restart_integration.py
python -m pytest -q tests/test_scan_policy.py tests/test_policy_scanning.py tests/test_policy_api.py tests/test_policy_ui.py tests/test_trusted_findings.py
python -m pytest -q tests/test_projects.py tests/test_project_quick_scan.py tests/test_scheduler.py tests/test_scheduled_scan.py tests/test_ssrf_enhanced.py tests/test_dashboard_javascript.py
```

Full regression and quality:

```bash
python -m pytest -q --disable-warnings
ruff check src tests
python -m compileall -q src tests
python -m pip wheel . --no-deps -w dist-test
```

Remove `dist-test` after isolated wheel import smoke. No type-check command is claimed because the repository has no configured type checker. Formatting uses Ruff check only unless the development environment supplies a project-approved formatter; do not add one silently.

Startup smoke uses temporary DB/history paths, starts `python -m brokenlinkbrief.app`, verifies HTTP 200 from `/health` and `/dashboard`, creates a temporary project/job through local HTTP, observes a terminal state against local fixtures, then stops the process.

Lab gates from the lab toolchain, mandatory before completion:

```bash
tdd-gate-v3.sh
bdd-gate.sh
security-gate.sh
doc-sync-check.sh
ui-gate.sh
git-push-verify.sh
```

Because these scripts are absent from this archive, the developer must run the official externally provided commands. “Command not found” is a blocking result, not a pass.

### Coverage and pass/fail criteria

- At least 90% statement coverage for new/changed `scan_jobs.py`, `job_service.py`, and `scan_policy.py` using the lab coverage gate. Branch outcomes listed above must all have named tests.
- Zero failing targeted or full regression tests.
- Zero Ruff violations in `src` and `tests`.
- Compileall, wheel build/import, startup smoke, and JavaScript syntax pass.
- No public-network dependency in automated tests.
- Every BDD acceptance criterion maps to one named test in the traceability matrix or development report.
- Lab gates and push verification pass with captured command output.

## Documentation Deliverables

### `README.md`

Add Reliable Monitoring Operations overview; project scan job journey; exact job states; cancellation and failed-source retry; policy defaults/host overrides; limits; evidence provenance; compatibility note for synchronous ad-hoc APIs; SQLite persistence/backup; startup worker behavior; privacy and storage notes.

### `CHANGELOG.md`

Add one release entry with actual version/date, durable job APIs and states, schedule unification, policy fields and bounds, migration, ignore-expiry clarification, security/privacy controls, actual test/gate counts, and compatibility statement. Never predict counts.

### API documentation

Create `docs/scan-jobs.md` for endpoint shapes, state machine, idempotency, leases/recovery, cancellation, retry preview/create, pagination, errors, and examples. Create `docs/scan-policies.md` for fields, validation, exact-host precedence, policy versioning, cache rules, evidence provenance, and examples. Update `docs/README.md` links.

### `FEATURES-DONE.md`

Replace/update with PR-1 through PR-6, US-001 through US-006, exact delivered behavior, exclusions, migrations, endpoints, UI surfaces, and named test evidence. No aspirational claims.

### `development-report.md`

Record architecture decisions, RED/GREEN chronology, schema migration validation, real local-I/O restart evidence, targeted/full results, coverage, Ruff, compile, wheel, startup, JS, lab gates, UI screenshots/checks, accessibility checks, security/secret scan, changed files, limitations, commit hash, remote branch, push verification, and artifact integrity.

## Expected File Changes

Expected additions:

- `src/brokenlinkbrief/scan_jobs.py`
- `src/brokenlinkbrief/job_service.py`
- `src/brokenlinkbrief/scan_policy.py`
- `tests/test_scan_jobs_store.py`
- `tests/test_job_service.py`
- `tests/test_jobs_api.py`
- `tests/test_jobs_ui.py`
- `tests/test_job_restart_integration.py`
- `tests/test_scan_policy.py`
- `tests/test_policy_scanning.py`
- `tests/test_policy_api.py`
- `tests/test_policy_ui.py`
- `docs/scan-jobs.md`
- `docs/scan-policies.md`

Expected modifications:

- `src/brokenlinkbrief/package.py`
- `src/brokenlinkbrief/app.py`
- `src/brokenlinkbrief/scheduled_scan.py`
- `src/brokenlinkbrief/scheduler.py` only if deterministic schedule-slot idempotency needs an exposed identifier
- `src/brokenlinkbrief/projects.py` only for shared DB helper/migration hook
- `src/brokenlinkbrief/findings.py`
- `src/brokenlinkbrief/finding_service.py`
- `tests/test_trusted_findings.py`
- `tests/test_project_quick_scan.py`
- `tests/test_scheduled_scan.py`
- `tests/test_ssrf_enhanced.py`
- `tests/test_dashboard_javascript.py`
- `README.md`
- `CHANGELOG.md`
- `docs/README.md`
- `FEATURES-DONE.md`
- `development-report.md`
- `pyproject.toml` and `src/brokenlinkbrief/__init__.py` only to synchronize the actual release version; no dependency additions are expected.

Files not expected to change: deployment configuration, webhook/notification implementation, governance/RBAC, CI gate, SPA scanner internals, historical reports, project portable schema, and this `implementation-plan.md` except for documented correction discovered during development.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Scans survive page refresh and request lifetime | Research P0 durable jobs; competitors expose controlled recurring crawls | US-001 | PR-1 | Create returns within 500 ms while blocked scanner completes later | `scan_jobs.py`, `job_service.py`, `app.py` | `test_job_create_returns_before_blocked_scanner_and_completes_later` | P0 |
| Partial results survive restart | Research recommends restart-safe progress | US-001 | PR-1 | Completed source count survives DB reopen and reaches one terminal state | store/service worker recovery | `test_completed_source_survives_coordinator_restart` | P0 |
| One failed source does not erase success | Monitoring reliability need | US-001 | PR-1 | 10 targets, one failure -> 9 completed/1 failed/Partial | job service | `test_ten_source_job_with_one_failure_is_partial_with_exact_counts` | P0 |
| User can stop obsolete work | Long scans need control | US-002 | PR-2 | Queued cancel causes zero scanner calls | job store/service/API/UI | `test_queued_cancel_makes_zero_scanner_calls` | P0 |
| Cooperative cancellation preserves evidence | Reliability and auditability | US-002 | PR-2 | Active source completes; no later source starts | worker coordinator | `test_running_cancel_finishes_active_source_and_starts_no_next_source` | P0 |
| Terminal states cannot be rewritten | Trustworthy job history | US-002 | PR-2 | Terminal cancel returns 409 and unchanged representation | store/API | `test_terminal_cancel_returns_conflict_without_mutation` | P0 |
| Retry only failed work | Research notes repeated checks and quota/rate-limit anxiety | US-003 | PR-3 | Child contains exactly parent failed sources | service/store | `test_retry_child_contains_only_failed_sources` | P0 |
| Project edits affect retry eligibility | Sources must remain project-owned | US-003 | PR-3 | Removed source excluded with code | service/API/UI preview | `test_retry_preview_excludes_source_removed_from_project` | P0 |
| Unsafe stored source never becomes SSRF path | Project security constraint | US-003 | PR-3 | All unsafe retry sources create no job or request | policy/service | `test_all_unsafe_retry_sources_create_no_job` | P0 |
| 429/timeouts need host-aware tuning | Lychee guidance and public false-positive issues in research | US-004 | PR-4 | Host concurrency <=2 and attempts <=3 | `scan_policy.py`, `package.py`, service | `test_exact_host_policy_limits_concurrency_and_attempt_count` | P0 |
| Policy precedence must be deterministic | Research warns over-tuning risks | US-004 | PR-4 | Exact host wins over project default | policy resolver | `test_exact_host_override_wins_over_project_default` | P0 |
| Invalid tuning must not create state | Safety and auditability | US-004 | PR-4 | Attempts >3 returns 400 and no version | policy store/API/UI | `test_invalid_attempt_limit_creates_no_policy_version` | P0 |
| Expected exception needs reason and expiry | Research noise-control demand | US-005 | PR-5 | Ignore persists reason/expiry and one audit event | findings/service/UI | `test_ignore_with_reason_and_expiry_audits_once` | P0 |
| Expiry alone must not invent fresh risk | Research specifies fresh confirmed recurrence | US-005 | PR-5 | Listing after expiry makes no version/state write | findings store | `test_expired_ignore_listing_does_not_reopen_without_fresh_evidence` | P0 |
| Invalid ignore is rejected | Existing privacy/lifecycle contract | US-005 | PR-5 | Blank/>500 reason makes no mutation/event | API/store/UI | `test_blank_or_excessive_ignore_reason_does_not_mutate` | P0 |
| Users need explainable classification | Trust is product differentiator | US-006 | PR-6 | 404/410 evidence includes policy provenance and ordered attempts | package/findings/detail UI | `test_repeated_404_410_evidence_includes_policy_provenance` | P0 |
| Temporary recovery must not create work | False-positive evidence | US-006 | PR-6 | 429 then 200 creates no finding | detailed scanner/finding service | `test_429_then_200_is_non_actionable_and_creates_no_finding` | P0 |
| Evidence must not leak secrets | Security/privacy constraint | US-006 | PR-6 | Sentinel absent from DB/API/UI/logs | sanitizer/store/app | `test_secret_sentinel_absent_from_db_api_ui_and_logs` | P0 |

## Risks and Mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| SQLite contention between worker, API, findings, schedules | Locked writes or slow UI | WAL, short transactions, busy timeout, one write per source, deterministic retry, contention integration test |
| Duplicate work after crash | Extra requests/notifications | Leases, atomic source completion, deterministic schedule idempotency, recovery tests |
| Python thread cannot be force-cancelled | Slow cancellation | Cooperative boundary between sources, strict timeout, no new source after acknowledgement, accurate Cancelling state |
| Per-host policy hides genuine failures | False negatives | Tight bounds, exact-host only, immutable versions, visible provenance, conservative classifier, reset action |
| Retry-After stalls worker | Poor throughput | Cap at 30 seconds, release host slot during wait only if implementation proves fairness, injectable clock tests |
| Cache returns stale health | Missed regressions | TTL off by default, only safe eligible outcomes, policy fingerprint/project isolation, visible cache provenance |
| Embedded app.py becomes fragile | UI regressions | Small rendering functions, semantic contract tests, Node syntax, optional E2E; frontend extraction deferred |
| Worker startup/shutdown affects current server | Hangs or lost progress | daemon coordinator, bounded shutdown, expired-lease recovery, startup smoke |
| Scheduled executor compatibility breaks | Existing automation failure | Adapter preserves public API and tests; schedule creates deterministic job slot |
| Policy JSON schema drifts | Unreadable evidence | versioned immutable schema, canonical serialization, migration and legacy null behavior |
| Lab gates absent | Unverified delivery | Treat unavailable official scripts as blocking; do not create fake pass-through scripts |
| Git remote unavailable | Cannot satisfy push policy | Development phase must report blocked completion and retain verified artifact; no false push claim |

## Definition of Done

- [ ] PR-1 through PR-6 are implemented with no facade, placeholder, simulated persistence, or disabled UI action.
- [ ] US-001 through US-006 happy, edge, and error criteria work end to end.
- [ ] Manual saved-project and scheduled scans use the same durable job model.
- [ ] Jobs survive restart, prevent duplicate committed execution, expose accurate progress, support cooperative cancellation, and retry only eligible failed sources.
- [ ] Project and exact-host policies validate all bounds, resolve deterministically, version immutably, and appear in evidence provenance.
- [ ] Ignore expiry reopens only on fresh confirmed evidence and all audit/version rules pass.
- [ ] Existing scan, batch, project, finding, export, notification, schedule, CLI, and CI contracts remain compatible.
- [ ] SSRF revalidation covers job creation, worker execution, retry, redirects, and cached observations.
- [ ] No headers, credentials, cookies, response bodies, plaintext idempotency keys, or secret sentinels appear in DB/API/UI/logs.
- [ ] Every acceptance criterion has named failing-first automated evidence and traceability.
- [ ] Unit, API, local real-I/O restart, UI contract, accessibility, boundary, migration, and security tests pass.
- [ ] `python -m pytest -q --disable-warnings` passes with zero failures.
- [ ] `ruff check src tests` and `python -m compileall -q src tests` pass.
- [ ] Wheel build and isolated import smoke pass; temporary build output is removed.
- [ ] Startup smoke returns HTTP 200 for `/health` and `/dashboard` and completes a local durable job.
- [ ] JavaScript syntax passes when Node is available.
- [ ] Changed/new core modules meet at least 90% statement coverage through the lab coverage gate.
- [ ] Desktop, tablet, mobile, keyboard, 200% zoom/reflow, reduced motion, contrast, and screen-reader checks are completed and recorded.
- [ ] Official `tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh`, and `ui-gate.sh` pass. Missing official scripts block completion.
- [ ] README, CHANGELOG, scan-job/policy API docs, FEATURES-DONE, and development-report match actual delivered behavior and actual results.
- [ ] Secret scan and stray-artifact scan pass; no runtime DB, cache, venv, coverage, build, screenshots, editor state, or credentials are packaged.
- [ ] A git commit with an accurate conventional message is created, pushed to the configured remote, and `git-push-verify.sh` confirms remote commit equality. Missing remote/access blocks completion.
- [ ] Every requirement maps to implementation locations and named test evidence in the final report.
- [ ] The complete project, not a patch, is repackaged; ZIP integrity, listing, clean extraction, required-file presence, and no-extra-enclosing-directory checks pass.
