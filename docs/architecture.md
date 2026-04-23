# BugHunter Architecture

This document is the canonical internal reference for how BugHunter works. It is more detailed than the README. It reflects the verified Claude Code plugin system mechanics as of April 2026.

---

## 1. Verified Claude Code Plugin Mechanics (Phase 1 findings)

All structural decisions below were verified against live documentation and reference plugins before writing.

### Plugin manifest

- **Path:** `.claude-plugin/plugin.json`
- **Only required field:** `name`
- Optional fields: `version`, `description`, `author`, `license`, `keywords`, `commands`, `agents`, `skills`, `hooks`, `mcpServers`, `userConfig`.
- Do not place other plugin content inside `.claude-plugin/` — only the manifest.

### Directory layout

```
bughunter/
├── .claude-plugin/plugin.json    # Manifest
├── agents/                       # Subagent .md files
├── skills/<name>/SKILL.md        # Recommended skill structure (vs legacy commands/)
├── examples/                     # Not plugin-executed; for docs + fixtures
├── docs/
├── README.md
└── LICENSE
```

### Skill frontmatter

```yaml
---
name: hunt
description: <when this skill should be invoked>
allowed-tools: Read, Glob, Grep, LS, Bash, Write, Edit, TodoWrite, Agent
---
```

Fields used:
- `name`: kebab-case identifier. Becomes `/bughunter:<name>`.
- `description`: when to invoke.
- `allowed-tools`: comma-separated list.

### Agent frontmatter

```yaml
---
name: silent-failure-hunter
description: <when the parent should delegate to this agent>
model: haiku
tools: Read, Glob, Grep, LS
color: yellow
---
```

Fields used:
- `name` (required)
- `description` (required)
- `model`: short alias (`haiku`, `sonnet`, `opus`) or `inherit`. All valid per current docs.
- `tools`: comma-separated allowlist.
- `color`: visual tag in Claude Code UI.

Plugin-shipped agents cannot use `hooks`, `mcpServers`, or `permissionMode` fields.

### Model aliases

- `BUGHUNTER_HAIKU_MODEL = haiku`
- `BUGHUNTER_OPUS_MODEL = opus`

Both are valid in current docs. Scanner agents use `haiku`; reviewer agents use `opus`.

### Subagent invocation

- Tool name: **`Agent`** (canonical; renamed from `Task` in v2.1.63).
- Legacy alias: `Task` (still works).
- The parent skill uses `Agent` in its `allowed-tools` to dispatch scanners and reviewers.

### Local development

```bash
claude --plugin-dir ./bughunter
```

The local copy takes precedence over any installed marketplace version of the same name. Use `/reload-plugins` to pick up changes without restarting.

### Validation

```bash
claude plugin validate
```

Or from within Claude Code: `/plugin validate`.

For debugging load issues: `claude --debug`.

---

## 2. Directory layout (this plugin)

```
bughunter/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── code-explorer.md
│   ├── test-coverage-analyzer.md
│   ├── silent-failure-hunter.md
│   ├── qa-agent.md
│   ├── code-fuzzing-agent.md
│   ├── untested-code-tester.md
│   ├── bug-verifier.md
│   └── findings-consolidator.md
├── skills/
│   ├── hunt/SKILL.md
│   ├── status/SKILL.md
│   └── triage/SKILL.md
├── examples/fixtures/planted-bugs/
├── docs/architecture.md   (this file)
├── README.md
└── LICENSE
```

---

## 3. Command flow: `/bughunter:hunt`

