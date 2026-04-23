# Planted Bugs Fixture

Small mixed-language codebase (Python + TypeScript) used to regression-test BugHunter.

See `EXPECTED.md` for the full list of planted bugs and the acceptance bar for a successful BugHunter run.

## Layout

```
planted-bugs/
├── EXPECTED.md          # Planted bug manifest + acceptance bar
├── README.md            # This file
├── src/
│   ├── payments.py      # F1 — swallowed retry exception
│   ├── pagination.ts    # F2 — off-by-one pagination
│   ├── config_loader.py # F3 — unvalidated input to yaml.load
│   ├── auth.ts          # F4 — critical path with zero test coverage
│   ├── inventory.py     # F5 — partial mutation, no rollback
│   ├── storage.ts       # F6 — missing env key crash
│   ├── http_client.py   # F7 — fallback masks original error class
│   ├── file_cache.py    # F8 — check-then-use race (stretch)
│   ├── metrics.ts       # F9 — precision-losing type coercion (stretch)
│   ├── utils.py         # Control — no bugs
│   └── constants.ts     # Control — no bugs
└── tests/
    └── test_utils.py    # Tests that cover utils.py (only).
```

## Why this fixture exists

Automated bug-finding tools are trivially fooled by any prompt change. This fixture converts BugHunter prompt tuning from "did the output look smart?" into a falsifiable pass/fail test: did BugHunter find ≥7 of 7 required planted bugs in Confirmed or Likely, with ≤2 false positives in Confirmed and ≤5 across Confirmed + Likely combined?

Use it after any change to scanner prompts, the verifier rubric, or the consolidator report template.
