# Research Findings

## Executive Summary

BrokenLinkBrief 1.3.1 is a mature beta, self-hostable link-quality monitor, not a simple one-off checker. The supplied project already supports static and JavaScript-rendered scans, saved projects, recurring schedules, diffing, alerts, exports, CI gates, evidence-aware trusted findings, source occurrences, lifecycle actions, and targeted verification. The codebase is strongest where broad SEO suites are weakest: focused repair evidence, local ownership of data, and a dependency-light deployment model.

The current market evidence does **not** justify another generic SEO dashboard. It supports a narrower position: **the trustworthy operations layer between detecting link rot and proving that repair work is complete**. Recurring demand is visible in requests to save arbitrary links and receive warnings, while open-source maintainers repeatedly report false positives from timeouts and HTTP 429 responses. Lychee's official guidance explicitly recommends tuning retries, concurrency, caching, authentication, or exclusions for rate limits, showing that network-policy tuning is table stakes rather than an edge case. [S1] [S2] [S3]

The top three recommended priorities are: **P0 durable asynchronous scan jobs**, **P0 project-level noise-control policies**, and **P1 actionable repair handoff with assignment and issue-tracker links**. The existing trusted-finding and Verify Fix slice should be preserved as the product core. The next development pass should complete durable jobs plus policy controls first, because both improve reliability of every manual, scheduled, and verification workflow. Issue-tracker handoff should be designed in the same pass but implemented only after job and policy events are stable.

Pricing evidence shows a wide willingness-to-pay range. Focused monitoring spans free to $159/month at Dr. Link Check, while professional desktop crawling costs £199/year and broad SEO suites start around $83 to $129/month before higher limits or added users. [S4] [S5] [S6] [S7] The defensible entry model for this project is therefore a generous self-hosted edition plus a future hosted plan based on monitored projects and scan frequency, not per-fix or opaque credits. Exact TAM and CAGR for this narrow category could not be validated from reliable primary evidence and are intentionally not invented.

## Project Understanding

### Verified purpose and users

BrokenLinkBrief scans public pages, extracts and checks links, records history, detects changes, and exposes results through HTTP APIs, a browser dashboard, CLI, exports, notifications, and CI. Verified implementation anchors include `scan_page`, `scan_batch`, `HistoryStore`, and `scan_link_detailed` in `src/brokenlinkbrief/package.py`; `_Handler` and `_DASHBOARD_HTML` in `src/brokenlinkbrief/app.py`; `ProjectStore` in `projects.py`; `FindingStore` in `findings.py`; and `FindingService` in `finding_service.py`.

Primary users are developers and documentation maintainers, SEO/content operators, site administrators, and small agencies. The codebase supports these users through CI baselines, source-aware findings, recurring projects, alerting, batch scans, and project portability. Agency positioning is an inference from multi-project functions, duplicated configurations, exports, and competitor packaging rather than verified product telemetry.

### Architecture and technology stack

- Python 3.10/3.11 package using the standard-library HTTP server and `urllib`-based network paths (`pyproject.toml`, `app.py`, `package.py`).
- SQLite-backed projects, findings, schedules, link state, governance, and scan history; JSONL history is also retained.
- Embedded HTML/CSS/vanilla JavaScript dashboard inside `app.py`, with Chart.js loaded externally.
- Optional Playwright/Chromium rendering via `SpaScanner` in `spa_scanner.py`.
- Docker and Railway deployment assets, setuptools packaging, pytest tests, and Ruff configuration.
- 98 extracted files, 26 Python source modules, 43 Python test files, and 251 statically discovered `test_` functions in this supplied archive.

### Existing interface and principal flow

The principal browser flow is: choose or create a project, run a single or batch scan, review results, filter/search/export, open trusted findings, inspect source/evidence, acknowledge or assign/ignore, repair externally, and use Verify Fix. Saved projects can also be archived, restored, duplicated, imported/exported, and pinned. Scheduling exists in application services and documentation but is not yet a polished browser administration workflow.

### Current strengths

1. **Evidence-aware repair loop.** `confidence.py`, `findings.py`, and `finding_service.py` distinguish confirmed, transient, bot-blocked, recovered, and inconclusive evidence and preserve verification/audit history.
2. **Exact repair context.** Source occurrences, anchor text, and bounded context reduce the need to reproduce a scan manually.
3. **Backward-compatible breadth.** Existing exports, APIs, project lifecycle, notifications, SPA scanning, and CI remain additive rather than repeatedly rewritten.
4. **Security intent.** SSRF validation, redirect policy, HMAC webhooks, formula-injection protection, sanitized evidence, and revalidation of stored URLs are present.
5. **Strong automated regression culture.** The project documents 838 passing tests in the latest development report, while this research phase did not alter or rerun product tests because source changes were prohibited.

