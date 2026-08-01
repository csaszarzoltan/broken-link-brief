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