```
Preflight
  Read CLAUDE.md, README.md, repo config files
  Identify source vs vendor/generated/test-fixture dirs
  Check for resumable .bughunter/scan-state.json
    ↓
Inventory
  Build canonical file list → .bughunter/inventory.json
  Enforce max_files_in_scope (refuse without --scope if exceeded)
    ↓
Chunking
  Dispatch code-explorer(haiku) once with the inventory
  Receive chunk map → .bughunter/chunks.json
  Apply chunk-size thresholds
    ↓
Coverage matrix init
  Build .bughunter/coverage-matrix.json
  Shape: { chunk_id: { lens_name: "pending" | "covered" | "skipped" } }
    ↓
Scanner loop (load-bearing)
  While any cell is "pending":
    Pick next batch of up to max_parallel_scanners (chunk, lens) pairs
    Prefer batching different lenses on same chunk (context locality)
    Parent Reads the chunk files once and passes content as context
    Dispatch scanner agents via Agent tool (parallel batch)
    Collect findings + coverage reports from each child
    Append findings → .bughunter/candidates.jsonl
    Update matrix cells to "covered" or "skipped"
    Track invocation count vs max_total_agent_invocations
    Update TodoWrite progress
    ↓
Normalization + dedup
  Read candidates.jsonl
  Drop findings missing required fields (files, line_spans, why_suspicious)
  Log drops to run-log.md
  Apply dedup algorithm
  Write .bughunter/candidates-normalized.json
    ↓
Opus verification
  For each normalized candidate:
    Parent reads cited files
    Dispatch bug-verifier(opus) with candidate + contents
    Collect verdict → .bughunter/verified.jsonl
    If verifier requested extra_context, parent fetches and re-dispatches ONCE
    ↓
Consolidation
  Dispatch findings-consolidator(opus) with verified set minus rejected
  Receive final Markdown report
  Write bughunter-report.md at repo root
  Write .bughunter/run-log.md (counts, breakdown, timestamps)
    ↓
Done
  Print short summary to chat
```

---

## 4. Agent inventory

### code-explorer (planner, haiku)

Identifies entry points, execution paths, subsystem boundaries, and bug hot zones (parsing, auth, persistence, concurrency, caching, retries, state transitions, config/env, migrations, network boundaries, cleanup paths). Produces the chunk map. Does **not** emit findings.

**Tools:** Read, Glob, Grep, LS

### test-coverage-analyzer (scanner, haiku)

Identifies under-tested critical paths. Distinguishes risky untested code from harmless trivial code. Calls out negative/error paths that look untested. Hypothesizes specific bug classes the missing tests would catch.

**Tools:** Read, Grep

### silent-failure-hunter (scanner, haiku)

Finds swallowed exceptions, broad catches, misleading fallbacks, null/default returns that suppress failure, partial-state mutation followed by failure without rollback, retry/recovery loops that hide real problems, divergence between user-visible behavior and logged behavior.

**Tools:** Read, Grep

### qa-agent (scanner, haiku)

Thinks like a skeptical QA engineer. Simulates suspicious user flows, invalid sequences, partial completion, multi-step interaction bugs, state drift between UX/API/cache/persistence layers.

**Tools:** Read, Grep

### code-fuzzing-agent (scanner, haiku)

Identifies input surfaces worth fuzzing, malformed state/config cases, parser/protocol/serialization hazards. Generates concrete adversarial input ideas and the likely failure mode (crash, hang, invalid transition, corruption, logic bypass).

**Tools:** Read, Grep

### untested-code-tester (scanner, haiku)

Correlates executable logic to testing blind spots. Finds weakly tested cleanup/failure branches, error paths, retries, feature flags, fallback chains, and conditional branches with little coverage. Proposes concrete failures the current suite would not catch.

**Tools:** Read, Grep

### bug-verifier (reviewer, opus)

Takes the normalized candidate list. For each candidate, re-reads the cited files (with `Read` and `Grep`) and evaluates against the classification rubric. Emits a verdict: `confirmed | likely | suspected | rejected`, with a 1–3 sentence rationale. May also emit `needs_context` to request a second-opinion round — the parent fetches the requested paths/symbols and re-dispatches the verifier once (no deeper recursion). If the second round also returns `needs_context`, the candidate is classified `suspected` and a note is written to `run-log.md`.