### Constraints for planning and development

- Preserve legacy endpoint and export shapes unless changes are additive/versioned.
- Treat all persisted URLs as untrusted before outbound use.
- Keep Playwright optional and static scanning dependency-light.
- Use migration-safe SQLite changes and avoid destructive resets.
- Do not expand the embedded frontend without JavaScript syntax and DOM-level regression coverage.
- Preserve source occurrence/evidence privacy: no headers, cookies, credentials, response bodies, or uncontrolled exceptions.
- Do not conflate raw HTTP status, confidence classification, business priority, and workflow state.

## Current-State Gap Analysis

| Area | Verified current state | Gap | User consequence | Priority |
|---|---|---|---|---|
| Scan execution | Single/batch requests and schedule workers exist | Browser scans are not durable jobs with resumable state, cancellation, or failed-source retry | Refreshes and process failures can lose operational context | P0 |
| Noise control | Evidence classification and bounded retries exist | No project/host policy UI for concurrency, retry, grace, cache, or authenticated rate-limit handling | Users cannot tune recurring false positives safely | P0 |
| Findings | Durable findings, assignment, ignore, audit, verification exist | No comments, labels, due dates, bulk actions, or external tracker link | Teams still hand work off manually | P1 |
| Scheduling | Cron parser, store, leasing, config exist | No complete in-product create/edit/pause/preview workflow | Recurring monitoring remains operator-heavy | P1 |
| Authentication | Optional bearer/query token | No secure browser session, expiration, recovery, or CSRF model | Query tokens can leak through URLs and logs | P1 |
| Integrations | Email, Slack, webhooks exist | Configuration and delivery history are not cohesive in the UI | Troubleshooting alerts is difficult | P2 |
| Information architecture | One long dashboard | No global navigation or shareable filtered views | Discoverability and scalability degrade as features grow | P2 |
| Frontend maintainability | Semantic HTML and useful accessibility hooks | Large embedded asset increases edit risk | UI regressions become harder to isolate | P2 |
| Market measurement | Strong pricing and feature comparables | No reliable narrow-category TAM/CAGR | Investment cases must use bottom-up validation, not invented market size | Explicit unknown |

## Target Users and Jobs to Be Done

| Segment | Core job | Current fit | Highest unmet need |
|---|---|---|---|
| Documentation developer | Prevent link regressions in PRs and scheduled checks | CI gate, CLI, JSON/CSV, evidence | Host-aware retry and durable CI/hosted identity |
| SEO/content operator | Find where a broken link occurs and coordinate repair | Source occurrences, filtering, exports, findings | Bulk triage, owner workflow, external issue handoff |
| Site administrator | Monitor sites without babysitting scans | Projects, schedules, alerts, dashboard | Durable jobs, schedule UI, delivery log |
| Small agency | Separate and repeatedly scan client sites | Projects, duplication, pinning, exports | Portfolio overview, reusable policies, client reporting |
| Engineering manager | Measure new regressions and repair completion | Diffing, verification, audit | SLA metrics, owner/due-date reporting, drill-down |

A direct user-demand example is the request to save commissioned social-post URLs and receive a warning when they disappear, which is monitoring of arbitrary known links rather than a one-time site crawl. [S1] Screaming Frog's official broken-link workflow emphasizes the need to identify the source page through inlinks, validating “where is it?” as a core repair job. [S8]

## Target-Market Pain Points

