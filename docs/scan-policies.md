# Scan Policies

Each active project has built-in defaults until a version is saved with `PUT /api/projects/{project_id}/scan-policy`. Policies bound timeout (1-60 seconds), concurrency (1-20), attempts (1-3), backoff (0-10 seconds), cache TTL (0-86400 seconds), Retry-After handling, and retryable temporary statuses. Exact-host overrides take precedence over project defaults; wildcards and path rules are rejected. `GET /api/projects/{project_id}/scan-policy` returns the active immutable version. Job records retain the policy version used for auditability.
