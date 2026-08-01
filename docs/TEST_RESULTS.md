# Validation Results

Validated on 2026-08-01 in the handoff environment.

## Automated tests

```text
304 passed, 1 xpassed in 24.29s
```

Command:

```bash
python -m pytest -q --disable-warnings
```

The xpass is a pre-existing test marked as expected-to-fail whose behavior is now implemented. No test failed.

## Static validation

Python bytecode compilation is included in packaging validation. Ruff is declared in the project's development dependencies, but the executable was not installed in the handoff environment, so lint could not be rerun there. Install development dependencies and run `ruff check src tests` before release if the release environment does not already apply that gate.
