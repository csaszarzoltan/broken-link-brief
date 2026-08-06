# Features Done

## Features Done (this pass)
- SSRF-safe trusted findings: every extracted or stored URL is revalidated before project finding or Verify Fix network access.
- Complete finding lifecycle safeguards: project integrity, archived-project read-only behavior, expired-ignore reopening, occurrence search, and occurrence reconciliation.
- Verified repair outcomes: recovered, removed from source, still broken, and inconclusive paths now have focused regression coverage.
- Findings UX completion: classification filter, verification/audit history, and action-specific status feedback.
- Environment-correct browser tests: SPA integration tests skip only when Chromium is genuinely unavailable.

## Sources
- research-findings.md items addressed: trustworthy findings, source-aware repair context, durable lifecycle, targeted verification.
- implementation-plan.md requirements addressed: PR-1, PR-2, PR-3 security, lifecycle, verification, UI, and regression criteria.
- CHANGELOG.md section this maps to: v1.3.1 (2026-08-06).
