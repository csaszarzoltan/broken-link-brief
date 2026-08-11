# Features Done

## Features Done (this pass)
- Active job heartbeats: running jobs renew their lease on a dedicated thread while source requests are blocked.
- Applied detailed-probe policy: effective timeout, attempt count, temporary statuses, and exponential backoff govern network evidence collection.

## Sources
- research-findings.md items addressed: durable long-running scans; timeout and HTTP 429/5xx false-positive controls.
- implementation-plan.md requirements addressed: PR-1 active heartbeat and the request-policy execution subset of PR-4.
- user stories covered: US-001 PASS for blocked-request heartbeat; US-004 PASS for timeout/attempt/status/backoff controls.
- CHANGELOG.md section this maps to: v1.4.2 (2026-08-11).
