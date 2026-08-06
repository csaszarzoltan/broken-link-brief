# Remediation Report

## Scope

Resolved the blocking and material nonblocking issues identified in `review-findings.md` without expanding the approved Trusted Finding to Verified Repair scope.

## Fixes

- Closed SSRF bypasses in saved-project finding generation and Verify Fix by applying `validate_scan_url` before every new extracted/stored target or source request.
- Added project foreign-key integrity for fresh schemas, project existence checks, and archived-project read-only enforcement.
- Implemented automatic reopening of expired ignores with an audit event.
- Added source URL and anchor-text search, validated state/classification filters, and active occurrence reconciliation after successful source verification.
- Redacted credential-like fragments in persisted error evidence.
- Added classification filtering plus evidence, verification, and audit history in the dashboard, with action-specific feedback.
- Reformatted and typed the new finding store/service modules.
- Made real-browser integration tests skip when the Python package exists but Chromium cannot launch.

## Verification

- Focused findings and JavaScript suite: 12 passed, 0 failed.
- Complete regression: 838 passed, 45 skipped, 1 xpassed, 0 failed.
- `python -m compileall -q src tests`: passed.
- Startup smoke: `/health` and `/dashboard` returned HTTP 200.
- Ruff, coverage, formatter, and wheel build remain unavailable in this execution image; no results are fabricated.

## Remaining Environment Limits

The graphical Chromium runtime, Ruff, coverage, pip, and Black are unavailable. Browser integration tests are now accurately skipped rather than failing when Chromium cannot launch. Source/semantic UI checks and Node syntax validation remain available.
