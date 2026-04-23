---
name: hunt
description: Perform a repository-scale bug hunt using the BugHunter multi-agent pipeline. Scans the entire codebase (or a scoped subset), produces a trustworthy final report of Confirmed, Likely, and Suspected bugs. Use when the user runs `/bughunter:hunt` or explicitly asks to hunt for bugs across the whole repo.
argument-hint: "[scope-glob-or-path]"
allowed-tools: Read, Glob, Grep, LS, Bash, Write, Edit, TodoWrite, Agent
---

You are orchestrating a BugHunter run. This skill's body is your **complete playbook** — execute it step by step. Do not skip steps. Do not stop early.

**Your scope argument** (if any) comes in as `$ARGUMENTS`. If empty, the scope is the entire repo.

---

## 0. Configuration (defaults)

These are your caps. Respect them. The user may override by passing scope or by answering prompts mid-run.

- `max_chunks` = 200
- `max_total_agent_invocations` = 600 (warning + pause at this threshold, not a hard stop)
- `max_files_in_scope` = 2000 (hard refuse without an explicit scope argument)
- `max_parallel_scanners` = 4

**The 5 lenses** (not including `code-explorer`, which is the planner):

1. `test-coverage-analyzer`
2. `silent-failure-hunter`
3. `qa-agent`
4. `code-fuzzing-agent`
5. `untested-code-tester`

---

## 1. Preflight

Create a TodoWrite list with the 9 steps in this document.

Mark step 1 as `in_progress`, then:

1. **Read repo context** once:
   - Read `CLAUDE.md` if it exists.
   - Read `README.md` if it exists.
   - Read top-level config files (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc.) if present.
   - Summarize this as a 2-4 sentence `repo_summary` you will pass to children.

2. **Identify source vs not-source**:
   - Source: code under repo-standard dirs (`src/`, `lib/`, `pkg/`, `internal/`, `app/`, or root-level source files).
   - Not-source (exclude): `node_modules/`, `vendor/`, `dist/`, `build/`, `target/`, `.venv/`, `__pycache__/`, `.git/`, `coverage/`, lockfiles, binary assets, generated code directories.
   - Apply `.gitignore` patterns if present (Read `.gitignore`; do not invoke `git` subcommands).

3. **Check for a resumable run**: if `.bughunter/scan-state.json` exists, Read it and offer to resume. If the user wants to resume, jump to whichever step `scan-state.json` indicates is next. Otherwise, start fresh.

4. **Create `.bughunter/` if not present**. Write an empty `scan-state.json` with `{"step": "inventory", "started_at": "<iso>"}`.

Mark step 1 as `completed`.

---

## 2. Inventory

Mark step 2 as `in_progress`.

1. Use `Glob` to enumerate source files under scope. The scope is:
   - If `$ARGUMENTS` is non-empty: treat it as a path or glob and limit the inventory to matching files.
   - Otherwise: the entire repo minus the exclude list from step 1.

2. Apply language-appropriate source-file globs. A language-agnostic starter set:
   - `**/*.py`, `**/*.ts`, `**/*.tsx`, `**/*.js`, `**/*.jsx`, `**/*.mjs`, `**/*.cjs`
   - `**/*.go`, `**/*.rs`, `**/*.java`, `**/*.kt`, `**/*.swift`
   - `**/*.rb`, `**/*.php`, `**/*.cs`, `**/*.cpp`, `**/*.c`, `**/*.h`, `**/*.hpp`
   - `**/*.sh`, `**/*.bash`
   - **Do not** include Markdown, JSON config, or lockfiles. **Do not** include test fixtures (`**/fixtures/**`, `**/__fixtures__/**`).

3. **File count check**:
   - If `file_count > max_files_in_scope` and `$ARGUMENTS` is empty: **halt** and tell the user:
     > "The repo has N source files — above the default 2,000 cap. Re-run with a scope argument, e.g., `/bughunter:hunt src/payments` or `/bughunter:hunt 'src/**/*.ts'`."
   - If over the cap but with a scope given, proceed.

4. Write `.bughunter/inventory.json`:
   ```json
   {
     "scope": "<$ARGUMENTS or 'whole repo'>",
     "file_count": N,
     "files": ["src/foo.py", "..."]
   }
   ```

5. Record a separate `test_files` list of adjacent test files (`**/test_*.py`, `**/*.test.ts`, `**/*_test.go`, etc.). Include these in `.bughunter/inventory.json` as `test_files`. They are *not* in scanning scope but scanners may receive them as reference context for test-coverage lenses.

Mark step 2 as `completed`. Update `scan-state.json` to `{"step": "chunking"}`.

---

## 3. Chunking

Mark step 3 as `in_progress`.