| User problem | Segment | Recurrence observed | Evidence | Confidence | Implication |
|---|---|---:|---|---|---|
| False positives from transient timeouts | Developers, docs teams | Repeated across public issues | ACCESS-Hive and llm-d issues describe valid links failing due to temporary network conditions or timeouts. [S2] [S9] | HIGH | Keep confidence evidence, retry policy, and inconclusive states first-class |
| HTTP 429/rate limiting creates noisy failures | CI maintainers, large scans | Official docs plus current discussion | Lychee documents 429 floods and recommends concurrency, retry, token, cache, and exclusion controls; a 2026 discussion calls host rate limiting a common real-world problem. [S3] [S10] | HIGH | Add host-aware policy controls and per-host scheduling |
| Users need source context, not only target status | SEO/content operators | Standard competitor workflow | Screaming Frog directs users to the Inlinks tab to locate the source of each broken URL. [S8] | HIGH | Preserve and improve occurrences, anchor/context, safe source links |
| Repeat verification should not consume opaque quota | Site owners | Vendor changed pricing after user learning | Dr. Link Check removed monthly link quotas because users fixing a site need repeated checks to verify changes. [S11] | HIGH | Avoid per-scan credit anxiety; make failed-source retry and Verify Fix cheap |
| Broad SEO suites are expensive for a focused job | Solo operators, small teams | Multiple current price pages/reviews | Ahrefs Lite is $129/month; Sitechecker starts at $83/month on its current official page; a Sitechecker review calls cost steep for solo bloggers. [S6] [S7] [S12] | HIGH | Position focused, self-hostable, lower-complexity value |
| Powerful desktop crawlers can feel technical | Non-technical operators | Multiple reviews | Verified-user summaries report an outdated/technical interface and learning time for Screaming Frog. [S13] | MEDIUM | Provide guided repair UI, not a spreadsheet clone |
| Long-running scans need control and recovery | Site admins, agencies | Inferred from product scale and competitor capabilities | Screaming Frog includes pause/resume and scheduling; open-source crawlers expose concurrency and retries. [S14] [S15] | MEDIUM | Durable job states, cancel, retry-failures, and progress are table stakes |
| Monitoring needs alerts and history | Site owners | Official competitor packaging | Dr. Link Check and Sitechecker package scheduled checks/monitoring and alerts by tier. [S4] [S7] | HIGH | Connect schedules, jobs, changes, and delivery records coherently |

## Competitor Weaknesses

### Dr. Link Check

Strong focused cloud monitoring and clear project/link limits, but substantial scale is gated at $49 to $159/month, and advanced repair ownership is not prominent on the official pricing page. Its own pricing-history post confirms that quota anxiety conflicted with repair verification. [S4] [S11] Opportunity: self-hosted ownership, evidence-grade classifications, and a true finding lifecycle.

### Screaming Frog SEO Spider

Best-in-class crawl depth, source inlinks, JavaScript rendering, scheduling, and configuration at £199/year, but local installation and a technical table-heavy interface impose a learning curve. [S5] [S8] [S13] Opportunity: cloud-like, guided, collaborative repair workflow while keeping precise evidence.

### Ahrefs Site Audit

Strong always-on auditing inside a broad SEO platform, with 100,000 crawl credits on the $129/month Lite plan. [S6] It is expensive if the buyer only needs reliable link operations, and its packaging emphasizes the wider SEO suite rather than repair lifecycle. Opportunity: narrow value, predictable costs, self-hosting, and source-to-verification workflow.

### Sitechecker

Strong agency monitoring, reports, unlimited users, GSC/GA4 context, and email/Slack alerts, but the official entry price is $83/month and daily monitoring begins higher. [S7] Independent review evidence highlights ease of use and actionable recommendations but also price sensitivity for solo users. [S12] Opportunity: focused pricing and operational evidence rather than a broad agency analytics bundle.

### Open-source Linkinator/Lychee class

Fast, automatable, developer-friendly, and configurable. Linkinator supports websites/docs/local files, fragments, retries, and exports; Lychee documents rate-limit tuning. [S3] [S15] Their weakness for this target is not scanning mechanics but the absence of a persistent repair workspace with owners, occurrences, verification history, and non-technical UX. Opportunity: use these projects as standards/behavior references while differentiating on operations.

## Competitor Comparison

| Product | Positioning | Current pricing evidence | Core strengths | Repeated weakness/gap | Exploitable space |
|---|---|---|---|---|---|
| Dr. Link Check | Focused hosted link checker/monitor | Free; $13, $49, $159/month [S4] | Scheduled checks, projects, filters, reports | Higher scale costs; limited visible repair collaboration | Trusted findings plus predictable self-hosted/hosted pricing |
| Screaming Frog | Desktop technical SEO crawler | Free 500 URLs; £199/year [S5] | Deep crawl controls, source inlinks, JS, integrations | Technical UI, local resources, per-user license [S13] | Guided team repair operations |
| Ahrefs Site Audit | Broad all-in-one SEO suite | $129/$249/$449 monthly; enterprise $1,499 [S6] | Always-on audit, large crawler/data ecosystem | Expensive and broad for link-only use | Narrow value and transparent limits |
| Sitechecker | Agency SEO monitoring/control center | $83/$208/$375 monthly on official page [S7] | Monitoring cadence, unlimited users, Slack/email, reports | Price sensitivity; bundled breadth [S12] | Affordable focused operations and self-hosting |
| Linkinator/Lychee | Open-source CI/CLI validation | Free/open source | Automation, speed, configurable retry/concurrency | No durable business repair lifecycle | Hosted UI/workflow built on auditable primitives |