**Tools:** Read, Glob, Grep, LS

### findings-consolidator (reviewer, opus)

Takes only post-verification candidates (not rejected). Produces the final three-section Markdown report exactly per the report schema. Enforces the 60-second evidence rule.

**Tools:** Read, Glob, Grep

---

## 5. Chunking strategy

| Repo size (source files) | Chunk granularity |
|---|---|
| ≤ 50 | File-level |
| 51–500 | Directory-level |
| > 500 | Subsystem-level (~2,000 LOC each), planned by code-explorer |
| Any file > 1,500 LOC | Split by logical boundary (top-level class or function group) |

Non-source files (vendor, generated, lockfiles, binaries, test fixtures) are excluded from scope. `.gitignore` and obvious exclude patterns are applied.

---

## 6. Scanner lenses

The coverage matrix tracks exactly these 5 lenses. `code-explorer` is the planner and is **not** a lens.

1. `test-coverage-analyzer`
2. `silent-failure-hunter`
3. `qa-agent`
4. `code-fuzzing-agent`
5. `untested-code-tester`

---

## 7. Finding schema (canonical)

Every scanner emits findings as a JSON array inside a fenced ```json block:

```json
{
  "agent": "silent-failure-hunter",
  "chunk_id": "src/payments/processor",
  "files": ["src/payments/processor/charge.ts"],
  "line_spans": [[142, 168]],
  "bug_label": "swallowed retry exception",
  "why_suspicious": "The retry loop catches all exceptions and continues without recording the failure class. After max_retries, it returns null instead of raising, so callers see a successful-looking nil result.",
  "reproduction_sketch": "// caller sees None and assumes success\nresult = charge_card(token, amount)\nif result is None:\n    # this branch is never reached because the function masks failure as a successful empty return\n    handle_failure()",
  "reproduction_status": "reasoned",
  "confidence_hint": "medium",
  "extra_context_needed": ["caller behavior in src/payments/api.ts"]
}
```

Field rules:

- `agent`: scanner name, lowercase with hyphens.
- `chunk_id`: must match a chunk_id from the coverage matrix.
- `files`: relative paths from repo root.
- `line_spans`: array of `[start, end]` inclusive line ranges.
- `bug_label`: 1–6 words, lowercase.
- `why_suspicious`: 1–4 sentences, concrete, evidence-based, references actual code logic.
- `reproduction_sketch`: code snippet showing how to trigger the bug.
- `reproduction_status`: exactly `"executed"` or `"reasoned"`. Scanners always emit `"reasoned"`.
- `confidence_hint`: `"low"`, `"medium"`, or `"high"`. Hint to Opus only.
- `extra_context_needed`: array of paths or symbols. Empty array if none.

Every scanner also emits a coverage report as a second JSON block:

```json
{
  "agent": "silent-failure-hunter",
  "chunk_id": "src/payments/processor",
  "covered": true,
  "skipped_reason": null,
  "lens_confidence": "high",
  "notes": "Reviewed all error handling sites in scope."
}
```

`covered` is `false` only when the agent could not actually examine the chunk (file too large, binary, missing). `skipped_reason` is required when `covered` is `false`.

---

## 8. Deduplication algorithm

Two findings A and B collapse into one if **all** of:

1. They share at least one file in `files`.
2. Their `line_spans` overlap by ≥ 1 line on a shared file, OR one span is within 5 lines of the other on a shared file.
3. Their `bug_label` strings, lowercased and stripped of stop words (`the`, `a`, `in`, `on`, `of`), share at least one content word OR one is a substring of the other.

When collapsing, the merged finding:

- Keeps the union of `files` and `line_spans`.
- Keeps the longest `why_suspicious` (by character count).
- Keeps the longest `reproduction_sketch` (by character count).
- Records all source agents in a new `flagged_by` array (replaces singular `agent`).
- Takes the highest `confidence_hint` among the merged set.

Conservative by design — merges only when evidence strongly suggests the same bug.

---

## 9. Opus classification rubric

The `bug-verifier` agent classifies each candidate using exactly:

- **Confirmed**: The failure mode is mechanically forced by the code as written. Reading the code in isolation is sufficient to see the bug. No reasonable missing context would exonerate it. Reproduction sketch is logically sound.
- **Likely**: The failure mode is plausible under stated assumptions. The assumptions themselves are reasonable but unverified (e.g., "if the caller passes a non-empty list" or "if upstream times out"). A runtime check would resolve it.
- **Suspected but Unlikely**: The pattern looks bug-shaped but evidence is circumstantial, OR a plausible benign explanation exists, OR the "bug" depends on caller behavior that contradicts apparent codebase conventions.
- **Rejected**: Does not meet the Suspected bar. Does not appear in the report.

Asymmetric on purpose: **false positives are worse than missed speculative bugs.**

The verifier may also emit a control-flow value of `needs_context` (not a classification) to request a second-opinion round; see §4 `bug-verifier` for the protocol. `needs_context` is not a terminal verdict.

---

## 10. Persistence layout

All state lives in `.bughunter/` at the target repo root. The final human-facing report lives at `bughunter-report.md` at the target repo root.

| File | Purpose |
|---|---|
| `inventory.json` | Canonical in-scope file list |
| `chunks.json` | Chunk map from code-explorer |
| `coverage-matrix.json` | `{ chunk_id: { lens: "pending" \| "covered" \| "skipped" } }` |
| `candidates.jsonl` | Raw findings from scanners (one JSON per line) |
| `candidates-normalized.json` | Deduplicated candidates after normalization |
| `verified.jsonl` | Opus verdicts (one per line) |
| `scan-state.json` | Run state enabling resume |
| `run-log.md` | Timestamp, scope, counts, drops, breakdown |

---

## 11. Cost and scale caps

| Cap | Default | Behavior on exceed |
|---|---|---|
| `max_chunks` | 200 | Hard stop; refuse run, suggest tighter scope |
| `max_total_agent_invocations` | 600 | Warning + pause; ask user to continue |
| `max_files_in_scope` | 2000 | Refuse without explicit `scope` arg |
| `max_parallel_scanners` | 4 | Upper bound for each dispatch batch |

Overridable via arguments to `/bughunter:hunt`.

---

## 12. Rationale for model choices

- **Haiku for scanners**: Broad recall at low cost. The scanner phase runs O(chunks × lenses) invocations; Haiku keeps this affordable. Scanners are tuned for recall, not precision — they should flag aggressively.
- **Opus for reviewer and consolidator**: Precision and judgment. These agents run O(candidates) invocations and must classify against a nuanced rubric. This is where false positives are filtered; it requires the strongest model.
- **Cost-precision tradeoff**: Haiku's job is *not* to be right — it's to find everything suspicious. Opus's job is to be right. The two-stage design keeps cost proportional to bug density, not repo size.
- **Coordination in parent, not children**: The parent skill owns the loop, the matrix, dedup, dispatch, and state. Children are stateless workers. This prevents state drift and makes resumption trivial.
- **60-second evidence rule**: Exists because the most common failure mode of automated bug-finding is a report full of plausible-sounding nonsense. Forcing concrete evidence per entry makes the report actionable, not decorative.

---

## 13. Deviations from original requirements prompt

| Prompt assumed | Verified reality | Decision |
|---|---|---|
| `commands/hunt.md` layout | `skills/` recommended, `commands/` legacy | Use `skills/hunt/SKILL.md` |
| `model: haiku` / `model: opus` invalid | Both are valid aliases per current docs | Use short aliases |
| `Task` tool for subagent dispatch | Renamed to `Agent` in v2.1.63 | Use `Agent` (Task still works as alias) |
