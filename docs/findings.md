# Trusted Findings API

BrokenLinkBrief 1.3.0 turns repeated, confirmed link failures into durable project findings. Existing scan and export contracts remain unchanged.

## Classification

Detailed probes retain bounded HEAD/GET attempts. Repeated 404 or 410 evidence is `CONFIRMED_BROKEN`; transport-only evidence is `TRANSIENT`; a later success is `RECOVERED`; conflicting restricted and successful probes are `BOT_BLOCKED`; remaining evidence is `INCONCLUSIVE`. Only confirmed failures create findings.

## Project scan

A saved single-target project scan sends its project ID with `/scan`. The server verifies that the source belongs to the active project, extracts source occurrences, gathers evidence, and upserts findings. Ad-hoc scans do not create project findings.

## Endpoints

All endpoints use the existing optional bearer/query-token authentication.

- `GET /api/findings?project_id=<id>&state=<state>&classification=<classification>&q=<text>&limit=50&offset=0`
- `GET /api/findings/<id>`
- `POST /api/findings/<id>/acknowledge` with `{"version": 1}`
- `POST /api/findings/<id>/assignment` with `{"version": 1, "assignee": "Alice"}`
- `POST /api/findings/<id>/ignore` with `{"version": 1, "reason": "Expected outage", "expiry": "2026-09-01"}`
- `POST /api/findings/<id>/reopen` with `{"version": 1}`
- `POST /api/findings/<id>/verify` with `{"version": 1}`

Mutations use optimistic versions. A stale version returns HTTP 409. Invalid payloads return 400 and missing findings return 404.

## Verify Fix

Verification rechecks the target and active source pages. `RECOVERED` and proven `REMOVED_FROM_SOURCE` resolve the finding; `STILL_BROKEN` remains active; insufficient evidence returns `INCONCLUSIVE` without resolving it. Stored URLs are treated as untrusted and pass the same scan validation boundary before application-initiated use.

## Persistence and privacy

Tables are added idempotently to `BROKENLINKBRIEF_PROJECT_DB`. Existing project rows are preserved. Findings retain bounded anchor/context text, evidence, verification history, and audit events. They do not store headers, cookies, response bodies, or credentials. Back up the SQLite database before upgrades.
