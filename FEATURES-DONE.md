# Features Done

## Features Done (this pass)
- Recoverable scan-job leases: worker ownership, heartbeat validation, exclusive claims, expired-lease recovery, and preservation of committed source results.
- Policy snapshot persistence: newly created jobs retain their complete immutable project policy document.
- Safe observation cache: project and policy-fingerprint scoped caching for recovered and confirmed-broken evidence only.

## Sources
- research-findings.md items addressed: durable asynchronous jobs; repeated-check efficiency; trustworthy evidence controls.
- implementation-plan.md requirements addressed: PR-1 lease recovery and the persistence/cache portions of PR-4.
- user stories covered: US-001 PASS; US-004 PARTIAL.
- CHANGELOG.md section this maps to: v1.4.1 (2026-08-11).
