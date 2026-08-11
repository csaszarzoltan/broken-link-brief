# Implementation Plan

## Executive Summary

This pass will finish the two P0 product slices already established by research and partially delivered in BrokenLinkBrief 1.4.1: **Operational Scan Jobs** and **Applied Noise Controls**. The implementation must complete the user-facing and execution gaps rather than add another subsystem.

Feature 1, **Operational Scan Jobs**, covers US-001 through US-003. The durable store already has exclusive leases, expiry recovery, cancellation, and failed-source retry primitives. This pass makes those primitives production-operable by adding active heartbeats during long requests, policy-aware bounded concurrency, scheduled-job unification, paginated job APIs, adaptive polling, a complete Job Detail dialog, cancellation confirmation, and retry preview/create flows.

Feature 2, **Applied Noise Controls**, covers US-004 through US-006. Policy versions and a conservative observation-cache adapter already exist, but they are not wired into network execution or findings. This pass applies effective policies to attempts, backoff, Retry-After, timeout, concurrency, and cache; implements fresh-evidence ignore expiry; persists sanitized policy provenance with finding evidence; and delivers the Scan Policy and Policy Applied interfaces.

The plan adds no runtime framework or service dependency. It preserves the standard-library server, SQLite, vanilla JavaScript dashboard, existing APIs/exports, and optional Playwright behavior. Scope is deliberately limited to completing six existing stories. Issue-tracker integration, account sessions/RBAC, schedule-administration screens, and global navigation remain deferred.

## Current-State Validation

The project and research are aligned. The archive contains 110 files and identifies version 1.4.1. Verified foundations include:

- `scan_jobs.py`: additive lease columns, exclusive claim, heartbeat validation, stale-owner rejection, expired-lease recovery, source persistence, cancellation, and idempotency.
- `job_service.py`: project job creation, process-local coordinator, source execution, cancellation boundary, and failed-source retry.
- `scan_policy.py`: validated defaults, immutable versions, exact-host overrides, normalization, precedence, and fingerprint.
- `observation_cache.py`: project/URL/fingerprint isolation with conservative classification eligibility.
- `app.py`: additive job/policy APIs and a basic Scan Jobs region.
- Story-focused tests for persistence, cancellation, retry, policy persistence, lease recovery, and cache isolation.

The current `development-report.md` accurately marks US-001 complete at the store level, US-002/US-003 partial, US-004 partial, and US-005/US-006 not started. Concrete remaining gaps are:

- Coordinator heartbeat does not run independently during a long source request.
- Job execution is sequential and does not apply project or exact-host concurrency.
- Detailed probing does not consume `EffectivePolicy`; Retry-After and cache are not in the request path.
- Scheduled execution does not create the same durable job identity.
- Job list is not fully paginated/filterable and the UI lacks detail, cancel, retry, polling, stale, and focus workflows.
- Policy editor/preview is absent.
- Cache rows are not used by finding-producing scans.
- Finding evidence lacks policy/cache provenance.
- Expired ignore is not a read-only derived condition followed by one confirmed-evidence reopen.

These gaps can be completed in one pass because schema adapters and services already exist. No data-model replacement or frontend rewrite is necessary.

## Research Priorities

| Candidate | Research priority | Current maturity | Decision |
|---|---:|---|---|
| Job heartbeat and safe recovery | P0 | Store complete; coordinator incomplete | Selected |
| Cancellation/retry operations UI | P0 | Backend partial; UI absent | Selected |
| Scheduled/manual execution unification | P0/P1 dependency | Separate paths | Selected |
| Runtime policy enforcement | P0 | Persistence only | Selected |
| Observation-cache integration | P0 support | Adapter only | Selected |
| Ignore expiry and finding provenance | P0 trust | Missing | Selected |
| Issue-tracker handoff | P1 | Not started | Deferred |
| Schedule CRUD UI | P1 | Not started | Deferred |
| Secure sessions and RBAC delivery | P1 | Not started | Deferred |
| Global frontend/navigation rewrite | P2 | Not required | Deferred |
| Notification registry/delivery log | P2 | Not started | Deferred |
| Billing/portfolio reporting | P2 | Unvalidated | Deferred |

