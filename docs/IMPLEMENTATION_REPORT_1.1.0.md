# BrokenLinkBrief 1.1.0 Implementation Report

## 1. Product understanding

BrokenLinkBrief serves developers, SEO/content operators, and site administrators who scan public pages, review link failures, compare history, export evidence, and automate checks. The 1.0.7 dashboard already supported single and batch scans, recent pages, source-aware filtering, history, and exports.

**Confirmed observation:** Repeat users could rescan recent pages but could not save a named, durable group of targets. Recent pages represented activity history rather than user intent.

**Inference:** Users who monitor the same websites repeatedly need stable projects to avoid reconstructing target lists and to create a foundation for later schedules, ownership, and notification policy.

## 2. Improvement summary

### Critical improvement implemented

- Added durable saved projects for one or many recurring scan targets.
- Added a browser create, list, load, and archive workflow.
- Added authenticated project APIs and SQLite persistence.

### Secondary improvements implemented

- Normalized and deduplicated targets while preserving their first-entered order.
- Rejected embedded target credentials.
- Applied existing SSRF validation before API persistence.
- Selected the appropriate scan mode automatically when a project is loaded.
- Added explicit loading, empty, success, validation, and error feedback.
- Kept archival non-destructive so scan history remains available.

### Not implemented yet

- Project editing and restoration of archived projects.
- Project schedules and notification policies.
- Organization ownership and project RBAC.
- Durable scan jobs and progress.
- Finding assignment and repair verification.

## 3. Requirements

### Must have

- **BR-PROJ-01:** Users can preserve recurring target groups as named projects.
- **UR-PROJ-01:** A user can create a project with 1 to 50 public targets.
- **UR-PROJ-02:** A user can load project targets into single or batch scan mode with one action.
- **FR-PROJ-01:** Projects and target order survive process restarts.
- **FR-PROJ-02:** Duplicate normalized targets are stored once.
- **SEC-PROJ-01:** API targets pass SSRF validation and may not contain URL credentials.
- **A11Y-PROJ-01:** Project loading, empty, success, validation, and error states are announced.
- **QA-PROJ-01:** Store, API, browser contract, security, and archive behaviors have automated tests.

### Should have

- **UR-PROJ-03:** Projects can be archived without deleting historical scan evidence.
- **OPS-PROJ-01:** Operators can configure a persistent database path.

## 4. Implementation details

### Added

- `src/brokenlinkbrief/projects.py`
  - Immutable `Project` model.
  - Target normalization.
  - SQLite schema and foreign-key enforcement.
  - WAL mode.
  - Create, get, list-active, and archive behavior.
- `tests/test_projects.py`
  - Unit, API integration, validation, persistence, UI contract, and archive tests.

### Changed

- `src/brokenlinkbrief/app.py`
  - Project dashboard panel and state feedback.
  - Project API endpoints.
  - Automatic scan-mode selection when loading targets.
  - Archive confirmation and refresh.
- `README.md`, `CHANGELOG.md`, `docs/README.md`, and `docs/PRODUCT_FEATURES.md`.
- `.gitignore` and `.dockerignore` to exclude SQLite runtime files.
- Package version to `1.1.0`.

### Architecture decisions

- SQLite was selected because the codebase already uses it for product capability stores and requires no new runtime dependency.
- Projects are additive and do not replace JSONL history in this increment.
- API validation uses the existing scan-target policy so saved targets cannot bypass the current SSRF boundary.
- Archive is a state transition, not a physical delete.

## 5. Testing

TDD sequence:

1. Added failing tests for project persistence, normalization, validation, API create/list, SSRF rejection, browser workflow, archival, and archive UI.
2. Confirmed failure before implementation.
3. Implemented the smallest coherent store and API.
4. Added dashboard delivery and archive behavior.
5. Re-ran targeted tests and embedded JavaScript syntax validation.
6. Ran the complete regression suite.

Coverage gaps:

- No real-browser automation was added.
- SQLite concurrent-write load testing remains future work.
- Manual screen-reader validation is still recommended.

## 6. Packaging and migration

The handoff ZIP contains source, tests, documentation, configuration, and both product and implementation reports. Runtime databases, history, caches, bytecode, and temporary files are excluded.

Upgrade is additive:

- No schema migration is needed for existing JSONL history.
- On first project API or dashboard use, the configured SQLite project schema is created automatically.
- Set `BROKENLINKBRIEF_PROJECT_DB` to a persistent writable location before production deployment.

## 7. Continued increment: 1.1.1 project lifecycle completion

The initial saved-project increment removed repeated target entry, but users still needed a safe way to correct project names or target lists and reverse archival. Version 1.1.1 completes this daily lifecycle.

### Requirements added

