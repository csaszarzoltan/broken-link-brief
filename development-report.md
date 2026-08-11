# Development Report

## Implemented Scope

Implemented active lease heartbeats during blocked source requests and applied immutable effective-policy timeout, maximum attempts, retryable temporary statuses, and bounded exponential backoff to detailed link probes.

## Research Items Addressed

Long-running scan recoverability and recurring timeout/429/5xx false-positive controls.

## Plan Requirements Completed

Completed the active-heartbeat acceptance slice of PR-1 and the detailed-probe execution slice of PR-4. Existing lease recovery, cancellation, retry, cache, and policy-version foundations remain green.

## User Stories Covered

- US-001: PASS for active heartbeat while the scanner blocks; existing recovery tests remain PASS.
- US-002: PARTIAL; existing cancellation remains green, policy-aware parallel concurrency is not complete.
- US-003: PARTIAL; retry remains green, scheduled unification is not complete.
- US-004: PASS for policy timeout, attempts, temporary-status selection, and backoff; PARTIAL overall because Retry-After/cache wiring is incomplete.
- US-005: FAIL, not implemented.
- US-006: FAIL, finding provenance/UI not implemented.

## Architecture Decisions

A dedicated daemon heartbeat thread is scoped to one claimed job and stopped before finalization. `scan_link_detailed` accepts an optional effective policy while retaining legacy defaults for existing callers. Requester and sleeper remain injectable.

## UI and UX Implementation

No new UI surface was completed. Existing dashboard startup and JavaScript regression remain green. Screenshots/E2E were blocked by unavailable graphical browser tooling.

## TDD Evidence

RED: three failures, two for unsupported `policy=` and one for unchanged heartbeat timestamp. GREEN: seven targeted operations tests passed after implementation.

## Tests and Coverage

- Baseline: 850 passed, 45 skipped, 1 xpassed.
- Final regression: 853 passed, 45 skipped, 1 xpassed, 0 failed.
- Targeted: 7 passed, 0 failed.
- Coverage: BLOCKED; pytest-cov rejected the `--cov` arguments. No percentage claimed.

## Lab Quality Gates

- tdd-gate-v3.sh: FAIL, command not found.
- bdd-gate.sh: FAIL, command not found.
- security-gate.sh: FAIL, command not found.
- doc-sync-check.sh: FAIL, command not found.
- ui-gate.sh: FAIL, command not found.

## Lint, Formatting, Type-Check, Build, and Startup Results

- Ruff: BLOCKED, executable unavailable.
- Formatting/type-check: not configured.
- Compile: PASS.
- Build: BLOCKED, pip module unavailable.
- Startup: PASS, health HTTP 200 (410 bytes), dashboard HTTP 200 (52,566 bytes).
- Integration: PASS, real SQLite job heartbeat test.
- E2E/screenshots: BLOCKED, browser tooling unavailable.

## Files Added

- tests/test_us_001_heartbeat.py
- tests/test_us_004_applied_policy.py

## Files Modified

- src/brokenlinkbrief/job_service.py
- src/brokenlinkbrief/package.py
- src/brokenlinkbrief/__init__.py
- pyproject.toml
- README.md
- CHANGELOG.md
- docs/scan-jobs.md
- docs/scan-policies.md
- FEATURES-DONE.md
- development-report.md

## Deferred or Blocked Items

Policy-aware parallelism, Retry-After parsing, cache request-path wiring, scheduled unification, complete operations/policy UI, ignore recurrence, finding provenance, coverage, lab gates, build, screenshots, and Git push.

## Known Limitations

Applied policy does not yet parse Retry-After headers because the current requester contract returns status/reason/location only. ObservationCache remains unwired to the detailed scan path. These are not listed as complete.

## Integrity Verification

All 110 pre-existing files remain present. Ten were intentionally modified and two tests were added. Temporary artifacts are excluded.

## Traceability Matrix

| Research need | User story id | Plan requirement | Implementation evidence | Test evidence | Status |
|---|---|---|---|---|---|
| Long request lease renewal | US-001 | PR-1 | heartbeat thread in JobService | test_us_001_heartbeat.py | COMPLETE |
| Cancellation/concurrency | US-002 | PR-2 | existing cancellation only | existing tests | PARTIAL |
| Schedule/retry | US-003 | PR-3 | existing retry only | existing tests | PARTIAL |
| Applied policy | US-004 | PR-4 | policy-aware scan_link_detailed | test_us_004_applied_policy.py | PARTIAL |
| Ignore recurrence | US-005 | PR-5 | none | none | NOT STARTED |
| Provenance UI | US-006 | PR-6 | none | none | NOT STARTED |

## Suggested Commit Message

feat(operations): apply scan policies and renew active job leases
