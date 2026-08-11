# Implementation Plan

## Executive Summary

This pass is a focused **Reliable Monitoring Operations Completion** pass. It does not add a new product direction. It completes and hardens the two research-validated P0 features that the preceding development report marks partial: **durable scan-job reliability and operations UX** (US-001 through US-003) and **executable noise-control policy with finding provenance** (US-004 through US-006).

The current tree contains useful foundations but does not yet satisfy the approved behavior contract. Jobs persist and support basic cancellation/retry, but there is no durable lease heartbeat or recovery, no complete job detail/cancel/retry UI, no adaptive polling, and no scheduled-executor unification. Policies persist and resolve exact-host overrides, but they do not control request attempts, concurrency, backoff, Retry-After, or cache behavior; policy provenance does not reach findings; and expiry-only ignore behavior is not implemented to the required fresh-evidence rule. The plan therefore chooses completion over expansion.

The pass will deliver two complete integrated features:

1. **Recoverable scan jobs and complete Jobs workspace.** Add lease ownership, heartbeat, expired-lease recovery, atomic source completion, schedule-to-job execution, paginated APIs, adaptive dashboard polling, job detail, cancellation, retry preview/create, and all specified UI states.
2. **Applied scan policies and evidence provenance.** Make project/exact-host policy values govern detailed probing and job execution; add bounded cache behavior; persist immutable effective-policy snapshots on observations; expose provenance in finding detail; and implement ignore expiry that reopens only on fresh confirmed evidence.

No new runtime dependency is required. The existing standard-library HTTP server, SQLite database, vanilla JavaScript dashboard, optional Playwright integration, and current scanner/finding services remain the architecture. Existing synchronous ad-hoc APIs and export formats remain backward compatible.

## Current-State Validation

The research report remains aligned with the actual product and its recommendations are actionable. The supplied project is BrokenLinkBrief 1.4.0 and contains 107 files. Its current implementation includes:

- `src/brokenlinkbrief/scan_jobs.py`: job/source/idempotency tables, queued claim, source completion, basic finalization, queued/running cancel, and source listing.
- `src/brokenlinkbrief/job_service.py`: saved-project job creation, target revalidation, process-local worker loop, sequential source execution, cancellation boundary, and failed-source retry preview/create.
- `src/brokenlinkbrief/scan_policy.py`: bounded policy model, immutable versions, exact-host normalization, host-override precedence, and policy fingerprint.
- `src/brokenlinkbrief/app.py`: additive jobs and policy APIs plus a basic Scan Jobs dashboard list.
- BDD-tagged tests for US-001 through US-004. The preceding report records 846 passed, 45 skipped, and one xpass, but explicitly marks US-001 and US-004 partial and US-005/US-006 incomplete.

Material gaps verified from source and report:

- `scan_jobs.py` has no `worker_id`, `lease_expires_at`, or `heartbeat_at` fields and no recovery transaction.
- A claimed job is simply changed to `RUNNING`; a crash can leave it permanently stuck.
- Source transition methods do not enforce ownership, expected state, or optimistic version checks; finalization can race.
- `job_service.py` runs sources sequentially and ignores effective policy concurrency, attempts, backoff, Retry-After, and cache.
- Schedule execution still has a separate orchestration path and does not create deterministic durable job records.
- Jobs UI lacks project/state filters, automatic polling, job-detail dialog, cancel confirmation, retry preview/create, stale-data handling, and focus restoration.
- Policy UI is absent.
- Policy snapshots are retained only as job version numbers, not as canonical effective values on evidence.
- `FindingStore` does not implement the planned “expired, awaiting fresh evidence” contract with a single audited reopen on confirmed recurrence.
- Official lab gate scripts, Git metadata, Ruff, coverage plugin, pip, and graphical browser tooling were unavailable in the last phase. This plan treats official gate availability and push verification as external completion criteria, not product features and not permission to create fake scripts.

The selected scope is achievable in one pass because the foundational tables, APIs, scanner, project store, finding service, dashboard patterns, and tests already exist. It requires completion and refactoring, not a framework rewrite.

## Research Priorities

| Candidate | Research rank | Current state | Value/risk assessment | Decision |
|---|---:|---|---|---|
| Recoverable durable jobs | P0 | Partial | Highest reliability value; existing foundation lowers risk | Selected |
| Complete job cancellation/retry UX | P0 | Partial backend, thin UI | Required to make durable jobs sellable and operable | Selected |
| Executable project/host policy | P0 | Persistence only | Directly addresses timeout/429 false positives | Selected |
| Ignore expiry on fresh evidence | P0 within noise controls | Not implemented | Small, high-trust lifecycle completion | Selected |
| Finding policy provenance | P0 within explainability | Missing | Necessary to audit and tune policies safely | Selected |
| Issue-tracker handoff | P1 | Not started | Valuable but depends on stable job/finding events | Deferred |
| Schedule administration UI | P1 | Service/config only | Job execution unification selected; CRUD UI deferred | Deferred |
| Secure browser sessions/RBAC | P1 | Not delivered | Cross-cutting identity/CSRF migration | Deferred |
| Global navigation/frontend extraction | P2 | Not started | Avoids unrelated rewrite during reliability completion | Deferred |
| Integration delivery log | P2 | Not started | Requires stable event model and secret references | Deferred |
| Portfolio reporting/billing | P2 | Not started | Requires hosted and organization validation | Deferred |