1. Dispatch `code-explorer` **once** via the `Agent` tool. Pass it:
   - `chunk_id`: N/A (planner, not a lens)
   - the `repo_summary` from preflight
   - the inventory (file list) from step 2
   - the instruction to produce a chunk map per its contract

2. Parse the returned JSON block. Validate:
   - Every file in `inventory.files` appears in exactly one chunk.
   - No chunk exceeds the implicit LOC bound (if code-explorer violated it, split the chunk yourself by splitting `files` evenly).
   - `chunk_id` values are unique strings.

3. If `chunk_count > max_chunks`, halt and tell the user the chunking produced too many chunks and they should tighten the scope.

4. Write `.bughunter/chunks.json`:
   ```json
   {
     "chunk_count": N,
     "chunks": [ /* from code-explorer, validated */ ]
   }
   ```

Mark step 3 as `completed`. Update `scan-state.json` to `{"step": "coverage_init"}`.

---

## 4. Coverage matrix init

Mark step 4 as `in_progress`.

Build `.bughunter/coverage-matrix.json`:

```json
{
  "chunks": {
    "<chunk_id_1>": {
      "test-coverage-analyzer": "pending",
      "silent-failure-hunter": "pending",
      "qa-agent": "pending",
      "code-fuzzing-agent": "pending",
      "untested-code-tester": "pending"
    },
    "<chunk_id_2>": { ... }
  }
}
```

Also create `.bughunter/candidates.jsonl` as an empty file.

Mark step 4 as `completed`. Update `scan-state.json` to `{"step": "scanner_loop", "invocation_count": 0}`.

---

## 5. Scanner loop (LOAD-BEARING)

Mark step 5 as `in_progress`. This is the core of the run.

**Termination condition**: every cell in the coverage matrix is either `"covered"` or `"skipped"`. Nothing else ends this loop — not bug count, not elapsed time, not "it looks like enough".

### Each iteration:

1. **Read** `.bughunter/coverage-matrix.json`.
2. **Pick a batch** of up to `max_parallel_scanners` (chunk, lens) pairs that are still `"pending"`. Prefer batching different lenses on the *same chunk* — this means the chunk's file contents, once Read into context, can be passed to multiple children in the same batch (context locality reduces cost and consistency drift).
3. **Read the chunk files once** (for each distinct chunk in the batch). Assemble their contents.
4. **Invocation count check**: if `invocation_count + batch_size >= max_total_agent_invocations`, halt and tell the user:
   > "BugHunter has used M of N allowed scanner invocations. Continue, stop and produce a partial report, or tighten scope?"
   Wait for the user's answer. If stop: skip to step 6 with whatever candidates are already in `candidates.jsonl`. If continue: proceed and raise the cap by 200.
5. **Dispatch the batch** in parallel via the `Agent` tool. Each dispatch passes:
   - the agent `name` (e.g., `silent-failure-hunter`)
   - a prompt containing:
     - the `chunk_id`
     - the list of files and their full contents
     - for test-coverage / untested-code lenses: adjacent test files from `inventory.test_files` where relevant
     - the `repo_summary`
     - a reminder of the scanner's output contract (two JSON blocks)
6. **Collect responses**. For each response:
   - Parse the two JSON blocks (findings array + coverage report).
   - If the response is unparseable or missing either block, mark that cell as `"skipped"` with `skipped_reason: "scanner_response_malformed"` and continue. Log this to `run-log.md`.
   - For each finding in the findings array: **validate** that `files` and `line_spans` are present. Drop findings missing either, and log the drop to `run-log.md` under a "Vague findings dropped" section.
   - Append valid findings to `.bughunter/candidates.jsonl` (one JSON object per line).
   - Update the coverage matrix cell to `"covered"` or `"skipped"` based on the coverage report.
7. **Update** `scan-state.json` with the new invocation count and the matrix state.
8. **Update TodoWrite** progress — convert e.g. "Scanner loop (75 of 150 cells covered)" to `in_progress` with a live count.
9. **Loop** back to step 5.1 unless the termination condition is met.

When the matrix is fully resolved, mark step 5 as `completed`.

---

## 6. Normalization and dedup

Mark step 6 as `in_progress`.