## Selected Scope for This Pass

### Feature A: Operational Scan Jobs

Complete the durable job service so one coordinator owns a job through a renewable lease while a bounded executor processes sources. A dedicated heartbeat loop renews every 5 seconds, including while requests are blocked. The coordinator stops writes immediately when ownership is lost. Project `max_concurrency` controls submitted sources and exact-host policy controls per-host active calls, with a hard global cap of 20.

Unify scheduled scans by creating one `SCHEDULED` job per schedule ID and due-slot key. Keep `ScheduledScanExecutor` source-compatible through an adapter that creates/waits for a job and returns its legacy `ScanResult` projection. Manual and retry jobs continue to use the same state machine.

Complete additive APIs for pagination, filters, expected versions, source pages, cancellation, and previewed failed-source retry. Complete the Scan Jobs interface with filters, adaptive polling, semantic progress, Job Detail dialog, source filters, cancellation confirmation, retry preview/create, parent/child navigation, stale-data recovery, mobile cards, and focus restoration.

### Feature B: Applied Noise Controls

Wire immutable policy snapshots into actual network behavior. Resolve exact-host policy for every target. Enforce timeout, maximum attempts, backoff, temporary statuses, numeric/HTTP-date Retry-After capped at 30 seconds, job concurrency, and host concurrency. All wait/request/clock dependencies remain injectable for deterministic tests.

Wire `ObservationCache` into detailed project scans after URL revalidation. Cache only successful/recovered and confirmed repeated 404/410 evidence, never transport-only, bot-blocked, unsafe, inconclusive, or first terminal observation. A hit creates new evidence referencing the cached source and marks `from_cache=true` without network I/O.

Persist policy version, fingerprint, rule, hostname, effective fields, and cache flag with finding evidence. Add derived `ignore_expired` without writes. The first later `CONFIRMED_BROKEN` observation atomically reopens an expired ignored finding once and audits the prior reason/expiry. Deliver a full Scan Policy dialog and a Policy Applied block in Finding Detail.

## Deferred Scope and Rationale

1. Issue-tracker integration: depends on stable job/finding events; future Repair Integrations phase.
2. Schedule CRUD and timezone UI: execution is unified here; administration remains a separate Monitoring Administration phase.
3. Secure browser sessions and RBAC: identity, cookies, CSRF, recovery, and deployment migration are cross-cutting; future Security Foundation.
4. Notification registry and delivery log: should consume finalized job/finding events; future Delivery Operations.
5. Global navigation and extracted frontend assets: not required for the bounded completion pass; future UX Scale-up.
6. Wildcard/regex/path policies: exact-host behavior remains deterministic and safer; future Advanced Noise Controls.
7. Authenticated targets and secret vault: no secret fields are added; future Authenticated Scanning.
8. External distributed queue: SQLite leases remain appropriate for the current single-deployment product.
9. Ad-hoc durable jobs: saved project identity remains required.
10. Finding comments, labels, due dates, and bulk actions: future Team Repair Workflow.
11. Agency portfolio and branded reports: depends on delivered organizations.
12. Hosted billing and quotas: requires commercial validation.

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

### PR-1: Continuous lease ownership and non-duplicating recovery

**Stories:** US-001.

**Research problem:** long scans must survive refresh/restart without repeating committed work.

**Behavior:** one coordinator claims a queued/expired job with worker ID and 30-second lease. A heartbeat thread renews every 5 seconds until terminal/cancel/lost lease. Source start and finish require current ownership. Recovery resets only orphaned RUNNING sources that lack committed result and completion timestamp.

**Inputs:** worker ID 1-128 printable characters; injected clock/sleeper; lease 30 seconds; heartbeat 5 seconds.

**Outputs:** job state/counts and derived `recoverable_at`; worker ID is never exposed by list API.

**Failure behavior:** stale owner receives `JobLeaseLost`, stops submitting sources, and cannot finalize. SQLite lock uses three retries at 25/50/100 ms, then emits sanitized `JOB_DB_BUSY`.

**Compatibility:** additive columns and fields; 1.4.0/1.4.1 databases migrate idempotently; current job IDs/states remain readable.