## Selected Scope for This Pass

### Feature 1: Recoverable Durable Jobs and Complete Jobs Workspace

Complete the job state machine and worker contract. Add lease fields and an atomic claim/recovery protocol. Each running job has one worker owner, a 30-second lease, and a heartbeat at least every 5 seconds while active. Startup and periodic recovery requeue an expired job with pending/running sources; any source left `RUNNING` without an atomically committed result returns to `PENDING`. Completed/failed/cancelled source rows never return to pending. A recovered job retains the same job ID and does not repeat committed source work.

Source execution uses a bounded executor. The project default `max_concurrency` sets the job-wide limit, and exact-host policy sets a per-host limit. Cancellation remains cooperative: no source begins after `CANCEL_REQUESTED` is observed, in-flight work may finish within timeout, and remaining pending sources become cancelled. Finalization is one transactional compare-and-set operation and terminal states are immutable.

Scheduled scans create the same job type with origin `SCHEDULED` and deterministic idempotency key derived from schedule ID plus due slot. `ScheduledScanExecutor` remains source-compatible through an adapter that creates/waits for a job and converts the terminal job representation to the legacy result object.

Complete the Jobs workspace: filters, automatic polling, empty/loading/stale/error/success states, semantic job cards, detail dialog, source filters, cancel confirmation, retry preview/create, parent/child navigation, focus restoration, and responsive mobile cards.

### Feature 2: Executable Noise-Control Policies and Finding Provenance

Apply the existing versioned policy model to actual network behavior. At job creation, snapshot the complete canonical policy document, not only its version number. For each discovered target, resolve an effective exact-host policy and pass an immutable `EffectivePolicy` to the detailed probe. The probe enforces timeout, maximum attempts, backoff, Retry-After cap, temporary statuses, and injects clock/sleeper/requester for deterministic tests. Job coordination enforces project and per-host concurrency.

Add a project-scoped observation cache keyed by normalized target URL and effective-policy fingerprint. Default TTL remains zero. Eligible cached values are successful outcomes and terminal repeated 404/410 evidence only. Transport failures, unsafe targets, bot-blocked, inconclusive, and single-attempt terminal failures are never cached. Cache is never shared across projects and expired entries are removed opportunistically.

Every persisted finding evidence group records policy version, policy fingerprint, rule type, exact hostname, effective values, and whether evidence came from cache. Finding detail exposes these fields. The dashboard adds a complete Scan Policy dialog and a Policy Applied block in finding details. Copy Evidence Summary uses already-sanitized loaded data.

Complete ignore semantics: expiry alone is read-only and displays “Expired, awaiting fresh confirmed evidence.” The first later `CONFIRMED_BROKEN` observation atomically reopens the finding once, clears active ignore fields but retains prior reason/expiry in audit metadata, increments the version once, and records `IGNORE_EXPIRED_REOPENED`. Non-confirmed evidence does not reopen.

## Deferred Scope and Rationale

1. **Issue-tracker integration:** stable job/finding event IDs are a prerequisite. Future phase: Repair Integrations.
2. **Schedule management screens:** this pass unifies execution only; CRUD, timezone preview, pause/resume, and DST UI remain a separate Monitoring Administration phase.
3. **Secure sessions and delivered RBAC:** requires identity, cookies, CSRF, expiration, recovery, and deployment migration. Future phase: Security Foundation.
4. **Notification registry and delivery log:** should consume stable terminal job/finding events. Future phase: Delivery Operations.
5. **Global navigation and extracted frontend bundle:** unrelated to finishing the selected workflows. Future phase: UX Scale-up.
6. **Wildcard, regex, or path policy rules:** exact-host rules remain deliberately deterministic. Future phase: Advanced Noise Controls.
7. **Authenticated targets and secret storage:** policy continues to contain no secrets. Future phase: Authenticated Scanning.
8. **Distributed external queue:** SQLite leasing remains the selected single-deployment design. Future phase only if telemetry demonstrates multi-node need.
9. **Ad-hoc durable jobs:** saved projects remain required for durable identity. Future phase: Job Generalization.
10. **Finding comments, labels, due dates, and bulk changes:** unrelated to reliability completion. Future phase: Team Repair Workflow.
11. **Portfolio reporting and white-label exports:** requires organization delivery. Future phase: Agency Operations.
12. **Hosted billing and quotas:** requires hosted demand validation and infrastructure economics. Future phase: Commercialization.

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

### PR-1: Lease-owned execution and restart recovery

**Evidence and stories:** research P0 durable jobs; US-001.

**Behavior:** extend job schema with `worker_id`, `lease_expires_at`, and `heartbeat_at`; atomically claim one queued or expired job; heartbeat every 5 seconds; lease duration 30 seconds; recover expired jobs and orphaned running sources; commit each source result and job counts transactionally.

