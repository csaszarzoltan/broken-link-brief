# Scan Policies

Each active project has built-in defaults until a version is saved with `PUT /api/projects/{project_id}/scan-policy`. Policies bound timeout (1-60 seconds), concurrency (1-20), attempts (1-3), backoff (0-10 seconds), cache TTL (0-86400 seconds), Retry-After handling, and retryable temporary statuses. Exact-host overrides take precedence over project defaults; wildcards and path rules are rejected. `GET /api/projects/{project_id}/scan-policy` returns the active immutable version. Job records retain the policy version used for auditability.

## Observation cache

The project-scoped observation cache is keyed by normalized URL and effective-policy fingerprint. TTL zero disables caching. Only RECOVERED and CONFIRMED_BROKEN observations are eligible; transient and inconclusive evidence is never cached or shared across projects.

## Applied detailed-probe fields

`timeout_seconds`, `max_attempts`, `temporary_statuses`, and `backoff_seconds` now govern detailed link probes when an effective policy is supplied. Backoff is exponential and capped at 30 seconds. Legacy callers without a policy retain existing bounded defaults.
