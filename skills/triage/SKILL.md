---
name: triage
description: Re-run only the Opus verification + consolidation stages of BugHunter against saved normalized candidates, without re-scanning. Use when the user has tuned the verifier or consolidator prompts and wants to re-triage existing candidates, or when they invoke `/bughunter:triage`.
allowed-tools: Read, Glob, Grep, LS, Write, Edit, TodoWrite, Agent
---

You are re-running only the triage (Opus verification + consolidation) portion of the BugHunter pipeline. This is for iteration: the scanner output is fixed; you are re-classifying it and re-rendering the report.

**This skill does not re-scan.** Scanner data is taken as-is from `.bughunter/candidates-normalized.json`.

## Preconditions

1. Read `.bughunter/candidates-normalized.json`. If missing, print:
   > "No normalized candidates found. Run `/bughunter:hunt` first (or resume an interrupted run)."
   and stop.

2. Read `.bughunter/inventory.json` to recover scope and `repo_summary` if needed.

3. Verify the files cited by candidates still exist. For any that no longer exist, record the candidate_id and drop it from the triage set with a note in the run log.

## Workflow

Create a TodoWrite list with: "verify", "consolidate", "write report".

### 1. Verify

For each candidate in `candidates-normalized.json`:

1. Read the cited files (just line spans + ~20 lines of context).
2. Dispatch `bug-verifier` via the `Agent` tool with the candidate and the file contents.
3. Collect the verdict JSON.
4. Second opinion: if `verdict == "needs_context"` with `extra_context_needed` populated, parent reads those paths and re-dispatches once. If still `needs_context`, treat as `suspected`.
5. Append to `.bughunter/verified.jsonl` (overwrite any existing file at start of this step).

Parallelize up to 4 verifier dispatches per batch.

Mark "verify" completed.

### 2. Consolidate

1. Filter `verified.jsonl` to exclude `verdict == "rejected"`.
2. Count verdicts.
3. Build `run_metadata`:
   ```json
   {
     "generated_at": "<ISO 8601 now>",
     "scope": "<from inventory.json>",
     "chunks_scanned": <from existing scan-state or inventory>,
     "scanner_invocations": <from existing scan-state if available, else null>,
     "candidates": <from candidates-normalized.json>,
     "final_findings": <count after filtering rejected>
   }
   ```
4. Dispatch `findings-consolidator` via `Agent` with `verified_findings` and `run_metadata`.

Mark "consolidate" completed.

### 3. Write report

1. The consolidator returns raw Markdown. Write it to `bughunter-report.md` at repo root.
2. Append a triage entry to `.bughunter/run-log.md` (do not overwrite any prior log) with timestamp, verdict breakdown, and note that this was a triage-only rerun.

Mark "write report" completed.

## Output to chat

Print a short summary:

```
BugHunter triage complete.

  Candidates re-verified: K
  Verdict breakdown:
    - Confirmed: <n>
    - Likely:    <n>
    - Suspected: <n>
    - Rejected:  <n>

Report rewritten: bughunter-report.md
Run log appended: .bughunter/run-log.md
```

## Hard rules

- **Never** re-dispatch scanners in triage mode. If the user needs fresh scanner output, they should run `/bughunter:hunt`.
- **Never** modify `candidates-normalized.json` during triage — it is the input artifact.
- **Never** recursively re-dispatch the verifier from within itself; the parent handles second-opinion rounds.