**Inputs:** worker ID 1-128 printable characters, injected UTC clock, lease duration 30 seconds, heartbeat interval 5 seconds.

**Outputs:** existing job representation plus worker/lease timestamps only for authenticated detail APIs; list API omits worker ID.

**Rules:** one active lease per job; only current owner may start/finish a source; completed sources are immutable; recovering a source is allowed only if state is RUNNING and no result/terminal timestamp exists; terminal jobs are never recovered.

**Failures:** a lost lease causes the old worker's next write to return `JobLeaseLost`; the coordinator stops processing that job. Database lock retries use three bounded attempts with 25/50/100 ms injected backoff, then sanitized failure logging.

**Compatibility:** additive columns and fields; migration is idempotent; older 1.4.0 databases open without reset; current job IDs/states remain valid.

**Acceptance:** restart test commits 3 of 10 sources, expires the lease, opens a new store/coordinator, completes exactly 7 more sources, and ends with one terminal state; two concurrent workers claim one job only once; stale owner cannot commit; API create returns in under 500 ms while scanner blocks at least one second.

**Non-goals:** distributed consensus, external broker, process termination of in-flight requests.

### PR-2: Policy-aware bounded execution and cancellation

**Evidence and stories:** timeout/429 demand and controllable long scans; US-002 and US-004.

**Behavior:** a bounded executor enforces project concurrency; per-host semaphores enforce exact-host concurrency. Detailed probes enforce attempts, timeout, backoff, Retry-After cap, and retryable statuses. Cancellation is checked before queue submission, before source start, and after source completion.

**Rules:** total global requests never exceed 20; project concurrency 1-20; host override cannot exceed project concurrency in effective execution; `Retry-After` waits at most 30 seconds; no real sleeps in unit tests; a cancel request starts zero new sources after acknowledgement.

**Acceptance:** six-source fixture with project concurrency 4 and host override 2 observes maximum 2 active calls to that host; max attempts 3 performs exactly three under repeated 503; 429 then 200 remains non-actionable; running cancellation preserves completed/in-flight results and cancels all pending sources.

**Non-goals:** adaptive machine-learning throttling, cross-process global rate limiter, force-killing request threads.

### PR-3: Retry-failure integrity and scheduled-job unification

**Evidence and stories:** repeat verification without redoing success; US-003.

**Behavior:** retry preview validates current project membership and URL policy; child job contains only eligible failed sources and snapshots current policy. Scheduled due work creates jobs using deterministic idempotency keys and the same worker path.

**Rules:** one schedule/due-slot produces at most one job; retry parent must be failed/partial; successful/cancelled sources are never copied; archived projects permit read-only job inspection but no retry/new scheduled job.

**Acceptance:** two failed sources create exactly a two-source child; removed source is excluded; all unsafe sources create no job/outbound request; two schedule workers processing the same due slot yield one job ID; existing `ScheduledScanExecutor` tests remain compatible.

**Non-goals:** arbitrary source selection, automatic infinite retry chains, schedule CRUD UI.

### PR-4: Observation cache and immutable policy snapshot

**Evidence and stories:** reducing repeated requests and false positives; US-004.

**Behavior:** persist the full job policy snapshot and per-observation effective policy. Cache eligible observations by project, URL, fingerprint, and expiry. A cache hit creates a new evidence observation that references the cached observation ID and marks `from_cache=true` without another network request.

**Rules:** TTL zero disables cache; maximum 86400 seconds; cache only successful or confirmed terminal 404/410 evidence; invalidate naturally through fingerprint/key changes; never share across projects; cap stored rows to 50,000 with oldest-expired cleanup first.

**Acceptance:** eligible hit within TTL makes zero requester calls and preserves classification; expired hit makes a request; different project/fingerprint misses; transport-only evidence never enters cache; unsafe URL is revalidated even on lookup and cannot be served from cache.

**Non-goals:** distributed cache, content-body cache, manual cache UI.

### PR-5: Ignore expiry on fresh confirmed recurrence

**Evidence and stories:** expected exceptions without permanently hiding risk; US-005.

**Behavior:** list/detail are read-only for expired ignores and expose derived `ignore_expired=true`. Fresh confirmed observation executes one atomic reopen/audit transition. UI uses exact label “Expired, awaiting fresh confirmed evidence.”

**Rules:** blank/over-500 reason rejected; expiry before current local date rejected on submission; non-confirmed evidence leaves state/version unchanged; concurrent confirmed observations create one reopen audit event.

**Acceptance:** valid ignore writes one audit event; expiry/list causes no write; first confirmed recurrence changes IGNORED to OPEN, increments once, clears active fields, and preserves old metadata in audit; second concurrent recurrence does not duplicate event; transient/recovered evidence does not reopen.

**Non-goals:** pattern-based suppression, deletion, project-wide ignore.

### PR-6: Policy provenance and complete operations UI

**Evidence and stories:** users must understand classifications and operate jobs; US-001 through US-006.

