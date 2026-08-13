# Refactor Baseline — 2026-08-13

**Task:** t_c7a458ed — Refactor broken-link-brief to fix P0 audit findings
**Methodology:** methodology_version 1.1 (roles/gates/MUST/SHOULD/MAY, exception protocol, enforcement mapping)
**Rule:** METH-REF-002 (refactoring baseline test kötelező)
**Commit under test:** `bc7cf9a` (Merge branch 'main' of https://github.com/csaszarzoltan/broken-link-brief)

## Environment

- Repo: `/home/zoltan/broken-link-brief` (worktree at `t_c7a458ed` workspace)
- Python: repo `.venv` (3.11) — METH-VENV-002 (sosem a rendszer python3)
- Dependencies: `pip install -e ".[dev]"` + `pyyaml` (needed by scheduler_config tests, not declared in `[dev]` — baseline env gap) + `playwright` (optional extra, installed; browsers in `~/.cache/ms-playwright`)

## Test suite baseline (METH-REF-002)

Command: `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q --tb=line`

Result: **912 passed, 42 skipped, 1 xpassed, 0 failed** (115s)

Notes:
- 6 tests FAIL in a bare `.[dev]` venv (missing pyyaml / playwright): `tests/test_scheduler_config.py::TestLoadProjectsConfig::*` (3, ImportError fallback path) and `tests/test_spa_scanner.py::TestSpaScannerBehavior::{test_scan_page_js_rendered_links, test_scan_page_deduplicates_spa_and_raw_links, test_scan_page_dynamic_tabs_accordions}` (3, Playwright not installed). These are **environment gaps, not code regressions** — with the declared runtime extras installed the suite is fully green. This refactor will add `pyyaml>=6.0` to `[project.optional-dependencies].dev` so a clean `.[dev]` install reproduces the green baseline (AC: "existing test suite passes").

## Lint baseline (ruff)

Command: `PATH="$PWD/.venv/bin:$PATH" ruff check . --statistics`

Result: **858 errors** (898 per audit JSON — audit ran `--select` with the full default set; 40 findings are in non-`src` files like `docs/_debug.py`, `tools/`, `tests/`... no: audit counts `ruff check .`; the difference 898 vs 858 is because the audit used a ruff version with different default rules. The task AC is "`ruff check .` reports no errors" — target is 0 with the pinned config in pyproject.toml).

Breakdown (audit, counts match task body): E501 449, E702 209, E701 111, I001 62 (31 in current ruff), E402 13, F401 12, N802 9 (2 in current ruff — N802 vs N802+UP037 split), E401 7, F841 5, N818 4, SIM118 3, E703 2, B008 1, B011 1, B017 1, B904 1, A002 1, SIM115 1, W292 1, W293 1, UP012 1, UP015 1, UP037 1.

## Radon baseline (complexity)

Command: `PATH="$PWD/.venv/bin:$PATH" radon cc src/brokenlinkbrief -s -n D --total-average`

Result: **325 blocks analyzed, average B (5.34).** Problematic functions (target: all below E rank, i.e. <31):

| File | Function | Line | CC | Rank |
|---|---|---|---|---|
| src/brokenlinkbrief/app.py | `_Handler.do_POST` (method) | 1849 | 171 | F |
| src/brokenlinkbrief/app.py | `_Handler.do_GET` (method) | 1328 | 133 | F |
| src/brokenlinkbrief/app.py | `_Handler` (class) | 1327 | 68 | F |
| src/brokenlinkbrief/diff_detector.py | `DiffDetector._compute_diff` (method) | 117 | 43 | F |
| src/brokenlinkbrief/regression_detector.py | `RegressionDetector.detect` (method) | 55 | 27 | D |
| src/brokenlinkbrief/scheduler_config.py | `validate_project_config` (function) | 44 | 23 | D |
| src/brokenlinkbrief/scheduled_projects.py | `aggregate_scheduled_projects` (function) | 26 | 22 | D |

METH-REF-001: E/F complexity → refactor kötelező. Task AC: "Radon reports complexity below E rank for all 7 problematic functions" — for the D functions (21-30) that means below E rank is already satisfied, but they are on the audit's 7-function list; per task wording "bring maximum complexity below E rank" the hard gate is F→below E; D functions should be reduced to C (≤20) as SHOULD per §15.1 (refactor javasolt D-re). Plan: extract helpers from all 7; verified by `radon cc` output at the end.

## Vulture baseline

1 item: `app.py:2325` unused variable `format` (100% confidence) — will be resolved by the A002 rename of `log_message(format, ...)` → `message` (both findings share the same line).

## Behavior-change guard (METH-REF-003)

No new behavior, no feature work. All changes are mechanical (line wrapping, statement splitting, import sorting, helper extraction with identical logic). Verified by: full suite green at end + git diff review + radon comparison.