## Validated Demand Signals

1. **Arbitrary-link monitoring:** A web-development user asked for saved links and warnings when commissioned social posts disappear, a close match to project-based recurring monitoring. Publication: 2023-08-11; accessed 2026-08-11. [S1]
2. **Transient false positives:** Maintainers moved full link checking to scheduled runs and proposed retries because temporary outages made unrelated PRs fail. Publication: 2022-11-16; accessed 2026-08-11. [S2]
3. **Current timeout false positives:** A 2026 issue reports valid Envoy links marked failed due to timeout and requests a higher threshold. Publication: 2026-04-22; accessed 2026-08-11. [S9]
4. **Rate-limit controls:** Lychee documents 429 floods and concrete mitigations; a 2026 maintainer response describes the problem as common enough to drive per-host rate limiting. Accessed 2026-08-11. [S3] [S10]
5. **Repeated repair verification:** Dr. Link Check changed from monthly quotas to per-project capacity because users need unlimited rechecks while fixing a site. Publication: 2019-04-29; accessed 2026-08-11. [S11]
6. **Source-location workflow:** Screaming Frog's official tutorial treats the Inlinks/source page as the necessary next step after finding a 404. Accessed 2026-08-11. [S8]
7. **Monitoring and alerts are paid value:** Focused and suite competitors reserve frequency, scale, alerts, integrations, or API access for paid tiers. [S4] [S6] [S7]
8. **Affordability gap:** Sitechecker review evidence praises ease/actionability but calls the subscription steep for a solo blogger; Screaming Frog reviews praise depth but call the interface technical. [S12] [S13]

## Market and Pricing Evidence

### Direction and adoption

Recurring audits, scheduling, alerts, crawl history, and project-based limits appear across Dr. Link Check, Screaming Frog, Ahrefs, Sitechecker, Semrush, Linkinator, and Lychee. This cross-category convergence is strong directional evidence that repeat monitoring, not only one-off scanning, is the durable use case. [S4] [S5] [S6] [S7] [S15]

Google's crawler documentation confirms that 4xx/5xx and failed redirects generate Search Console errors, while 2xx can still represent a soft 404, supporting the need for evidence beyond a simplistic “status below 400 equals healthy” rule. [S16]

### Pricing range and monetization pattern

| Market layer | Evidence | Buyer interpretation |
|---|---|---|
| Free/open source | Linkinator, Lychee, LinkChecker | Developers expect a capable free automation baseline |
| Focused monitoring | Dr. Link Check: $0, $13, $49, $159/month [S4] | Willingness to pay rises with project size, cadence, and reports |
| Desktop professional | Screaming Frog: free up to 500 URLs, £199/year [S5] | One-time annual-like licensing remains attractive to technical users |
| SEO suite entry | Sitechecker $83/month; Ahrefs Lite $129/month [S7] [S6] | Broad analytics supports higher ARPU but creates a focus/price gap |
| Broad suite mid-market | Ahrefs $249/$449; Sitechecker $208/$375 [S6] [S7] | Agencies pay for scale, users, integrations, and reporting |

Recommended commercial hypothesis, to validate rather than treat as fact:
- Maintain a free self-hosted edition with complete core repair workflow.
- Future hosted Starter: 3 projects, daily scans, 30-day history, email alerts, roughly $12 to $19/month.
- Team: 10 projects, hourly/daily schedules, Slack/webhooks, 1-year history, roughly $39 to $59/month.
- Agency: portfolio controls and branded reports, roughly $99 to $149/month.
These ranges are positioning hypotheses derived from competitor anchors, not demonstrated willingness-to-pay for BrokenLinkBrief itself. No reliable narrow-category TAM/CAGR was found.

## Modern UX Expectations

### Category baseline