**Acceptance:** a 10-source restart fixture commits three sources, expires owner, recovers seven, and produces exactly ten calls and one terminal state; two workers claim once; heartbeat remains valid while a source blocks for 12 seconds; API create returns within 500 ms while execution blocks one second.

**Non-goals:** distributed consensus, external broker, forced thread termination.

### PR-2: Policy-aware parallel execution and cooperative cancellation

**Stories:** US-002 and US-004.

**Behavior:** a bounded executor submits at most project concurrency; a hostname semaphore limits active calls using exact-host policy. Cancellation is checked before submission, immediately before source start, and after completion. In-flight requests may finish within timeout; pending work becomes cancelled.

**Validation/business rules:** project concurrency 1-20; effective host concurrency is `min(host override, project concurrency)`; hard global request cap 20; no source starts after cancellation acknowledgement.

**Acceptance:** six same-host sources under project 4/host 2 observe at most two active calls; cancellation after three completed starts no fourth pending source; completed/in-flight results remain readable; terminal cancellation returns 409/current representation.

**Non-goals:** preemptive request termination, distributed rate limiter.

### PR-3: Scheduled-job identity and failed-source retry integrity

**Stories:** US-003.

**Behavior:** scheduled due work creates origin `SCHEDULED` job with idempotency key derived from schedule ID and canonical due timestamp. Retry preview recomputes active-project membership and URL safety; child uses current policy and only eligible FAILED sources.

**Acceptance:** two workers for one due slot produce one job ID; legacy scheduler result projection remains equal for counts/status; two failed sources produce two-source child; removed source is excluded; all unsafe sources produce no job and zero network requests.

**Non-goals:** schedule CRUD UI, arbitrary retry selection, automatic recursive retries.

### PR-4: Effective request policy and safe observation cache

**Stories:** US-004 and US-006.

**Behavior:** `scan_link_detailed` accepts optional `EffectivePolicy` without breaking legacy callers. Attempts obey max attempts, timeout, backoff, retryable temporary statuses, and Retry-After. Cache lookup occurs only after URL security validation; cache hit emits new observation with provenance.

**Rules:** TTL 0 disables; max 86400; eligible classes RECOVERED and CONFIRMED_BROKEN only; confirmed 404/410 requires repeated evidence; max 50,000 rows; project/fingerprint isolation; expired cleanup on writes.

**Acceptance:** repeated 503 with max attempts 3 makes exactly three calls; 429 Retry-After then 200 is non-actionable; eligible hit makes zero calls; expired/different project/fingerprint misses; transient/unsafe never caches; wait cap is 30 seconds.

**Non-goals:** body cache, distributed cache, user-editable scripts.

### PR-5: Expired ignore with one confirmed-evidence reopen

**Stories:** US-005.

**Behavior:** list/detail calculate `ignore_expired=true` without writes. Fresh confirmed evidence atomically changes IGNORED to OPEN, clears active ignore fields, increments version once, and records `IGNORE_EXPIRED_REOPENED` with prior metadata.

**Validation:** reason 1-500 trimmed characters; expiry ISO date not before local submission date; expected version required.

**Acceptance:** listing expired ignored finding changes no row/version; first confirmed recurrence reopens/audits once; concurrent second recurrence creates no duplicate event; transient/recovered/inconclusive evidence preserves ignored state; invalid reason makes no mutation.

**Non-goals:** pattern suppression, deletion, project-wide ignore.

### PR-6: Operations UI and explainable evidence

**Stories:** US-001 through US-006.

**Behavior:** complete Jobs workspace, Job Detail dialog, Scan Policy dialog, and Finding Policy Applied block. All mutations use current expected version. Dynamic data uses textContent or existing escape helper.

**Acceptance:** DOM tests cover all specified states; browser flow can queue, observe, cancel/retry, save/preview policy, and inspect provenance; focus returns correctly; progress has accessible name/text; copied summary contains no secret sentinel; mobile/zoom has no page-level horizontal scrolling.

**Non-goals:** frontend framework, global navigation, redesign of unrelated analytics.

## UI and UX Specification

### Personas and journeys

Primary persona: site administrator monitoring recurring saved projects. Secondary persona: SEO/content operator reducing false positives and reviewing trusted evidence.