**Behavior:** additive finding detail fields expose policy version/fingerprint/rule/hostname/effective fields/cache flag. Dashboard implements Jobs workspace, Job Detail dialog, Scan Policy dialog, and finding Policy Applied block.

**Validation:** all dynamic data rendered with text content/escape helper; expected versions required for mutations; policy form uses existing server bounds; conflict reload retains local draft for manual reapply.

**Acceptance:** every screen/state in the UI specification is represented by DOM-level tests; live startup flow creates a job, observes progress, cancels or retries, saves versioned policy, and displays provenance; keyboard focus and announcements follow specified behavior; secret sentinel absent from database, API, HTML, copied summary, and logs.

**Non-goals:** frontend framework, global navigation, visual redesign of unrelated dashboard sections.

## UI and UX Specification

### Personas and primary journey

Primary persona: site administrator running recurring saved-project scans. Secondary persona: SEO/content operator tuning noisy hosts and reviewing trusted findings.

Primary journey: **Saved Project -> Run project scan -> Scan Jobs -> Job Detail -> observe progress -> cancel or retry failures -> Trusted Finding -> Policy Applied evidence.** Policy journey: **Saved Project -> Edit scan policy -> change exact-host rule -> preview -> save -> run job -> inspect applied version.**

### Information architecture

Preserve the single-page dashboard and existing section order, with these final positions:

1. Header and product status.
2. Saved Projects.
3. Scan Jobs.
4. Trusted Findings.
5. Ad-hoc Scan Pages.
6. Recent Pages.
7. Historical Analytics.

No new global navigation or framework is introduced. Project cards are the entry point for jobs and policies.

### Design system

Retain existing semantic HTML, dark surfaces, CSS custom properties, and vanilla JavaScript. Add no frontend dependency. Use spacing 4/8/12/16/24/32 px; body 16 px at 1.5 line height; dense metadata 14 px; cards 10 px radius; controls 6 px radius; normal text contrast 4.5:1; UI boundaries/focus 3:1; visible 2 px focus ring with 2 px offset; primary touch targets 44x44 px; color never carries state alone. Disable transitions and smooth scroll under reduced motion.

### Screen states and behavior

Every asynchronous region independently supports loading skeleton, empty guidance, disabled action reason, validation errors, recoverable server error, stale-data state, success announcement, and conflict refresh. Polling updates do not replace focused nodes or announce every count change.

## Screen Inventory and User Flows

### Screen 1: Saved Project card enhancements

Header retains project name, pin, and health summary. Add policy line `Scan policy vN · X exact-host overrides`. Primary action remains `Run project scan`. Secondary action `Edit scan policy` follows it. On create, button becomes `Queuing scan…`, disabled, and card sets `aria-busy=true`. Success announces job short ID and moves focus to its Jobs card. Validation error lists each rejected project source and offers existing Edit project. Storage error says no job was created and preserves actions.

### Screen 2: Scan Jobs workspace

Header contains `Scan Jobs`, project selector, state selector, and `Refresh jobs`. Default query shows all nonterminal jobs plus 20 newest terminal jobs. Loading shows three inert skeleton cards. Empty state says `No project scans yet` and `Run a saved project` focuses Saved Projects. Stale state appears after two poll failures, retains cards, and offers Resume updates.

Cards show project, origin, state text, created time, short ID, native progress, completed/failed/cancelled/pending counts, policy version, parent link, and `View job`. `Cancel scan` appears for queued/running states. `Retry failed sources` appears only for failed/partial terminal states. Poll every 2 seconds while any visible job is nonterminal and every 10 seconds otherwise; pause when document hidden; refresh immediately on visibility return.

### Screen 3: Job Detail dialog

Native dialog header contains project, state, full job ID with Copy, and Close. Summary contains timestamps, origin, policy version, parent/child links, and textual/native progress. Source filter tabs: All, Running/Pending, Failed, Completed, Cancelled. Rows/cards show source URL, state, attempts, sanitized reason, start/completion time.

Cancel flow: View job -> Cancel scan -> confirmation names remaining count -> Confirm cancellation -> state becomes Cancelling -> pending sources become Cancelled -> completion announcement. Close remains enabled. Conflict refreshes detail and explains the state changed.

Retry flow: View partial job -> Retry failed sources -> preview lists eligible, excluded, invalid -> Create retry job -> child card appears and focus moves to child heading. If zero eligible, creation is disabled and reasons remain visible.

### Screen 4: Scan Policy dialog

Header: `Scan policy for [project name]`, active version, Close. Defaults block contains timeout, concurrency, attempts, backoff, Retry-After checkbox, cache TTL, and temporary-status checkboxes with visible min/max help. Exact-host overrides block lists sorted cards with Edit/Remove and `Add exact-host override`. Helper explicitly states that subdomains do not inherit.

Preview block accepts one URL and displays effective source (`Project default` or exact hostname), all resolved fields, fingerprint prefix, and whether cache is enabled. Preview never saves. Footer actions: `Save policy`, `Reset to built-in defaults`, `Cancel`.

Validation summary receives focus; each field is linked with `aria-describedby`. Conflict presents server version and retained local draft; user chooses `Reload server version` or `Reapply my draft`. Success announces new version and updates project card without closing.

