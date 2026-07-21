# Changelog

## 0.5.0 — 2026-07-21

### Features
- Add Railway deployment support: `railway.toml`, `Dockerfile`, and `PORT` env var binding
- Add `__main__` block to `app.py` that reads `PORT` from environment and binds to `0.0.0.0`
- Add Docker support with multi-stage-ready Dockerfile

### Fixes
- Fix import paths: replace `apps.brokenlinkbrief` with `brokenlinkbrief` across all modules and tests
- Fix `pyproject.toml` build backend: replace invalid `setuptools.backends._legacy:_Backend` with `setuptools.build_meta`
- Fix `conftest.py` to add `src/` directory to `sys.path` for test imports

### Tests
- Add `tests/test_deployment.py` with Railway readiness smoke tests (health endpoint, PORT binding)
- Full suite: 40 passed, 1 xpassed, zero regressions

### Docs
- Add Railway and Docker deployment sections to `README.md`
- Add deploy button for one-click Railway deployment

## 0.4.3 — 2026-07-20

### Features
- Add JSONL (JSON Lines) response format to the BrokenLinkBrief `/scan` endpoint: `GET /scan?url=<target>&format=jsonl` returns one JSON object per line with `Content-Type: application/x-jsonlines`
  - Each line is a self-contained JSON object with fields `url`, `status`, `reason`, and `location`
  - No wrapping array and no trailing newline — safe for streaming and line-by-line processing
  - Pipe-friendly: parseable with `json.loads()` per line, or by tools like `jq` and `awk`
  - Follows the same auth pattern as other formats (optional bearer or query token)
- Add `render_jsonl` helper in `apps/brokenlinkbrief/package.py` for streaming-friendly JSONL export; follows the existing `render_csv`/`render_markdown` pattern
- Add `_write_jsonl` handler in `apps/brokenlinkbrief/app.py` following existing CSV/Markdown route patterns, with `Content-Type: application/x-jsonlines`

### Docs
- Add JSONL row to the endpoints table, curl example, and sample JSONL output in `README.md`
- Add "JSONL export" section with `render_jsonl` usage example and Content-Type note in `README.md`
- Expand this changelog entry with design rationale (streaming, line-oriented, pipe-friendly)

### Tests
- Add `tests/test_jsonl_scan.py` with 8 tests: 3 interface, 4 behavioral, 1 regression guard
- Full suite: 53 passed, 1 xpassed, zero regressions; ruff clean

## 0.4.2 — 2026-07-20

### Features
- Add JSONL usage logging for successful `/scan` requests with timestamp, target URL, result count, broken count, format, latency, and status, routed by `BROKENLINKBRIEF_LOG_FILE` or `stderr`

### Docs
- Document `BROKENLINKBRIEF_LOG_FILE` in `apps/brokenlinkbrief/README.md`

## 0.4.1 — 2026-07-20

### Features
- Route `format=markdown` on the BrokenLinkBrief `/scan` endpoint, returning `text/markdown; charset=utf-8` using the existing `render_markdown` helper

### Docs
- Update README endpoint table to list `format=markdown` alongside JSON and CSV

## 0.4.0 — 2026-07-20

### Features
- Add `format=csv` export to the BrokenLinkBrief `/scan` endpoint, returning `text/csv` with a stable `url,status,reason,location` header row
- Add `render_csv` exporter to `apps/brokenlinkbrief/package.py` and re-export it from `apps/brokenlinkbrief/export.py`

### Fixes
- Harden CSV output against spreadsheet formula injection (CWE-1236): prefix fields starting with `= + - @ \t \r` with an apostrophe so attacker-influenced `reason`/`location` values render as literal text

### Tests
- Add `tests/test_brokenlinkbrief_csv_endpoint.py` with CSV interface/behavior and formula-injection neutralization regression tests

### Docs
- Refresh `analysis/analysis-brief.md` and `analysis/research-brief.md` for the structured-export increment
- Add CSV export analysis retrospective

## 0.3.0 — 2026-07-20

### Features
- Add `BrokenLinkBrief` micro-feature: `/scan?url=` endpoint with optional bearer auth, markdown brief export, and `/health` smoke-test (apps/brokenlinkbrief/)
- Add research brief and analysis brief artifacts under `analysis/`

### Fixes
- Resolve `render_markdown` spec conflict between export behavioral tests and existing unit tests; align export module with canonical implementation

### Tests
- Add behavioral tests for `BrokenLinkBrief` export module covering interface contract, markdown formatting, and empty-results behavior

### Docs
- Add `docs/CONTINUOUS-DELIVERY.md` for autonomous delivery workflow
- Add `AGENTS.md` with project context for autonomous swarm
- Normalize analysis brief and research brief formatting

## 0.1.0 — 2026-07-19

### Features
- Initialize project scaffold: `apps/`, `packages/`, `docs/`, `infra/`, `tests/`, `src/`
- Add `repo_productization_kit` with sanitizers and release helpers
- Add `ruff` and `pytest` configuration