Primary flow: Saved Projects -> Run project scan -> Scan Jobs -> View job -> observe/cancel/retry -> Trusted Finding -> Policy Applied. Policy flow: Saved Project -> Edit scan policy -> add exact host -> Preview effective policy -> Save policy -> run job -> inspect provenance.

### Information architecture and design system

Retain the existing single dashboard: Header, Saved Projects, Scan Jobs, Trusted Findings, Ad-hoc Scans, Recent Pages, Analytics. Retain vanilla JS and CSS properties. Tokens: spacing 4/8/12/16/24/32 px; body 16 px/1.5; dense text 14 px/1.45; radii 6/10 px; focus ring 2 px plus 2 px offset and >=3:1 contrast; normal text >=4.5:1; controls 44x44 px where primary; reduce transitions/smooth scroll under reduced motion. State text is always visible, never color-only.

## Screen Inventory and User Flows

### Screen 1: Saved Project card

Blocks: name/pin/health header; policy summary `Scan policy vN · X exact-host overrides`; action row with primary `Run project scan`, secondary `Edit scan policy`, then existing actions. During creation, card is busy and label becomes `Queuing scan…`. Success announces `Scan queued as JOB-XXXXXXXX` and focuses matching Jobs card. Validation lists rejected sources and offers Edit project. Storage error states no job was created and preserves controls.

### Screen 2: Scan Jobs workspace

Header: title, explanation, Project filter, State filter, `Refresh jobs`. Body loads three inert skeleton cards. Empty state says `No project scans yet` with `Run a saved project`. Cards show project, origin, state, short ID, created time, native progress, textual counts, policy version, parent link, and `View job`. Active cards expose `Cancel scan`; partial/failed expose `Retry failed sources`.

Poll every 2 seconds while visible nonterminal jobs exist, otherwise 10 seconds. Pause when page hidden and refresh on visibility return. After two failures retain cards, show `Updates paused`, and offer `Resume updates`. Polling must not replace the focused card or announce routine count changes.

### Screen 3: Job Detail dialog

Native dialog with project/state heading, full job ID and `Copy job ID`, Close, progress summary, timestamps, origin, policy version, parent/child links. Source tabs: All, Running/Pending, Failed, Completed, Cancelled. Source row/card shows URL, state, attempt count, sanitized reason, start/completion.

Cancel click opens confirmation naming remaining count. Confirm sets Cancelling and disables only conflicting actions. Close remains available. Retry click first loads preview with eligible/excluded/invalid lists. `Create retry job` is disabled if none eligible. Success creates child, updates parent link, and focuses child card. 409 refreshes detail and says another session changed the job.

### Screen 4: Scan Policy dialog

Header names project/version. Defaults fields: timeout, project concurrency, max attempts, backoff, respect Retry-After, cache TTL, temporary statuses. Exact-host section lists sorted override cards with Edit/Remove and `Add exact-host override`; helper says subdomains do not inherit. Preview accepts URL and returns source rule, all effective values, fingerprint prefix, and cache enabled state. Footer: `Save policy`, `Reset to built-in defaults`, `Cancel`.

Loading uses form skeleton. Validation summary gets focus and links to fields. Conflict retains local draft and offers `Reload server version` or `Reapply my draft`. Success announces version and updates project card without closing.

### Screen 5: Finding Detail Policy Applied

Above Probe Evidence show version, rule, hostname, timeout, attempts, cache source, fingerprint prefix, and observed time. `Copy evidence summary` copies sanitized loaded values. Legacy evidence says provenance unavailable. Active ignore shows reason/expiry; expired ignore says exactly `Expired, awaiting fresh confirmed evidence`; recurrence adds audit event and Open state.

### Responsive/accessibility

Desktop >=1024 px uses two-column jobs and policy fields; tablet 640-1023 px one-column jobs/two-column fields; mobile <640 px stacks controls and uses full-width-minus-16 px dialogs and card representations. At 320 CSS px/200% zoom no page-level horizontal scroll. Use labelled sections, ordered job list, articles/headings, labelled progress, explicit labels/errors, native dialogs, captions/definition lists, live regions, safe links, initial focus, Escape rules, and trigger focus restoration.

### Success and recovery flows

