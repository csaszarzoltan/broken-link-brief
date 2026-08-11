# Features Done

## Features Done (this pass)
- Durable scan jobs: persisted saved-project work, source progress, idempotent creation, cooperative cancellation, and failed-source retry.
- Versioned scan policies: validated project defaults and deterministic exact-host overrides with immutable versions.
- Scan jobs UI: accessible live job summaries with progress and recovery feedback.

## Sources
- research-findings.md items addressed: durable asynchronous jobs; project and host noise-control policies.
- implementation-plan.md requirements addressed: PR-1, PR-2, PR-3, and the persistence/API portion of PR-4.
- user stories covered: US-001, US-002, US-003, US-004.
- CHANGELOG.md section this maps to: v1.4.0 (2026-08-11).
