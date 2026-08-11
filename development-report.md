# Development Report

## Implemented Scope

Completed the durable-job recovery foundation and safe observation-cache foundation: worker-owned leases, heartbeat validation, exclusive claims, stale-owner rejection, expired-lease recovery without repeating committed sources, complete immutable policy snapshots on jobs, and project/policy-fingerprint scoped caching for eligible evidence.

## Research Items Addressed

Durable asynchronous scan recovery, repeated-check efficiency, and auditable policy isolation.

## Plan Requirements Completed

PR-1 lease/recovery is complete for store and coordinator ownership. PR-4 cache persistence/isolation and job policy snapshots are complete. Remaining PR-2 runtime policy execution, PR-3 scheduled unification, PR-5 ignore recurrence, and PR-6 complete UI/provenance remain incomplete.

## User Stories Covered

- US-001: PASS for exclusive lease claim, recovery, stale-owner rejection, and non-repetition of completed sources.
- US-002: Existing cancellation behavior remains PASS; planned policy-aware bounded concurrency not completed.
- US-003: Existing retry behavior remains PASS; scheduled unification not completed.
- US-004: PARTIAL, cache isolation/eligibility and policy snapshots PASS; runtime retry/concurrency enforcement incomplete.
- US-005: FAIL, not implemented.
- US-006: FAIL, finding-level provenance/UI not implemented.

## Architecture Decisions

Extended the existing SQLite job schema additively. Lease writes use short immediate transactions and owner checks. Added `ObservationCache` as a separate adapter with conservative eligibility and project/fingerprint isolation. No runtime dependency was added.

## UI and UX Implementation

No new screens were added in this pass. Existing Scan Jobs UI remains operational and JavaScript syntax regression passed. Graphical screenshots/E2E were blocked because browser tooling was unavailable.

## TDD Evidence

RED: `tests/test_us_001_job_recovery.py` and `tests/test_us_004_observation_cache.py` initially failed during collection because `JobLeaseLost` and `ObservationCache` did not exist. GREEN: final targeted UI/feature run reported 5 passed; combined new/previous operations tests reported 12 passed.

## Tests and Coverage

- Baseline: 846 passed, 45 skipped, 1 xpassed, 0 failed.
- Final regression: 850 passed, 45 skipped, 1 xpassed, 0 failed.
- Final targeted: 5 passed, 0 failed.
- Coverage: BLOCKED. pytest-cov is unavailable; the exact command failed with `unrecognized arguments: --cov`. No percentage is claimed.

## Lab Quality Gates

- tdd-gate-v3.sh: FAIL, command not found.
- bdd-gate.sh: FAIL, command not found.
- security-gate.sh: FAIL, command not found.
- doc-sync-check.sh: FAIL, command not found.
- ui-gate.sh: FAIL, command not found.

## Lint, Formatting, Type-Check, Build, and Startup Results

- Ruff: FAIL/BLOCKED, executable unavailable.
- Formatting: not configured.
- Type-check: not configured.
- Compile: PASS, `python -m compileall -q src tests`.
- Build: BLOCKED, pip module unavailable in this environment.
- Startup: PASS; `/health` 200 (409 bytes), `/dashboard` 200 (52,566 bytes).
- Integration: PASS using real SQLite reopen and lease expiry.
- E2E/screenshots: BLOCKED, no graphical browser tooling.

## Files Added

- src/brokenlinkbrief/observation_cache.py
- tests/test_us_001_job_recovery.py
- tests/test_us_004_observation_cache.py

## Files Modified

- src/brokenlinkbrief/scan_jobs.py
- src/brokenlinkbrief/job_service.py
- src/brokenlinkbrief/__init__.py
- pyproject.toml
- README.md
- CHANGELOG.md
- docs/scan-jobs.md
- docs/scan-policies.md
- FEATURES-DONE.md
- development-report.md

## Deferred or Blocked Items

Runtime policy concurrency/retry/Retry-After enforcement, scheduled-job unification, full operations UI, ignore-expiry recurrence, finding policy provenance, measured coverage, official gates, Ruff, build, screenshots, and Git push.

## Known Limitations

Heartbeat support is available but the coordinator does not yet run a separate periodic heartbeat during a single long source request. Cache adapter is implemented and tested but is not yet wired into the detailed scanner. These items are not listed as done.

## Integrity Verification

All 107 pre-existing files remain present. Intentional changes and additions are listed above. Runtime DBs, caches, bytecode, build output, histories, and credentials are excluded.

## Traceability Matrix

| Research need | User story id | Plan requirement | Implementation evidence | Test evidence | Status |
|---|---|---|---|---|---|
| Restart-safe jobs | US-001 | PR-1 | lease columns, claim, heartbeat, recovery, owner checks | test_us_001_job_recovery.py | COMPLETE |
| Cancellation | US-002 | PR-2 | existing cancel state machine | existing US-002 tests | PARTIAL |
| Failed-only retry | US-003 | PR-3 | existing retry preview/child job | existing US-003 tests | PARTIAL |
| Safe repeat work | US-004 | PR-4 | observation_cache.py and job policy snapshot | test_us_004_observation_cache.py | PARTIAL |
| Ignore recurrence | US-005 | PR-5 | not implemented | none | NOT STARTED |
| Finding provenance | US-006 | PR-6 | not implemented | none | NOT STARTED |

## Suggested Commit Message

feat(operations): add recoverable job leases and safe observation cache