Success: queue 10-source project, reload, see preserved progress, open partial job, retry one failure, open child, inspect finding policy provenance. Recovery: source blocks while heartbeat renews; process stops; lease expires; new coordinator recovers only uncommitted source; UI retains counts and reaches terminal. Policy conflict retains draft and requires explicit reapply.

### UI verification

Start server with temporary paths and local fixture. If Playwright/Chromium is available, capture temporary screenshots at 1440x900, 768x1024, and 390x844 for Jobs empty/running/partial, retry preview, policy validation/success, and expired-ignore detail. Run keyboard-only, 200% zoom/reflow, reduced motion, contrast, and one screen-reader smoke. Exclude screenshots from package. If graphical tooling is unavailable, report blocked and do not claim visual inspection; DOM and JS syntax tests remain mandatory.

## Architecture and Technical Design

### Components

- `scan_jobs.py`: schema migration, state machine, owner/version predicates, heartbeat, recovery, pagination, atomic finalize.
- `job_service.py`: heartbeat lifecycle, bounded executor, host semaphores, cancellation barrier, schedule adapter, policy/cache/finding orchestration.
- `scan_policy.py`: immutable policy parsing/resolution/fingerprint and preview.
- `observation_cache.py`: eligibility, expiry, cleanup, source-observation reference.
- `package.py`: policy-aware detailed probing with injected requester/clock/sleeper.
- `scheduled_scan.py`: compatibility adapter to JobService.
- `findings.py`/`finding_service.py`: provenance persistence and atomic ignore recurrence.
- `app.py`: authenticated APIs, coordinator lifecycle, complete dashboard behavior.

### Data flow

Create job -> validate project/sources -> snapshot full policy -> commit job/sources/idempotency -> 202 -> lease claim -> heartbeat -> bounded source submission -> target validation -> effective policy -> cache lookup -> detailed probe on miss -> eligible cache write -> finding/history with provenance -> owner-checked source commit -> cancel barrier/finalize -> UI polling.

### Persistence

Retain existing lease/snapshot/cache tables. Add cache `source_observation_id` and cap cleanup. Add evidence columns `policy_version`, `policy_rule`, `policy_hostname`, `policy_fingerprint`, `effective_policy_json`, `from_cache`, `cached_observation_id`. Add derived ignore expiry in serialization, no schema field needed. All migrations are transactional/idempotent and preserve null legacy provenance.

### Errors/logging

Stable new codes: `JOB_LEASE_LOST`, `JOB_DB_BUSY`, `JOB_VERSION_CONFLICT`, `POLICY_VERSION_CONFLICT`, `POLICY_INVALID`, `NO_RETRYABLE_SOURCES`. Structured logs include safe IDs/counts/hostname/version/latency, never tokens, keys, headers, cookies, bodies, context, or raw exceptions.

### Dependencies and alternatives

No runtime dependency changes. Redis/Celery, wildcard policy, forced thread cancellation, mutable policy, and frontend rewrite are rejected for scope/operational risk. SQLite with explicit leases remains the evidence-to-risk best fit.

## Data, API, and Compatibility Changes

Complete these additive contracts:

- `POST /api/projects/{project_id}/jobs`, optional `Idempotency-Key`, body `{"render_js":false}`, response 202.
- `GET /api/jobs?project_id=&state=RUNNING,FAILED&limit=20&offset=0&updated_after=`.
- `GET /api/jobs/{id}` and `/sources?state=&limit=100&offset=0`.
- `POST /api/jobs/{id}/cancel` body `{"version":N}`.
- `POST /api/jobs/{id}/retry-failures` body `{"version":N,"preview":true|false}`.
- `GET/PUT /api/projects/{id}/scan-policy`.
- `POST /api/projects/{id}/scan-policy/preview` body containing URL and optional draft.

Do not expose worker ID. Detail may expose derived `recoverable_at`. Finding evidence adds nullable provenance/cache fields. Existing `/scan`, `/scan-batch`, exports, project portable schema v1, CLI, notifications, and findings actions remain compatible. Duplicate/import starts with policy v0/no jobs. Archive preserves reads and blocks mutations.

## Security and Privacy Considerations

