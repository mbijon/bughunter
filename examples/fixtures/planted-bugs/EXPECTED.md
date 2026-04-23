# Planted Bugs — Expected Findings

This fixture is a regression test bed for BugHunter. Each bug below is intentionally planted in the listed file. A successful BugHunter run should find bugs **F1–F7** in either the **Confirmed** or **Likely** section of `bughunter-report.md`. Stretch bugs F8–F9 should appear at least in **Suspected but Unlikely**.

## Acceptance bar

A fixture run is acceptable if **all** of:

- ≥ 7 of 7 required planted bugs (F1–F7) appear in Confirmed or Likely.
- ≤ 2 false positives in Confirmed.
- ≤ 5 false positives across Confirmed + Likely combined.
- Coverage matrix shows 100% covered or explicitly skipped with reason.
- Report follows schema exactly.
- No agent invocation errors in `run-log.md`.

---

## Required bugs

### F1 — Swallowed exception in retry loop

- **File:** `src/payments.py`
- **Lines:** 20–39 (the `charge_card` function)
- **Label:** swallowed retry exception
- **Description:** `charge_card` retries up to 3 times, catches every exception with a bare `except:`, and returns `None` after the loop exhausts — callers have no way to distinguish success-returning-nothing from total failure.

### F2 — Off-by-one in pagination boundary

- **File:** `src/pagination.ts`
- **Lines:** 13–39 (the `paginate` function; bug at the loop on line 30)
- **Label:** off-by-one pagination
- **Description:** `paginate` uses `<` instead of `<=` on the upper boundary, so the last item of every page is skipped when the page exactly fills.

### F3 — Unvalidated input passed to parser

- **File:** `src/config_loader.py`
- **Lines:** 9–31 (the `load_user_config` function; unsafe `yaml.load` at line 29)
- **Label:** unvalidated config input
- **Description:** `load_user_config` reads a user-supplied path and passes the raw content directly into `yaml.load` (unsafe) without schema validation, type checking, or size limits. Hostile input can execute arbitrary code.

### F4 — Critical path with zero test coverage

- **Files:** `src/auth.ts` and (absent) `tests/auth.test.ts`
- **Lines:** entire file `src/auth.ts`
- **Label:** untested auth critical path
- **Description:** `src/auth.ts` contains session-validation logic and token expiry checks. No test file exists for it. Every branch — including the token-expiry branch and the invalid-signature branch — is completely untested.

### F5 — Partial state mutation on failure (no rollback)

- **File:** `src/inventory.py`
- **Lines:** 25–44 (the `transfer_items` function)
- **Label:** partial mutation no rollback
- **Description:** `transfer_items` decrements from the source inventory, then attempts to increment the destination. If the destination write raises, the source decrement is never rolled back, permanently leaking inventory.

### F6 — Config/env assumption that breaks on missing key

- **File:** `src/storage.ts`
- **Lines:** 29–38 (the `getStorageClient` function)
- **Label:** missing env key crash
- **Description:** `getStorageClient` reads `process.env.STORAGE_BUCKET` and passes it directly into a downstream constructor without a default or presence check. When the env var is unset, the resulting `undefined` propagates and causes a confusing downstream crash far from the root cause.

### F7 — Retry/fallback that masks the original error class

- **File:** `src/http_client.py`
- **Lines:** 17–32 (the `fetch_with_fallback` function)
- **Label:** fallback masks error
- **Description:** `fetch_with_fallback` catches any exception from the primary endpoint and calls `fetch_from_backup()`. If the backup also fails, the caller sees only the backup's error — the original root cause from the primary is lost with no logging.

---

## Stretch bugs

### F8 — Race window between check and use

- **File:** `src/file_cache.py`
- **Lines:** 7–25 (the `read_cached_file` function)
- **Label:** check-then-use race
- **Description:** `read_cached_file` calls `os.path.exists(path)` then `open(path)`. Between the two calls another process can delete the file, causing a `FileNotFoundError` that defeats the purpose of the check.

### F9 — Silent type coercion losing precision

- **File:** `src/metrics.ts`
- **Lines:** 19–32 (the `recordLatency` function)
- **Label:** precision loss coercion
- **Description:** `recordLatency` accepts a number and writes it to a field typed as `number` in a JSON payload. Large nanosecond values arrive as `bigint` in calling code but are silently coerced to `Number` via `+value`, losing precision above 2^53.

---

## Not-bugs (control cases)

These files contain *no* intentional bugs. Any BugHunter finding in these files is a false positive.

- `src/utils.py` — simple pure utility functions.
- `src/constants.ts` — numeric and string constants.
- `tests/test_utils.py` — tests that actually pass.

If a run flags more than one issue in these files, the false positive budget is already mostly spent.