### Screen 5: Trusted Finding Policy Applied block

Position directly above Probe Evidence. Show version, rule, exact hostname, timeout, max attempts, cache source, fingerprint prefix, and observation time. `Copy evidence summary` copies only sanitized loaded fields and announces completion. Legacy rows show `Legacy observation, policy provenance unavailable`.

Ignored finding displays reason/expiry. Expired state displays exact text `Expired, awaiting fresh confirmed evidence`; it does not appear as open until confirmed recurrence. Audit timeline shows `IGNORE_EXPIRED_REOPENED` with prior reason/expiry metadata after recurrence.

### Responsive and accessibility behavior

Desktop >=1024 px: two-column job cards; policy defaults two columns; host rules table/card grid. Tablet 640-1023 px: one-column jobs and two-column policy fields. Mobile <640 px: single-column controls/cards, full-width dialogs minus 16 px, internal vertical scrolling, host overrides as cards. At 320 CSS px and 200% zoom, no page-level horizontal scrolling or clipped critical actions.

Use labelled sections, ordered job list, articles with headings, labelled progress, native dialog, explicit form labels, table captions, live regions, and safe external link attributes. Opening dialog focuses heading/primary action; closing restores trigger; if a filtered row disappears, focus moves to Jobs heading with explanation. Escape closes only when no save is pending.

### End-to-end success flow

User queues a 10-source project, leaves/reloads dashboard, sees same running job and preserved progress, opens detail, observes one failure, previews and creates a one-source retry, opens child job, then opens a trusted finding and sees exact policy provenance.

### Friendly failure flow

A worker loses its lease during a scan. The old worker receives lease-lost and stops. After expiry, a new worker recovers pending work without repeating completed sources. UI shows `Recovering` as Running with preserved counts, then terminal result. If policy save conflicts, dialog retains local values and requires explicit reapply.

### UI verification

Run supported server with temporary state, deterministic fixture server, and browser tooling when available. Capture temporary screenshots at 1440x900, 768x1024, and 390x844 for empty Jobs, running job, partial detail/retry preview, policy validation, policy success, and expired-ignore finding. Perform keyboard-only, 200% zoom/reflow, reduced motion, contrast, and one screen-reader smoke check. Exclude screenshots from final package and record filenames/results in `development-report.md`. If graphical tooling is unavailable, DOM tests remain mandatory but the development phase must report the visual check blocked rather than claim it.

## Architecture and Technical Design

### Component boundaries

- `scan_jobs.py`: schema v2, immutable models, state machine, lease claim/heartbeat/recovery, source compare-and-set, pagination, cancellation, retry eligibility, idempotency.
- `job_service.py`: project/policy snapshot, coordinator lifecycle, bounded source executor, host semaphores, schedule adapter, finding/history integration.
- `scan_policy.py`: validation, canonical serialization/fingerprint, exact-host resolution, immutable policy versions, snapshot parsing.
- `observation_cache.py` new: SQLite cache adapter with eligibility, lookup, expiry, project/fingerprint isolation, bounded cleanup.
- `package.py`: detailed probe accepts `EffectivePolicy`, injectable requester/clock/sleeper, bounded Retry-After and attempt behavior; legacy `scan_page` unchanged.
- `scheduled_scan.py`: compatibility adapter to common job service.
- `findings.py` and `finding_service.py`: policy provenance columns/writes and atomic expired-ignore reopen.
- `app.py`: authenticated APIs, coordinator lifecycle, complete UI and state management.

### Job and evidence data flow

Create -> authenticate -> active project -> revalidate sources -> load immutable policy document -> transaction inserts job/source/snapshot/idempotency -> return 202 -> coordinator atomically leases -> bounded execution resolves per-target policy -> cache lookup after URL validation -> detailed probe -> cache eligible evidence -> finding/history processing with provenance -> atomic source commit -> heartbeat/count refresh -> final compare-and-set.

### Persistence changes

Alter `scan_jobs` add nullable `worker_id`, `lease_expires_at`, `heartbeat_at`, `policy_snapshot_json`, and `schema_version` default 2. Add source `version` and `policy_fingerprint`. Add `scan_observation_cache` with ID, project, normalized URL, policy fingerprint, observation JSON, classification, created/expires timestamps, source observation ID; index project/url/fingerprint and expiry.

Add finding evidence provenance columns or a canonical `policy_json` field plus indexed version/fingerprint. Prefer explicit scalar columns for list/detail fields and canonical JSON for effective values. Migration is transactional/idempotent, never drops rows, and preserves existing null provenance as legacy.

### State and concurrency

Database is authoritative. Use `BEGIN IMMEDIATE` only for short claim/finalize/recovery transactions. Source requests happen outside transactions. Owner/version predicates protect writes. Job-wide ThreadPoolExecutor size equals project concurrency, capped 20. Per-host semaphores use effective max concurrency. Coordinator heartbeat thread updates only owned running job.

### Logging and errors

