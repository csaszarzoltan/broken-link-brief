# Product feature implementation guide

The six research specifications are implemented as independent Python modules:

- `scheduler.py`: durable schedules and atomic due-work leasing.
- `triage.py`: HTML anchor occurrences, findings, and assignment conflict control.
- `confidence.py`: deterministic evidence classification.
- `policy.py`: outbound URL, DNS/IP, port, and redirect-policy validation.
- `governance.py`: organizations, memberships, capability authorization, and service credentials.
- `ci_gate.py` and `cli.py`: versioned baselines and CI outcomes.

The current release intentionally keeps these application services separate from the legacy HTTP handler. This preserves existing `/scan`, `/scan-batch`, history, webhook, and export behavior while providing stable APIs for the next delivery layer. SQLite files are runtime state and must not be committed.

## Security boundaries

Outbound targets must pass `validate_target`; redirect hops must be supplied to `validate_redirect_chain`. Service-key plaintext is generated once and only its SHA-256 digest is persisted. Organization capability checks deny access when membership is absent, including cross-organization access.

## Compatibility

The new modules are additive. Existing imports and endpoint response shapes are unchanged. The package version is 1.0.0 and installs the `brokenlinkbrief` console command.