- **UR-PROJ-04, Must:** A user can edit a project's name and ordered targets without changing its stable ID.
- **UR-PROJ-05, Must:** A user can browse archived projects and restore one to active use.
- **UX-PROJ-02, Must:** Edit mode is explicit, cancellable, and reuses the accessible project form.
- **SEC-PROJ-02, Must:** Updated targets pass the same normalization, credential, count, and SSRF checks as creation.
- **QA-PROJ-02, Must:** Store, API, and dashboard lifecycle behaviors have failing-first automated tests.

### Implementation details

- Extended `ProjectStore` with `update()`, `restore()`, and `list_archived()`.
- Added authenticated PUT and restore routes.
- Added browser Edit, Cancel edit, Show archived, Show active, and Restore actions.
- Kept project IDs stable across edits and preserved scan history across archive/restore transitions.

## 8. Continued increment: 1.1.2 one-action project scanning

Version 1.1.2 removes the final repeated step in the saved-project workflow. Users no longer need to load targets and then submit the scan form. Active projects can be scanned directly, and each card communicates whether the project has ever been scanned and how many latest-snapshot links need attention.

### Requirements added

- **UR-PROJ-06, Must:** A user can start a saved project scan with one action.
- **UX-PROJ-03, Must:** Project cards show a concise latest health state or an explicit Never scanned state.
- **FR-PROJ-05, Must:** A project summary aggregates only the latest retained scan for each target.
- **OPS-PROJ-02, Must:** History location can be configured for persistent production storage.
- **QA-PROJ-03, Must:** Aggregation, empty history, API output, and browser quick-scan contracts have failing-first tests.

### Implementation details

- Added `ProjectStore.summarize()` using the latest history record for every target.
- Enriched project API items with `scan_summary`.
- Added `runProjectScan()` and a primary project-card action.
- Added `BROKENLINKBRIEF_HISTORY_DIR` support to `HistoryStore` while preserving `.history` as the default.

## 9. Continued increment: 1.1.3 portable project configuration

Version 1.1.3 supports repeat setup across installations without exporting runtime or sensitive state. Users can download a minimal versioned project configuration and import it as a new project.

### Requirements added

- **UR-PROJ-07, Should:** A user can export and import reusable project configuration through the dashboard.
- **DI-PROJ-01, Must:** Portable configuration has an explicit schema version.
- **SEC-PROJ-03, Must:** Imports use the same validation and SSRF boundary as project creation.
- **PRIV-PROJ-01, Must:** Portable exports omit runtime identifiers, timestamps, history, archive state, findings, and secrets.
- **QA-PROJ-04, Must:** Store, schema, API, security, and browser contracts have failing-first tests.

### Implementation details

- Added `ProjectStore.export_configuration()` and `import_configuration()`.
- Added authenticated export and import API routes.
- Added browser JSON download and file-selection workflows.
- Unsupported schemas fail explicitly rather than being guessed or silently upgraded.

## 10. Continued increment: 1.1.4 project duplication

Version 1.1.4 reduces repetitive setup when users need a project variant with the same targets. Both active and archived projects can be duplicated, while the source project remains unchanged.

### Requirements added

- **UR-PROJ-08, Should:** A user can duplicate a project in one action.
- **FR-PROJ-09, Must:** A duplicate receives a new identity and starts active.
- **FR-PROJ-10, Must:** Duplicate naming is deterministic and avoids existing project names.
- **PRIV-PROJ-02, Must:** Duplication copies configuration only, not history or runtime state.
- **QA-PROJ-05, Must:** Store, naming, API, error, and browser contracts have failing-first tests.

### Implementation details

- Added `ProjectStore.duplicate()`.
- Added the authenticated duplicate route.
- Added a browser **Duplicate** action for active and archived projects.
- After duplication, the dashboard returns to the active project list and announces the generated copy name.

## 11. Continued increment: 1.1.5 pinned projects

As the saved-project list grows, recency alone is not enough to keep the most operationally important projects easy to reach. Version 1.1.5 adds persistent pinning while retaining recent-update ordering for the remaining projects.

### Requirements added

- **UR-PROJ-09, Should:** A user can pin frequently used active or archived projects.
- **UX-PROJ-04, Must:** Pinned projects appear before unpinned projects and the action label reflects current state.
- **FR-PROJ-12, Must:** Pin state survives restarts and can be changed independently of project content.
- **DATA-PROJ-01, Must:** Existing project databases migrate without manual intervention or data loss.
- **FR-PROJ-13, Must:** Duplicated and imported projects begin unpinned.
- **QA-PROJ-06, Must:** Persistence, ordering, migration, copy behavior, API, and browser contracts have failing-first tests.

### Implementation details

- Added the `pinned` field to the immutable Project model.
- Added automatic SQLite column migration using `PRAGMA table_info` and `ALTER TABLE`.
- Added `ProjectStore.set_pinned()` and pin-first list ordering.
- Added authenticated pin API handling with strict boolean payload validation.
- Added Pin and Unpin dashboard actions with live status feedback.