Structured events: job_created, job_claimed, job_heartbeat, job_recovered, source_started/completed/failed, cancel_requested/acknowledged, retry_created, policy_saved/resolved, cache_hit/miss/store, finding_reopened_after_expiry. Include IDs, counts, safe hostname, policy version, latency, correlation ID. Exclude tokens, idempotency plaintext, headers, cookies, bodies, full context, and raw exceptions. New API errors retain stable code/detail/field/current envelope.

### Alternatives rejected

Redis/Celery is rejected because it adds operations/dependency burden. Wildcard policies remain rejected for ambiguity. Force cancellation is rejected for thread safety. Mutable policy versions are rejected because old evidence must stay explainable. Frontend rewrite is rejected because existing semantic/vanilla patterns can deliver the bounded workflow.

## Data, API, and Compatibility Changes

Retain existing endpoints and add/complete:

- `POST /api/projects/{project_id}/jobs` -> 202 job; optional `Idempotency-Key`; body `{"render_js":false}`.
- `GET /api/jobs?project_id=&state=RUNNING,FAILED&limit=20&offset=0&updated_after=` -> paginated list.
- `GET /api/jobs/{id}` -> job detail.
- `GET /api/jobs/{id}/sources?state=&limit=100&offset=0` -> paginated sources.
- `POST /api/jobs/{id}/cancel` body `{"version":N}`.
- `POST /api/jobs/{id}/retry-failures` body `{"version":N,"preview":true|false}`.
- `GET /api/projects/{id}/scan-policy`.
- `PUT /api/projects/{id}/scan-policy` with expected version/defaults/host overrides.
- `POST /api/projects/{id}/scan-policy/preview` with URL and optional draft.

Job detail adds lease status only as derived `recoverable_at`, not raw worker identity. Finding evidence adds `policy_version`, `policy_rule`, `policy_hostname`, `policy_fingerprint`, `effective_policy`, and `from_cache`, all nullable for legacy rows.

Existing `/scan`, `/scan-batch`, renderers, CLI, project portable schema v1, findings actions, notifications, and history shapes remain compatible. Import/duplicate projects begin policy version 0 and no jobs. Archive blocks new/retry/policy mutation but preserves reads. Existing scheduled configuration schema remains unchanged.

## Security and Privacy Considerations

Revalidate source/target immediately before every outbound request and before cache lookup. Redirects use current centralized safeguards. Stored URLs are untrusted. Exact hosts use parsed IDNA hostname equality, never suffix matching. Bound timeout, attempts, concurrency, Retry-After, cache TTL/rows, source count, pagination, and JSON sizes. Cache never stores bodies, headers, cookies, credentials, or uncontrolled errors. Cache remains project-scoped. Hash idempotency keys and never log them. Require existing authentication and optimistic versions for all mutation APIs. Escape/textContent all UI data. Add security regression tests for stored unsafe sources, cache bypass attempts, host confusion, IPv4/IPv6/private redirects, and secret sentinels.

## Test Strategy (TDD)

### RED tests for Feature 1

Create/update story-named modules:

- `tests/test_us_001_job_recovery.py`: claim exclusivity, heartbeat, lease loss, restart recovery, completed-source non-repetition, under-500-ms creation.
- `tests/test_us_002_policy_cancellation.py`: project/host concurrency, cancellation before submit/start, in-flight preservation, terminal conflict.
- `tests/test_us_003_retry_schedule.py`: retry exactness, exclusions, unsafe zero-I/O, schedule due-slot idempotency, legacy executor adapter.
- `tests/test_jobs_api.py`: auth, pagination, validation, stable errors, concurrency conflict.
- `tests/test_jobs_ui.py`: all Jobs and Job Detail states/focus/polling.

Real integration uses temporary SQLite plus local HTTP fixtures with delayed 200, repeated 503, 429-then-200, timeout, and terminal 404. Simulate process restart by closing coordinator/store and creating new instances, not by mocking persistence.

### RED tests for Feature 2

- `tests/test_us_004_applied_policy.py`: exact-host precedence, concurrency measurement, exact attempt count, Retry-After cap, fingerprint snapshots, cache eligibility/isolation/expiry.
- `tests/test_us_005_ignore_expiry.py`: no-write expiry reads, one fresh-confirmed reopen, concurrent recurrence, nonconfirmed no reopen, validation.
- `tests/test_us_006_policy_provenance.py`: persisted/API/UI provenance, legacy null behavior, copy summary, secret redaction.
- `tests/test_policy_api.py` and `tests/test_policy_ui.py`: GET/PUT/preview, conflict recovery, every form state.
- `tests/test_observation_cache.py`: boundaries and security.

### Acceptance-to-test mapping

Every Given/When/Then criterion in the six embedded stories receives a `US-xxx` marker or story-named test. The final development report lists each criterion and exact test node ID. Tests that only expect `NotImplementedError` are forbidden.

### Commands

Targeted:

```bash
python -m pytest -q tests/test_us_001_job_recovery.py tests/test_us_002_policy_cancellation.py tests/test_us_003_retry_schedule.py tests/test_jobs_api.py tests/test_jobs_ui.py
python -m pytest -q tests/test_us_004_applied_policy.py tests/test_us_005_ignore_expiry.py tests/test_us_006_policy_provenance.py tests/test_policy_api.py tests/test_policy_ui.py tests/test_observation_cache.py
python -m pytest -q tests/test_project_quick_scan.py tests/test_scheduled_scan.py tests/test_trusted_findings.py tests/test_ssrf_enhanced.py tests/test_dashboard_javascript.py
```

Full and repository-supported checks:

```bash
python -m pytest -q --disable-warnings
ruff check src tests
python -m compileall -q src tests
```

Coverage uses the official lab coverage environment and must measure `scan_jobs.py`, `job_service.py`, `scan_policy.py`, `observation_cache.py`, and changed finding/probe branches at >=90% statement coverage. If pytest-cov is unavailable, the gate is blocked, not waived.

Wheel command remains `python -m pip wheel . --no-deps -w dist-test` when pip is available; remove output after isolated import. Startup smoke starts `python -m brokenlinkbrief.app` with temporary state, verifies `/health` and `/dashboard`, creates a local-fixture project/job, observes recovery/terminal behavior, and stops cleanly. Node syntax uses existing dashboard regression path. Browser E2E is required when Playwright/Chromium is available.

Mandatory official lab commands:

```bash
tdd-gate-v3.sh
bdd-gate.sh
security-gate.sh
doc-sync-check.sh
ui-gate.sh
bash ~/.hermes/scripts/git-push-verify.sh <repo_path>
```

Missing official commands or Git remote access block final completion; developer must not add pass-through replacements.

## Documentation Deliverables

- `README.md`: final durable-job user journey, states, recovery guarantees, cancellation/retry, policy tuning, cache rules, finding provenance, migration, operations, troubleshooting.
- `CHANGELOG.md`: actual version/date, completed job reliability, policy execution, UI, migration, security, actual tests/gates.
- `docs/scan-jobs.md`: state machine, leases/recovery, idempotency, APIs, scheduled unification, errors.
- `docs/scan-policies.md`: fields/bounds, exact-host precedence, Retry-After, cache eligibility, provenance, examples.
- `docs/findings.md`: expired-ignore and provenance fields.
- `FEATURES-DONE.md`: only genuinely complete requirements/stories and actual test evidence.
- `development-report.md`: RED/GREEN, migration, local I/O, coverage, quality gates, UI/screenshots, Git/push, changed files, limitations, traceability.

## Expected File Changes

Expected additions:

- `src/brokenlinkbrief/observation_cache.py`
- `tests/test_us_001_job_recovery.py`
- `tests/test_us_002_policy_cancellation.py`
- `tests/test_us_003_retry_schedule.py`
- `tests/test_us_004_applied_policy.py`
- `tests/test_us_005_ignore_expiry.py`
- `tests/test_us_006_policy_provenance.py`
- `tests/test_jobs_api.py`
- `tests/test_jobs_ui.py`
- `tests/test_policy_api.py`
- `tests/test_policy_ui.py`
- `tests/test_observation_cache.py`

Expected modifications:

- `src/brokenlinkbrief/scan_jobs.py`
- `src/brokenlinkbrief/job_service.py`
- `src/brokenlinkbrief/scan_policy.py`
- `src/brokenlinkbrief/package.py`
- `src/brokenlinkbrief/scheduled_scan.py`
- `src/brokenlinkbrief/app.py`
- `src/brokenlinkbrief/findings.py`
- `src/brokenlinkbrief/finding_service.py`
- existing US-001 through US-004 tests where migrated to stronger story modules
- `tests/test_scheduled_scan.py`
- `tests/test_trusted_findings.py`
- `tests/test_ssrf_enhanced.py`
- `tests/test_dashboard_javascript.py`
- `README.md`, `CHANGELOG.md`, `docs/scan-jobs.md`, `docs/scan-policies.md`, `docs/findings.md`, `FEATURES-DONE.md`, `development-report.md`
- `pyproject.toml` and `src/brokenlinkbrief/__init__.py` only for synchronized release version; no runtime dependency is planned.

No deployment, governance, webhook, CI-gate, SPA-scanner, or project portable-schema changes are expected.

## Traceability Matrix