- Persistent project context and navigation for Overview, Jobs/Scans, Findings, Schedules, Integrations, and Settings.
- Guided first run: create project, validate scope, run first scan, explain why only confirmed failures become findings, configure schedule/alert.
- Durable job surfaces with queued, running, partial, completed, failed, and cancelled states.
- Findings table with server pagination, filters, search, owner, source count, confidence, and workflow state.
- Detail panel/dialog with target, all source occurrences, ordered evidence, audit, verification, and safe external links.
- Independent empty/loading/error/stale/disabled/success states for every panel, not one global failure.
- Responsive cards at narrow widths, no horizontal page scroll at 320 CSS pixels, and preserved critical actions at 200% zoom.
- Trust indicators: clear data location, retention, sanitized evidence, outbound security policy, last scan time, applied policy version, and audit history.
- Progressive disclosure: summary first, attempts/context/audit collapsed until requested.

WCAG 2.2 expects keyboard accessibility, visible focus, focus not obscured, reflow, status messages, and minimum target-size handling; W3C's guidance explains the importance of clear focus indicators and lists the relevant criteria. [S17] [S18]

### Existing coverage versus missing baseline

| Expectation | State | Evidence in project |
|---|---|---|
| Labels, live regions, dialog focus, reduced motion | Mostly met | `app.py` dashboard and findings UI tests |
| Exact source context and evidence | Met | `findings.py`, `finding_service.py`, `docs/findings.md` |
| Durable job progress/cancel/retry | Missing | Synchronous scan endpoints; scheduler is separate |
| Independent panel failures | Partial | Dashboard has local feedback but analytics aggregation remains broad |
| Secure browser session | Missing | Query/bearer token auth only |
| Shareable filtered views | Missing | Filters are mainly in-memory |
| Schedule administration | Missing/partial | Scheduler/config services and docs exist, complete UI does not |
| Integration test/delivery history | Missing | Channels exist but no cohesive registry/log UI |
| Frontend component isolation | Missing | Dashboard remains embedded in `app.py` |

## Open-Source and Automation Opportunities

1. **Adopt host-aware scheduling patterns from Lychee.** Per-host concurrency, retry-after handling, cache age, authentication, and specific exclusions should inform project policy design. [S3] [S10]
2. **Match Linkinator's CI ergonomics.** Recursive Markdown/HTML/local scanning, fragment checks, skip patterns, retries, and job summaries are useful compatibility targets. [S15]
3. **Retain LinkChecker's protocol/filter/export lessons.** It demonstrates mature recursive checking, regex restrictions, proxy/auth, robots handling, and multiple output formats. [S14]
4. **Use standards, not crawler guesses, for HTTP classification.** Google's published handling of success, redirects, errors, and soft 404s provides a reference for explicit semantics. [S16]
5. **Automate failed-source retry.** Durable job records can create a child job containing only failed sources, reducing network load and user waiting.
6. **Automate expiry and recurrence.** Expired ignores should reopen only on fresh confirmed evidence, and resolved findings should reopen on recurrence with an audit trail.
7. **Generate versioned issue payloads.** External-tracker handoff should include stable finding ID, bounded source context, evidence summary, and back-link, with idempotency to prevent duplicates.
8. **Keep compatibility with the current stack.** SQLite leases, immutable dataclasses, standard-library HTTP, existing `FindingStore`, and optional Playwright allow these improvements without a framework rewrite.

## Differentiation Opportunities

