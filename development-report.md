# Development Report

## Implemented Scope

Implemented the core of Reliable Monitoring Operations: SQLite-backed saved-project jobs, persisted per-source progress, idempotent creation, cooperative queued/running cancellation, failed-source retry previews and child jobs, additive job APIs, exact-host versioned scan-policy persistence, and an accessible dashboard job summary.

## Research Items Addressed

Durable asynchronous jobs and project/host noise-control policy foundations were addressed. Evidence-policy execution inside the low-level detailed probe, observation cache, policy provenance on findings, and the full policy editor were not completed.

## Plan Requirements Completed

PR-1, PR-2, and PR-3 are substantially implemented. PR-4 is PARTIAL: validation, immutable versions, exact-host precedence, API persistence, and job policy snapshots exist; probe concurrency/retry/cache execution and policy editor are blocked. PR-5 and PR-6 were not changed because the supplied trusted-findings implementation already covers part of ignore/evidence behavior, but the newly planned recurrence/provenance requirements were not completed.

## User Stories Covered

- US-001: PASS for persistence, idempotency, partial completion, and source counts; FAIL for lease heartbeat/restart recovery timing contract.
- US-002: PASS for queued cancellation and terminal conflict; PASS at service boundary for cooperative running cancellation.
- US-003: PASS for failed-only child jobs and removed-source exclusion; unsafe-source behavior uses existing validation.
- US-004: PARTIAL/PASS for saved exact-host precedence and bounded validation; FAIL for runtime concurrency/attempt enforcement and complete UI.
- US-005: FAIL, no new acceptance test or implementation in this pass.
- US-006: FAIL, policy provenance is retained at job level only, not finding evidence.

## Architecture Decisions

Added `scan_jobs.py`, `job_service.py`, and `scan_policy.py`. Jobs and policies share the configured project SQLite database. Existing synchronous scan APIs remain unchanged. A process-local daemon coordinator is started lazily by job API access. Exact-host rules are normalized with IDNA and avoid wildcard matching.

## UI and UX Implementation

Added a semantic Scan jobs section with heading, live status, ordered job cards, textual state/counts, native progress elements, policy version, empty and retry states. It is integrated with the real jobs API. The planned job-detail dialog, cancellation/retry controls, and policy editor were not completed. HTML/JavaScript syntax regression passed. Startup HTML was inspected through the delivered dashboard response; graphical screenshots and E2E were blocked because no usable browser automation/runtime was available.

## TDD Evidence

RED: first targeted run after tests were authored reported 6 failures and 2 passes due to the unimplemented/incorrect job insert path (`sqlite3.OperationalError: table scan_jobs has 14 columns but 15 values were supplied`). GREEN: after correction, the story-targeted suite reported 8 passed. Affected UI syntax suite then reported 9 passed.

## Tests and Coverage

- Baseline: `python -m pytest -q --disable-warnings` -> 838 passed, 45 skipped, 1 xpassed, 0 failed.
- Final: `python -m pytest -q --disable-warnings` -> 846 passed, 45 skipped, 1 xpassed, 0 failed.
- Targeted: 9 passed, 0 failed.
- Coverage command using pytest-cov failed because the plugin is unavailable (`unrecognized arguments: --cov`). No coverage percentage is claimed.

## Lab Quality Gates

- `tdd-gate-v3.sh`: FAIL, command not found.
- `bdd-gate.sh`: FAIL, command not found.
- `security-gate.sh`: FAIL, command not found.
- `doc-sync-check.sh`: FAIL, command not found.
- `ui-gate.sh`: FAIL, command not found.
- `bash ~/.hermes/scripts/git-push-verify.sh /tmp/blb-develop`: FAIL, script not present.

## Lint, Formatting, Type-Check, Build, and Startup Results

- Ruff: BLOCKED, executable not installed.
- Formatting: not configured; no pass claimed.
- Type-check: not configured.
- Compile: `python -m compileall -q src tests` PASS.
- Wheel: BLOCKED, Python environment has no pip module.
- Startup: PASS. `/health` HTTP 200 (410 bytes) and `/dashboard` HTTP 200 (52,566 bytes) on port 8765 with a temporary database.
- Integration: PASS through real SQLite reopen in story tests and live HTTP startup smoke.
- E2E/screenshots: BLOCKED, no graphical browser runtime/tooling.

## Files Added

- src/brokenlinkbrief/scan_jobs.py
- src/brokenlinkbrief/job_service.py
- src/brokenlinkbrief/scan_policy.py
- tests/test_us_001_durable_jobs.py
- tests/test_us_002_job_cancellation.py
- tests/test_us_003_retry_failures.py
- tests/test_us_004_scan_policy.py
- docs/scan-jobs.md
- docs/scan-policies.md

## Files Modified

- src/brokenlinkbrief/app.py
- src/brokenlinkbrief/__init__.py
- pyproject.toml
- README.md
- CHANGELOG.md
- FEATURES-DONE.md
- development-report.md

## Deferred or Blocked Items

Runtime policy enforcement in detailed probes, observation cache, finding policy provenance, expired-ignore fresh-evidence behavior, job lease heartbeat/recovery, complete job-detail/policy UI, scheduled-executor unification, 90% measured coverage, lab gates, Ruff, wheel build, screenshots/E2E, and git push verification remain blocked or incomplete.

## Known Limitations

The worker is process-local and lacks the planned durable heartbeat/expired-lease recovery. Policy versions are persisted and snapshotted by jobs but do not yet alter scanner retries/concurrency/cache. New POST job endpoints need a follow-up centralized auth helper review. Dashboard job cards poll only on explicit load/refresh rather than the planned adaptive timer.

## Integrity Verification

The input contained 98 pre-existing files. No pre-existing file was removed. Intentional changes are listed above. Temporary DBs, caches, bytecode, build outputs, and scratch data are excluded from packaging.

## Traceability Matrix

| Research need | User story id | Plan requirement | Implementation evidence | Test evidence | Status |
|---|---|---|---|---|---|
| Durable jobs | US-001 | PR-1 | scan_jobs.py, job_service.py, job APIs | test_us_001_durable_jobs.py | PARTIAL |
| Cancellation | US-002 | PR-2 | ScanJobStore.cancel, coordinator cancellation boundary | test_us_002_job_cancellation.py | COMPLETE |
| Failed-source retry | US-003 | PR-3 | retry_preview/retry_failures and child job | test_us_003_retry_failures.py | COMPLETE |
| Host policy | US-004 | PR-4 | ScanPolicyStore validation/version/resolve | test_us_004_scan_policy.py | PARTIAL |
| Ignore recurrence | US-005 | PR-5 | not implemented | no new evidence | NOT STARTED |
| Evidence provenance | US-006 | PR-6 | job-level policy version only | no finding-provenance test | PARTIAL |

## Suggested Commit Message

feat(operations): add durable scan jobs and versioned host policies
