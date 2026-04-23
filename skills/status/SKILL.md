---
name: status
description: Report the current state of an in-progress or completed BugHunter scan. Reads .bughunter/ and prints a short summary. Use when the user runs `/bughunter:status`.
allowed-tools: Read, Glob, LS
---

You are printing a BugHunter status report. Keep it short and factual.

## Steps

1. **Check for `.bughunter/`**:
   - If absent, print `No BugHunter run in progress or completed in this repo.` and stop.

2. **Read `.bughunter/scan-state.json`** if present.

3. **Read `.bughunter/inventory.json`** if present — note scope, file count.

4. **Read `.bughunter/coverage-matrix.json`** if present. Compute:
   - total cells = `chunks × lenses`
   - covered cells
   - skipped cells
   - pending cells

5. **Count lines in `.bughunter/candidates.jsonl`** if present (each line = one raw finding).

6. **Read `.bughunter/candidates-normalized.json`** if present — note candidate count after dedup.

7. **Count lines in `.bughunter/verified.jsonl`** if present. Tally by verdict.

8. **Check `bughunter-report.md`** at repo root — exists?

## Output format

Print a single block. Scale detail to the run's state:

```
BugHunter status

  Step:            <from scan-state.json>
  Scope:           <from inventory.json>
  Files in scope:  <N>
  Chunks:          <from chunks.json>

  Coverage matrix: <covered>/<total> cells covered (<skipped> skipped, <pending> pending)
  Raw candidates:  <jsonl line count>
  Normalized:      <count>
  Verified:        <count> (confirmed <n>, likely <n>, suspected <n>, rejected <n>)

  Report:          bughunter-report.md [exists | not yet written]
  Last update:     <mtime of scan-state.json>
```

If any file is missing, render its row as `—`. Do not fabricate numbers.

Do not dispatch any agents. This skill is read-only on `.bughunter/`.