Revalidate all stored URLs before request and cache lookup. Revalidate redirects. Exact host uses parsed IDNA equality. Bound all request, retry, wait, concurrency, cache, pagination, and JSON limits. Cache no bodies/headers/cookies/credentials/raw exceptions. Scope cache to project/fingerprint. Hash idempotency keys. Require existing authentication and expected versions for mutations. Render untrusted text through textContent/escape helper. Test host confusion, private IPv4/IPv6, unsafe redirects, stored unsafe sources, cache bypass, and secret sentinels.

## Test Strategy (TDD)

RED-first story tests:

- `tests/test_us_001_job_operations.py`: heartbeat during blocked call, restart nonduplication, claim race, async response.
- `tests/test_us_002_cancellation_concurrency.py`: project/host maxima, cancellation barriers, terminal conflicts.
- `tests/test_us_003_schedule_retry.py`: due-slot idempotency, adapter compatibility, retry exactness and unsafe zero-I/O.
- `tests/test_us_004_applied_policy_cache.py`: attempts, backoff, Retry-After, eligibility, expiry/isolation.
- `tests/test_us_005_ignore_expiry.py`: no-write derived expiry, one confirmed reopen, concurrent recurrence, nonconfirmed cases.
- `tests/test_us_006_provenance_ui.py`: DB/API/DOM/copy provenance and sentinel redaction.
- `tests/test_jobs_api.py`, `test_jobs_ui.py`, `test_policy_api.py`, `test_policy_ui.py` for contracts/states.

Use real temporary SQLite and local HTTP fixture for delayed 200, repeated 503, 429-then-200, timeout, repeated 404, and restart. No public network.

Targeted commands:

```bash
python -m pytest -q tests/test_us_001_job_operations.py tests/test_us_002_cancellation_concurrency.py tests/test_us_003_schedule_retry.py tests/test_jobs_api.py tests/test_jobs_ui.py
python -m pytest -q tests/test_us_004_applied_policy_cache.py tests/test_us_005_ignore_expiry.py tests/test_us_006_provenance_ui.py tests/test_policy_api.py tests/test_policy_ui.py
python -m pytest -q tests/test_scheduled_scan.py tests/test_trusted_findings.py tests/test_ssrf_enhanced.py tests/test_dashboard_javascript.py
```

Full checks:

```bash
python -m pytest -q --disable-warnings
ruff check src tests
python -m compileall -q src tests
python -m pip wheel . --no-deps -w dist-test
```

Remove build output after isolated import smoke. Type-check remains “not configured.” Measure >=90% statement coverage on changed/new job, policy, cache, probe, and finding modules using official lab coverage tooling; unavailable plugin blocks coverage acceptance.

Mandatory official gates:

```bash
tdd-gate-v3.sh
bdd-gate.sh
security-gate.sh
doc-sync-check.sh
ui-gate.sh
bash ~/.hermes/scripts/git-push-verify.sh <repo_path>
```

Missing commands/Git remote block completion; never add fake pass-through scripts.

## Documentation Deliverables

- README: complete job/policy user flows, configuration, bounds, recovery, cache, provenance, troubleshooting.
- CHANGELOG: actual release/date/features/fixes/tests/docs/gates.
- `docs/scan-jobs.md`: state machine, leases, polling APIs, schedule identity, cancellation/retry.
- `docs/scan-policies.md`: effective fields, precedence, Retry-After, cache, preview.
- `docs/findings.md`: ignore expiry and provenance fields.
- FEATURES-DONE: only fully delivered stories/requirements with actual evidence.
- development-report: RED/GREEN, counts, coverage, gates, UI screenshots/checks, Git/push, integrity, traceability.

## Expected File Changes

Expected modifications: `scan_jobs.py`, `job_service.py`, `scan_policy.py`, `observation_cache.py`, `package.py`, `scheduled_scan.py`, `findings.py`, `finding_service.py`, `app.py`, relevant existing tests, README, CHANGELOG, three docs, FEATURES-DONE, development-report, and synchronized version files.

