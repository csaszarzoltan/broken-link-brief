# Validation Results

Validated on 2026-08-01 in the handoff environment. The results include the 1.0.2 recent-page, 1.0.3 change-history, and 1.0.4 actionable-detail increments.

## Automated tests

```text
317 passed, 1 xpassed in 24.13s
```

Command:

```bash
python -m pytest -q --disable-warnings
```

The xpass is a pre-existing test marked as expected-to-fail whose behavior is now implemented. No test failed.

## Static validation

Python bytecode compilation is included in packaging validation. Ruff is declared in the project's development dependencies, but the executable was not installed in the handoff environment, so lint could not be rerun there. Install development dependencies and run `ruff check src tests` before release if the release environment does not already apply that gate.


## Dashboard JavaScript syntax

The embedded dashboard script was extracted and validated with:

```bash
node --check dashboard.js
```

A regression test now performs this validation automatically whenever Node.js is available.