| Research need | Research evidence | User story id | Planned requirement | Acceptance criterion | Planned implementation location | Planned test evidence | Priority |
|---|---|---|---|---|---|---|---|
| Job survives refresh/restart | Research P0 durable jobs | US-001 | PR-1 | 3 completed sources are not repeated after lease recovery | scan_jobs.py, job_service.py | test_us_001_job_recovery.py | P0 |
| Job creation is asynchronous | Monitoring operations | US-001 | PR-1 | 202 under 500 ms while scanner blocks >=1 s | app.py, job_service.py | jobs API integration test | P0 |
| User can cancel obsolete work | Long-running scan control | US-002 | PR-2 | zero new source starts after cancellation acknowledgment | coordinator/store/UI | test_us_002_policy_cancellation.py | P0 |
| Host controls prevent rate-limit noise | Lychee/429 evidence in research | US-002 | PR-2 | observed exact-host concurrency never exceeds 2 | package.py, job_service.py | concurrency fixture test | P0 |
| Retry only failed work | Recheck/quota anxiety evidence | US-003 | PR-3 | child contains only current eligible failures | job_service.py, APIs/UI | test_us_003_retry_schedule.py | P0 |
| Scheduled work has one identity | Recurring monitoring demand | US-003 | PR-3 | duplicate due-slot claims produce one job | scheduled_scan.py, job store | schedule idempotency integration | P0 |
| Policy is applied, not decorative | Timeout/429 false positives | US-004 | PR-2/PR-4 | exactly 3 attempts under repeated 503; 429->200 nonactionable | package.py, scan_policy.py | test_us_004_applied_policy.py | P0 |
| Cache reduces safe repeated work | Verification/recheck demand | US-004 | PR-4 | eligible hit makes zero requester calls; unsafe/ineligible never hit | observation_cache.py | test_observation_cache.py | P0 |
| Expected exceptions expire safely | Research noise-control signal | US-005 | PR-5 | expiry read is no-write; confirmed recurrence reopens once | findings.py/service.py | test_us_005_ignore_expiry.py | P0 |
| Weak evidence does not reopen | Trustworthy finding positioning | US-005 | PR-5 | transient/recovered after expiry leaves ignored state/version | finding service | parameterized recurrence tests | P0 |
| Classification must be explainable | Evidence-aware differentiator | US-006 | PR-6 | finding detail shows policy version/rule/attempts/cache | findings/API/UI | test_us_006_policy_provenance.py | P0 |
| Evidence must not leak secrets | Security/privacy constraint | US-006 | PR-6 | sentinel absent from DB/API/UI/copy/logs | sanitizer/store/app | secret-sentinel end-to-end test | P0 |

## Risks and Mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| Lease race repeats a source | Duplicate network work/alerts | owner/version predicates, atomic terminal commit, stale-owner tests |
| SQLite contention | Slow or failed writes | WAL, short transactions, busy timeout, bounded retry, contention test |
| Thread cancellation is cooperative | Delayed cancel | strict timeout, no new submissions, honest Cancelling state |
| Policy over-tuning hides issues | False negatives | conservative defaults, tight bounds, exact-host only, visible provenance |
| Cache returns stale results | Missed regressions | TTL off by default, narrow eligibility, fingerprint/project isolation |
| Retry-After stalls capacity | Poor throughput | 30-second cap, injectable wait, host-slot fairness test |
| Schedule adapter breaks callers | Regression | preserve public result model and existing tests |
| Embedded frontend complexity | JS/UI regression | modular functions, DOM contracts, Node syntax, browser E2E when available |
| Legacy evidence lacks provenance | Confusing display | explicit legacy label and nullable API fields |
| Gate/Git tooling absent | Cannot certify lab completion | treat as BLOCKED, never fabricate scripts or push result |

## Definition of Done

- [ ] PR-1 through PR-6 are complete with no facade, placeholder, mock production behavior, or hidden nonfunctional control.
- [ ] US-001 through US-006 pass every embedded happy, edge, and error criterion.
- [ ] Lease ownership, heartbeat, recovery, stale-owner rejection, atomic source commit, and terminal immutability are proven with real SQLite reopen tests.
- [ ] Manual and scheduled saved-project work use one durable job identity and execution path.
- [ ] Cancellation and failed-source retry work through API and complete UI flows.
- [ ] Policy values actually govern concurrency, timeout, attempts, backoff, Retry-After, and cache.
- [ ] Cache eligibility, expiry, isolation, bounds, and unsafe-URL revalidation pass.
- [ ] Expired ignores reopen once only on fresh confirmed evidence.
- [ ] Finding evidence and UI expose sanitized immutable policy provenance.
- [ ] Existing scan/batch/export/project/finding/notification/schedule/CLI/CI contracts remain green.
- [ ] Targeted, full regression, real local-I/O, security, migration, API, UI, and accessibility tests pass.
- [ ] Changed/new core modules achieve >=90% measured statement coverage.
- [ ] Ruff, compile, wheel/import, startup, JavaScript syntax, and applicable browser E2E pass.
- [ ] Desktop/tablet/mobile screenshots and keyboard/zoom/reduced-motion/contrast/screen-reader checks are recorded when tooling permits; unavailable tooling is reported as blocking, not passed.
- [ ] Official `tdd-gate-v3.sh`, `bdd-gate.sh`, `security-gate.sh`, `doc-sync-check.sh`, and `ui-gate.sh` pass.
- [ ] README, CHANGELOG, API docs, FEATURES-DONE, and development-report match actual behavior and actual counts.
- [ ] No credentials, runtime DB, cache, venv, dependency directory, coverage/build output, screenshots, editor state, or scratch data are packaged.
- [ ] `git add -A`, commit, pull/rebase, push, clean status, and official `git-push-verify.sh` complete successfully; missing Git metadata/remote blocks completion.
- [ ] Every research need and user story maps to implementation and named test evidence.
- [ ] Complete project ZIP passes integrity, listing, clean extraction, required-file, and no-extra-directory verification.