Expected additions: six story-focused tests plus job/policy API/UI tests if not already present. No deployment, governance, webhook, CI-gate, SPA internals, or portable-project-schema changes.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Survive restart | P0 durable jobs | US-001 | PR-1 | exactly 10 calls after 3+7 recovery | scan_jobs.py/job_service.py | test_us_001_job_operations.py | P0 |
| Async durable start | monitoring operations | US-001 | PR-1 | 202 under 500 ms while blocked | app.py/service | API integration | P0 |
| Stop obsolete work | long-scan control | US-002 | PR-2 | no source starts after acknowledgement | service/store/UI | test_us_002_cancellation_concurrency.py | P0 |
| Host-aware limits | 429/timeout evidence | US-002 | PR-2 | max two active same-host calls | policy/service | concurrency fixture | P0 |
| Retry only failures | verification/quota demand | US-003 | PR-3 | child contains exact eligible failures | service/API/UI | test_us_003_schedule_retry.py | P0 |
| One scheduled identity | recurring monitoring | US-003 | PR-3 | duplicate due slot yields one job | scheduled_scan.py | schedule race test | P0 |
| Policy changes behavior | false-positive evidence | US-004 | PR-4 | exactly three 503 attempts; 429->200 nonactionable | package.py/policy.py | test_us_004_applied_policy_cache.py | P0 |
| Safe cache | repeated-check demand | US-004 | PR-4 | hit zero calls; unsafe/transient never cached | observation_cache.py | cache tests | P0 |
| Expiring exceptions | noise-control demand | US-005 | PR-5 | no-write expiry; confirmed reopen once | findings/service | test_us_005_ignore_expiry.py | P0 |
| Weak evidence stays ignored | trustworthy findings | US-005 | PR-5 | transient/recovered no version change | finding service | parameterized tests | P0 |
| Explain classification | evidence differentiator | US-006 | PR-6 | DB/API/UI policy provenance | findings/app | test_us_006_provenance_ui.py | P0 |
| No secret leakage | security constraint | US-006 | PR-6 | sentinel absent DB/API/UI/copy/log | sanitizer/store/UI | end-to-end sentinel test | P0 |

## Risks and Mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| Lease race duplicates work | duplicate alerts/requests | owner/version predicates and race tests |
| SQLite contention | failed writes | WAL, short transactions, bounded retry |
| Cooperative cancel delay | user uncertainty | strict timeout and honest Cancelling state |
| Over-tuned policy | hidden failures | conservative bounds, exact-host only, provenance |
| Stale cache | missed regression | TTL off by default and narrow eligibility |
| Retry-After stalls slots | low throughput | 30-second cap and injected fairness tests |
| Schedule adapter regression | broken automation | legacy projection and existing tests |
| Embedded JS complexity | UI regression | modular functions, DOM tests, Node/browser checks |
| Legacy evidence missing fields | confusion | explicit legacy label and nullable fields |
| Missing lab/Git tooling | uncertified delivery | block completion and report truthfully |

## Definition of Done

- [ ] PR-1 through PR-6 complete without stubs or hidden nonfunctional controls.
- [ ] US-001 through US-006 pass every embedded happy, edge, and error criterion.
- [ ] Heartbeat, recovery, stale-owner rejection, atomic completion, and nonduplication proven with real SQLite/I/O.
- [ ] Manual and scheduled scans use one job identity/path.
- [ ] Cancellation/retry work through complete UI.
- [ ] Policy governs timeout, concurrency, attempts, backoff, Retry-After, and cache.
- [ ] Ignore expiry and finding provenance are complete and audited.
- [ ] Existing contracts remain green.
- [ ] Targeted/full/integration/security/UI/accessibility tests pass.
- [ ] Changed modules meet >=90% measured coverage.
- [ ] Ruff, compile, wheel/import, startup, JS, and applicable E2E pass.
- [ ] UI screenshots/checks are recorded when tooling permits; unavailable tooling is blocked, not passed.
- [ ] Official TDD, BDD, security, doc-sync, and UI gates pass.
- [ ] Documentation and audit files match actual behavior/counts.
- [ ] No secrets or stray artifacts packaged.
- [ ] Git commit/push and official verification pass; missing Git/remote blocks completion.
- [ ] Every requirement/story maps to implementation and named tests.
- [ ] Complete project ZIP passes integrity, listing, extraction, required-file, and layout verification.
