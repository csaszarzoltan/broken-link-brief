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

## Saved project delivery in 1.1

`projects.py` adds a durable SQLite adapter for named recurring target groups. The main HTTP application now exposes authenticated list, create, and archive operations, and the dashboard can load saved targets directly into single or batch scan mode.

The project database is independent of legacy JSONL history, so upgrading from 1.0.x is additive. Set `BROKENLINKBRIEF_PROJECT_DB` to a persistent writable path in production. Project archival is non-destructive and does not remove scan history.

### Project lifecycle in 1.1.1

Saved projects can be edited without changing their IDs. Archived projects are available through a separate view and can be restored. All update paths retain the same validation and security boundary as project creation.

### One-action project scans in 1.1.2

Active projects can start scanning immediately. Project API responses also include a compact latest-state summary derived from retained history. Use `BROKENLINKBRIEF_HISTORY_DIR` to place JSONL history on persistent storage.

### Portable project configuration in 1.1.3

Project names and targets can be exported as a versioned JSON configuration and imported into another installation. Portable files intentionally omit runtime history and identity. Import creates a new project and reruns all target validation.

### Project duplication in 1.1.4

Projects can be copied with one action. The duplicate receives a new ID, remains independent of the source, starts active, and retains only the name-derived copy label and ordered targets.