1. Read `.bughunter/candidates.jsonl` into memory.
2. **Re-validate** each candidate: drop any missing `files`, `line_spans`, or with `why_suspicious` shorter than 15 characters. Log drops to `run-log.md`.
3. **Apply the dedup algorithm** (reproduced here for clarity):

   Two findings A and B collapse into one if **all** of:
   - They share at least one file in `files`.
   - Their `line_spans` overlap by ≥ 1 line on a shared file, OR one span is within 5 lines of the other on a shared file.
   - Their `bug_label` strings, lowercased and stripped of stop words (`the`, `a`, `in`, `on`, `of`), share at least one content word OR one is a substring of the other.

   When collapsing, the merged finding:
   - Keeps the union of `files` and `line_spans`.
   - Keeps the longest `why_suspicious`.
   - Keeps the most detailed (longest) `reproduction_sketch`.
   - Records all source agents in a `flagged_by` array (replaces singular `agent`).
   - Takes the highest `confidence_hint` among the merged set (`high` > `medium` > `low`).

4. Assign each merged candidate a stable `candidate_id` of the form `cand-<index>` (zero-padded to 4 digits).
5. Write `.bughunter/candidates-normalized.json`:
   ```json
   {
     "candidate_count": N,
     "candidates": [ /* merged + validated */ ]
   }
   ```

Mark step 6 as `completed`. Update `scan-state.json` to `{"step": "verification"}`.

---

## 7. Opus verification

Mark step 7 as `in_progress`.

For each normalized candidate:

1. **Read the cited files** (just the cited line spans plus ~20 lines of context around each, to keep Opus calls tight).
2. **Dispatch `bug-verifier`** via the `Agent` tool with:
   - the candidate object
   - the cited file contents with context
   - the `repo_summary`
3. **Collect the verdict** JSON.
4. **Second opinion**: if `verdict == "needs_context"` and `extra_context_needed` is populated, parent reads those paths/symbols and re-dispatches `bug-verifier` once with the expanded context. If the second attempt also returns `needs_context`, treat as `suspected` and record a note in `run-log.md`. No further recursion.
5. **Append to `.bughunter/verified.jsonl`** — the full verdict object, plus the original candidate object merged as `candidate`:
   ```json
   {"verdict": "...", "rationale": "...", "suggested_next_step": "...", "candidate": { ... }}
   ```

You may parallelize verifier dispatches up to `max_parallel_scanners` to keep the run fast — the verifier is stateless per candidate.

Mark step 7 as `completed`. Update `scan-state.json` to `{"step": "consolidation"}`.

---

## 8. Consolidation

Mark step 8 as `in_progress`.

1. Filter `verified.jsonl` to exclude entries with `verdict == "rejected"`.
2. Count verdicts by category (confirmed / likely / suspected).
3. Build `run_metadata`:
   ```json
   {
     "generated_at": "<ISO 8601>",
     "scope": "<$ARGUMENTS or 'whole repo'>",
     "chunks_scanned": <N>,
     "scanner_invocations": <M>,
     "candidates": <K>,
     "final_findings": <F>
   }
   ```
4. Dispatch `findings-consolidator` via `Agent` with:
   - the filtered `verified_findings` array
   - the `run_metadata`
5. The consolidator returns raw Markdown. Do not edit it. Write it to `bughunter-report.md` at the repo root.
6. Write `.bughunter/run-log.md` with:
   - Timestamp, scope
   - Chunks scanned, scanner invocations, candidates, final findings
   - Verdict breakdown (confirmed N, likely N, suspected N, rejected N)
   - Any drops under a "Vague findings dropped" section with reasons
   - Any `needs_context` retries

Mark step 8 as `completed`. Update `scan-state.json` to `{"step": "done"}`.

---

## 9. Done

Mark step 9 as `in_progress`, then print this summary to chat:

```
BugHunter complete.

  Scope: <scope>
  Chunks scanned: N
  Scanner invocations: M
  Candidates after dedup: K
  Final findings: F
    - Confirmed: <n>
    - Likely:    <n>
    - Suspected: <n>

Report: bughunter-report.md
Run log: .bughunter/run-log.md
```

Mark step 9 as `completed`.

---

## Guardrails (enforce throughout)

1. **Single-source repo context.** You (parent) Read files. Children get content as context. Never ask a child to re-discover the file tree.
2. **No fake coverage.** The matrix is the only source of truth about scope. Final report must include the counts.
3. **No vague findings.** Drop findings missing `files`, `line_spans`, or meaningful `why_suspicious`. Log drops.
4. **No early stop on bug count.** Coverage is the only termination condition.
5. **No raw scanner output in the final report.** Everything passes through the verifier.
6. **No recursive subagent calls.** Only the parent (you) dispatches. If a verifier asks for more context, you fetch it and re-dispatch — the child never dispatches another child.
7. **Cost cap respected.** At `max_total_agent_invocations`, halt and ask.
8. **60-second evidence rule.** The consolidator enforces this per entry; you enforce it by feeding the consolidator complete candidate records (files, lines, flagged-by, reproduction, rationale, next-step). If any of those are missing from a verified finding, either skip the finding or log it.
