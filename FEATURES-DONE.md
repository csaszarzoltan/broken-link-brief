# Features Done

## Features Done (this pass)
- Evidence-aware probing: bounded retry evidence is classified without changing legacy `LinkResult` or export contracts.
- Durable trusted findings: confirmed project failures upsert stable findings with source occurrences, evidence, lifecycle state, optimistic versions, and audit history.
- Targeted Verify Fix: target and active sources produce recovered, removed, still-broken, or inconclusive outcomes with durable verification records.
- Trusted Findings dashboard: project-scoped filtering, accessible detail review, live action feedback, responsive cards, safe external links, focus restoration, and reduced-motion support.
- Additive findings API: authenticated list, detail, acknowledge, assignment, ignore, reopen, and verify operations.

## Sources
- research-findings.md items addressed: evidence-aware false-positive reduction; source occurrence and repair context; durable finding lifecycle; targeted Verify Fix.
- implementation-plan.md requirements addressed: PR-1, PR-2, PR-3, selected UI/UX and compatibility contract.
- CHANGELOG.md section this maps to: v1.3.0 (2026-08-06).
