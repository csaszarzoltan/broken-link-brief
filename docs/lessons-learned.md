# Lessons Learned — ruff P0 Audit Re-run (roadmap-010, "hamis komplett")

**Task:** t_91ac6b8a — Refactor broken-link-brief: ruff P0 audit re-run
**Date:** 2026-08-14
**Status:** resolved — `ruff check .` reports 0 errors under both verified ruff versions

## What was found

1. **The previous "completed" audit was a false positive ("hamis komplett").**
   The prior completion (t_c7a458ed, commit `4a579db`) verified with the repo's
   `.venv` ruff only. That version is **0.16.0** and reported `All checks passed!`
   — while the operator's verification toolchain (ruff **0.5.7** on `PATH`,
   the Hermes agent venv) reported **45 errors**. Both binaries read the same
   `pyproject.toml`, yet disagreed.

2. **The task body's error description was stale.**
   The card claimed "45 errors: E402 module-level import dominant, F401, F841,
   E501". The real 45 under ruff 0.5.7 were:
   | Code | Count | Meaning |
   |---|---|---|
   | I001 | 36 | Import block un-sorted/un-formatted (tests/) |
   | N802 | 7 | `do_*` function names should be lowercase |
   | SIM115 | 1 | `open()` without context handler (`app.py:207`) |
   | UP038 | 1 | Use `X | Y` in `isinstance` instead of `(X, Y)` |

3. **Root cause of the I001 storm: a ruff first-party auto-detection change.**
   - ruff **>= 0.6** auto-detects the `src/` layout, so `brokenlinkbrief`
     imports are first-party; the current code style (blank line between
     third-party and first-party blocks) is exactly what 0.16.0 wants.
   - ruff **0.5.7** does not auto-detect; it treated `brokenlinkbrief` as
     third-party and demanded the import blocks be merged (36 files).
   - This was a **toolchain-config disagreement, not a code defect** — the
     tests' import style was already correct. Fixing the code to satisfy
     0.5.7 would have broken 0.16.0.

## What was fixed

1. `pyproject.toml` — pinned the first-party package explicitly:
   ```toml
   [tool.ruff.lint.isort]
   known-first-party = ["brokenlinkbrief"]
   ```
   Makes import sorting identical across ruff versions.

2. `pyproject.toml` — documented the `do_*` HTTP handler protocol exception:
   ```toml
   [tool.ruff.lint.pep8-naming]
   ignore-names = ["do_GET", "do_POST", "do_PUT", "do_DELETE", "do_HEAD"]
   ```
   (`do_*` methods are the `http.server.BaseHTTPRequestHandler` stdlib API
   contract, not a naming violation. N802 without this exception is a
   false positive.)

3. `src/brokenlinkbrief/app.py:204` — SIM115: converted `_get_log_file()` into
   a `@contextmanager` (yields the open file, or `sys.stderr` when no log path
   is configured). Both call sites now use `with _get_log_file() as log_file:`
   — the try/finally manual-close dance is gone. Bonus: removed the
   `__import__("os")` hack — `os` is imported at module level already.

4. `tests/test_deployment.py:116` — UP038: `isinstance(x, (int, float))` →
   `isinstance(x, int | float)`. (Rule UP038 was removed in ruff 0.16.0; the
   change is still valid syntax on py3.10+ and keeps 0.5.7 happy too.)

## Verification (which ruff version, what result)

| Check | Command | Result |
|---|---|---|
| ruff 0.5.7 (operator PATH) | `ruff check .` | **0 errors** (was 45) |
| ruff 0.16.0 (repo `.venv`) | `./.venv/bin/ruff check .` | **0 errors** |
| ruff format (0.16.0) | `./.venv/bin/ruff format --check .` | 112 files formatted |
| Tests | `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/ -q` | **912 passed, 42 skipped, 1 xpassed** (127.6s) |

## Lessons for the next audit cycle

- **Always run the exact ruff version the operator/CI will use.** If a task
  says "current repo config", verify what `ruff check .` means for BOTH the
  repo `.venv` and the agent `PATH` ruff. A single-version green is not
  "komplett" when the verification lane uses another version.
- **Version-drift noise is a config problem, not a code problem.** When two
  ruff versions disagree on hundreds of findings (here 36/45 were I001), first
  diff the rule sets and the first-party detection, then fix config — not 36
  files of import churn that would flip-flop with the next version bump.
- **Pin the lint contract in `pyproject.toml`.** `known-first-party` +
  protocol-method `ignore-names` are cheap and make the outcome
  deterministic across ruff versions.
- **Do not trust the task body's error codes blindly.** The card listed
  E402/F401/F841/E501, none of which existed. Run the linter first and work
  from the real findings.
- SIM115/SIM118-style findings are usually a sign of hand-rolled
  open/close logic that a `@contextmanager` replaces more safely — prefer the
  structural fix over a `# noqa`.