| Opportunity | Problem solved | Target user | Evidence | Competitor gap | Value | Complexity | Risk | Priority | Success criterion |
|---|---|---|---|---|---|---|---|---|---|
| Durable asynchronous scan jobs | Refresh/process loss; no cancel/retry | Admins, agencies | Monitoring cadence and crawl controls are table stakes [S4] [S5] | Focused tools monitor but often hide job mechanics | Reliability and operational control | HIGH | SQLite worker recovery and duplicate execution | P0 | 99% of committed jobs reach one terminal state in restart tests; failed-source retry repeats no successful source |
| Project/host noise-control policies | 429/timeouts create false findings | Developers, docs teams | Lychee guidance and current issue evidence [S3] [S9] [S10] | Most tools expose low-level knobs without evidence-linked policy history | Fewer false positives with auditability | MEDIUM | Over-tuning may hide failures | P0 | Reduce fixture false-positive findings by at least 80% without suppressing repeated 404/410 cases |
| Repair handoff and external issue link | Work leaves the app through CSV/manual copy | Team leads, developers | Source context and repeated verification demand [S8] [S11] | Crawlers detect but do not own repair lifecycle | Faster assignment and less duplicate work | MEDIUM | Integration auth and duplicate issues | P1 | 90% of issue creations are idempotent in retry tests and include source context plus backlink |
| In-product schedule administration | Schedules require config/operator work | Site admins | Paid competitors monetize cadence and alerts [S4] [S7] | Self-hosted tools often require cron files | Lower onboarding friction | MEDIUM | Timezone/DST and worker state | P1 | User creates, previews, pauses, and resumes a schedule in under 2 minutes in usability tests |
| Secure browser sessions | Query token leakage and poor account UX | All browser users | Project docs acknowledge query-token exposure | Many hosted products provide standard sessions | Trust and deployability | HIGH | Identity migration and CSRF | P1 | No credential appears in URL/history/log tests; session expiry and logout pass E2E tests |
| Actionable portfolio overview | Cumulative charts do not direct work | Agencies/managers | Suites emphasize monitoring, reports, severity [S7] [S19] | Broad suites are expensive and noisy | Quick prioritization across projects | MEDIUM | Metric-definition drift | P2 | Every overview metric drills to the exact filtered records and reconciles to API totals |
| Transparent self-hosted pricing/limits | Suite cost and credit anxiety | Solo operators, small teams | Pricing anchors and Dr. Link Check quota change [S4] [S6] [S7] [S11] | Broad suites bundle unrelated SEO features | Clear value and trust | LOW | Hosting economics | P2 | At least 30% hosted-trial conversion in a future instrumented pilot without per-scan overage complaints |

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
  },
  {
    "id": "US-007",
    "epic": "Actionable Repair Handoff",
    "role": "repair owner",
    "action": "create an issue from a trusted finding with source context",
    "benefit": "I can move work into the team's existing tracker without copying data manually",
    "story": "As a repair owner, I want to create an issue from a trusted finding with source context, so that I can move work into the team's existing tracker without copying data manually.",
    "gui_flow": [
      "User opens a confirmed finding -> sees source occurrences and verification history",
      "User clicks Create issue -> sees integration, project, title, and body preview",
      "User chooses which occurrences to include -> preview updates without exposing secrets",
      "User confirms -> sees linked external issue ID and Open in tracker action",
      "User returns later -> sees synchronization status and last delivery result"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "a configured issue-tracker integration and an unlinked finding",
        "when": "the user creates an issue",
        "then": "exactly one external issue is created with finding ID, target URL, bounded source context, and a backlink"
      },
      {
        "type": "given",
        "text": "the finding already has an external issue",
        "when": "the user clicks Create issue",
        "then": "the UI opens the existing link or requires explicit Create another instead of silently duplicating"
      },
      {
        "type": "given",
        "text": "the tracker returns an authentication error",
        "when": "creation fails",
        "then": "the finding remains unchanged, the secret is masked, and the UI shows a test-integration action"
      }
    ]
  },
  {
    "id": "US-008",
    "epic": "Actionable Repair Handoff",
    "role": "team lead",
    "action": "assign trusted findings and filter by owner and state",
    "benefit": "responsibility remains visible across scans",
    "story": "As a team lead, I want to assign trusted findings and filter by owner and state, so that responsibility remains visible across scans.",
    "gui_flow": [
      "User opens Findings -> sees project, state, classification, owner, and search filters",
      "User selects one finding -> opens the detail dialog",
      "User enters an assignee -> saves and receives a live success message",
      "User closes the dialog -> list retains filters and updates the owner cell",
      "User filters by assignee -> sees only matching findings with total count"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "an open finding at version 4",
        "when": "the user assigns Alice with expected version 4",
        "then": "assignee becomes Alice, version becomes 5, and audit history records the change"
      },
      {
        "type": "given",
        "text": "another session updates the finding first",
        "when": "the user saves stale version 4",
        "then": "the server returns 409 with the current representation and the UI preserves the typed assignee for retry"
      },
      {
        "type": "given",
        "text": "assignee text exceeds 120 characters",
        "when": "the user saves",
        "then": "client and server reject it and no audit event is added"
      }
    ]
  },
  {
    "id": "US-009",
    "epic": "Actionable Repair Handoff",
    "role": "repair owner",
    "action": "verify a fix and close work only with sufficient evidence",
    "benefit": "resolution is credible and auditable",
    "story": "As a repair owner, I want to verify a fix and close work only with sufficient evidence, so that resolution is credible and auditable.",
    "gui_flow": [
      "User opens a finding -> sees Verify fix as the primary action",
      "User clicks Verify fix -> dialog becomes busy and announces verification started",
      "System revalidates target and active source URLs -> shows source-check progress summary",
      "Verification completes -> shows Recovered, Removed from source, Still broken, or Inconclusive",
      "User closes dialog -> list updates while preserving filter, sort, selection, and focus"
    ],
    "acceptance_criteria": [
      {
        "type": "given",
        "text": "the target succeeds and at least one source still contains it",
        "when": "verification completes",
        "then": "outcome is RECOVERED, finding becomes RESOLVED, and evidence plus audit records persist"
      },
      {
        "type": "given",
        "text": "all successfully fetched sources prove the link absent",
        "when": "verification completes",
        "then": "outcome is REMOVED_FROM_SOURCE and active occurrences are reconciled without deleting history"
      },
      {
        "type": "given",
        "text": "a source cannot be fetched and target evidence is insufficient",
        "when": "verification completes",
        "then": "outcome is INCONCLUSIVE, workflow state is unchanged, and the sanitized source failure is shown"
      }
    ]
  }
]
```

## Priority-Ranked Development Recommendations

1. **P0: Durable asynchronous jobs.** Introduce a single job model used by manual and scheduled scans, with SQLite persistence, leasing, idempotency keys, cancellation, partial completion, progress, and child retry jobs. This is the foundation for reliable monitoring, not a UI-only enhancement.
2. **P0: Host-aware noise-control policies.** Add project defaults plus optional hostname overrides for concurrency, retries, Retry-After, timeout, cache, excluded/accepted temporary outcomes, and authentication references. Persist the applied policy version with evidence.
3. **P1: Actionable repair handoff.** Expand the existing finding lifecycle with owner filters and one idempotent issue-tracker connector after stable job/finding events exist.
4. **P1: Schedule administration UI.** Reuse the scheduler store, but route due work through the durable job service so manual and scheduled runs share status and history.
5. **P1: Secure browser sessions.** Replace query-token-first browser usage with secure, expiring sessions and CSRF protection while retaining bearer tokens for API clients.
6. **P2: Integration registry and delivery log.** Persist channel configuration references and sanitized delivery attempts; add Test connection and Retry where safe.
7. **P2: Frontend extraction and global navigation.** Extract assets and add navigation only after the job/findings information architecture stabilizes.

## Recommended Scope for the Next Development Pass

Deliver one coherent **Reliable Monitoring Operations** vertical slice:

- Add `ScanJobStore` and `ScanJobService` using the configured SQLite database.
- States: QUEUED, RUNNING, PARTIALLY_COMPLETED, COMPLETED, FAILED, CANCEL_REQUESTED, CANCELLED.
- Manual and scheduled project scans create the same job type.
- Add per-source progress, sanitized failures, cancellation, restart recovery, idempotent submission, and retry-failed-sources.
- Add project defaults and hostname override policies for concurrency, retries/backoff, timeout, cache age, and temporary-status treatment.
- Record policy version and attempt evidence against results/findings.
- Add dashboard Jobs panel with loading, empty, progress, partial, cancelled, failure, and success states.
- Retain current synchronous endpoints for compatibility; either wrap them around a blocking wait with strict limits or introduce additive `/api/jobs` endpoints and migrate the dashboard first.
- Do **not** include a global frontend rewrite, billing, portfolio white-labeling, full identity/RBAC integration, or multiple issue trackers in this pass.

Pass-level success metrics:
- Restart test proves no committed job is lost or executed twice.
- Cancellation prevents new sources from starting after acknowledgement.
- Retry-failed-sources contains exactly the eligible failures.
- Rate-limit fixtures show at least 80% fewer false actionable findings than the default uncontrolled fixture while repeated 404/410 remains confirmed.
- Existing 1.3.1 APIs, exports, findings, project lifecycle, and 838-test regression baseline remain compatible.

## Risks, Unknowns, and Assumptions

- **No product telemetry or interviews were supplied.** User segments and workflow frequency are triangulated from public behavior and project design, not measured BrokenLinkBrief usage.
- **No reliable narrow TAM/CAGR.** Broad website-monitoring or SEO-market reports are not accepted as a precise market size for this product.
- **SQLite concurrency.** Durable jobs are feasible for a compact self-hosted deployment, but multi-process lease recovery and write contention require explicit tests.
- **Policy misuse.** Accepting 429 or broad exclusions can hide genuine outages; controls need defaults, warnings, evidence, and bounded scope.
- **Legal/privacy boundaries.** Source context may contain sensitive content; continue bounded extraction and avoid storing bodies, credentials, headers, or cookies.
- **Authentication references.** Host-specific credentials can improve reliability but materially expand secret-management scope; implement references to environment/secret stores, not plaintext database values.
- **Issue-tracker assumptions.** Demand for handoff is inferred from export and team workflows. Validate the first connector with interviews before supporting several vendors.
- **Pricing hypotheses are unvalidated.** Competitor anchors support ranges, not conversion forecasts.
- **Accessibility requires manual evidence.** Contract tests alone cannot prove WCAG 2.2 AA; keyboard, zoom/reflow, contrast, and screen-reader checks remain release gates.
- **Current source count/test count are archive observations.** They are not claims that all tests were executed during this research-only phase.

## Sources

1. **[S1]** Reddit r/webdev, “Is there a tool for checking broken links?” Published 2023-08-11. https://www.reddit.com/r/webdev/comments/15o2xye/is_there_a_tool_for_checking_broken_links/ Accessed 2026-08-11.
2. **[S2]** ACCESS-Hive GitHub, “Markdown link check false positives #227.” Published 2022-11-16. https://github.com/ACCESS-Hive/access-hive.github.io/pull/227 Accessed 2026-08-11.
3. **[S3]** Lychee official documentation, “Rate Limits.” https://lychee.cli.rs/troubleshooting/rate-limits/ Accessed 2026-08-11.
4. **[S4]** Dr. Link Check, “Pricing.” https://www.drlinkcheck.com/pricing Accessed 2026-08-11.
5. **[S5]** Screaming Frog, “Pricing.” https://www.screamingfrog.co.uk/seo-spider/pricing/ Accessed 2026-08-11.
6. **[S6]** Ahrefs, “Plans & Pricing.” https://ahrefs.com/pricing Accessed 2026-08-11.
7. **[S7]** Sitechecker, “Plans & Pricing.” https://sitechecker.pro/account/plans/ Accessed 2026-08-11.
8. **[S8]** Screaming Frog, “How To Find Broken Links Using The SEO Spider.” https://www.screamingfrog.co.uk/seo-spider/tutorials/broken-link-checker/ Accessed 2026-08-11.
9. **[S9]** llm-d-router GitHub, “False positives in Check Markdown Links #864.” Published 2026-04-22. https://github.com/llm-d/llm-d-router/issues/864 Accessed 2026-08-11.
10. **[S10]** Lychee GitHub Discussion #2033, “Suddenly have 429 with developer.hashicorp.com.” Published 2026-02-06. https://github.com/lycheeverse/lychee/discussions/2033 Accessed 2026-08-11.
11. **[S11]** Dr. Link Check Blog, “Pricing Changes.” Published 2019-04-29. https://www.drlinkcheck.com/blog/pricing-changes Accessed 2026-08-11.
12. **[S12]** Capterra, “Sitechecker Pricing,” including published user review on solo-blogger price sensitivity. https://www.capterra.com/p/166377/Sitechecker/pricing/ Accessed 2026-08-11.
13. **[S13]** Techjockey, “Screaming Frog Reviews 2026: Pros & Cons and Ratings.” https://www.techjockey.com/reviews/screaming-frog Accessed 2026-08-11.
14. **[S14]** LinkChecker official documentation, “LinkChecker.” https://linkchecker.github.io/linkchecker/index.html Accessed 2026-08-11.
15. **[S15]** Justin Beckwith, “Linkinator - Broken Link Checker & Website Crawler.” https://jbeckwith.com/projects/linkinator Accessed 2026-08-11.
16. **[S16]** Google for Developers, “How HTTP status codes affect Google's crawlers.” Updated 2026-02-04. https://developers.google.com/crawling/docs/troubleshooting/http-status-codes Accessed 2026-08-11.
17. **[S17]** W3C WAI, “Understanding WCAG 2.2.” https://www.w3.org/WAI/WCAG22/Understanding/ Accessed 2026-08-11.
18. **[S18]** W3C WAI, “Understanding Success Criterion 2.4.13: Focus Appearance.” https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance Accessed 2026-08-11.
19. **[S19]** Semrush, “Technical SEO audit / Site Audit features.” https://www.semrush.com/features/site-audit/ Accessed 2026-08-11.
20. **[S20]** GitHub Docs, “Rate limits for the REST API.” https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api Accessed 2026-08-11.
21. **[S21]** GitHub, `JustinBeckwith/linkinator` repository. https://github.com/JustinBeckwith/linkinator Accessed 2026-08-11.
