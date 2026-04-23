# BugHunter Plugin Design Spec

## Overview

BugHunter is a Claude Code plugin that performs repository-scale bug hunting through a staged multi-agent workflow. It is not a PR review tool and not a linter. It scans an entire codebase (or scoped subset), uses cheap Haiku scanners for broad coverage, then uses Opus reviewers to triage candidates into a trustworthy final report.

**Primary quality bar:** Real bug yield with low false positives. Every finding that survives to the final report must include enough evidence that a reviewer can confirm or reject it in under 60 seconds without re-running BugHunter.

### Naming

- Human-facing documentation: **BugHunter**
- Manifest name, namespace, CLI usage, file paths, identifiers: **`bughunter`** (lowercase)

---

## Plugin Structure (Verified from Live Docs)

Based on verified Claude Code plugin documentation (April 2026):

```
bughunter/
├── .claude-plugin/
│   └── plugin.json                # Manifest: name "bughunter"
├── agents/
│   ├── code-explorer.md           # Haiku — planner/mapper
│   ├── test-coverage-analyzer.md  # Haiku — scanner
│   ├── silent-failure-hunter.md   # Haiku — scanner
│   ├── qa-agent.md                # Haiku — scanner
│   ├── code-fuzzing-agent.md      # Haiku — scanner
│   ├── untested-code-tester.md    # Haiku — scanner
│   ├── bug-verifier.md            # Opus — reviewer
│   └── findings-consolidator.md   # Opus — reviewer
├── skills/
│   ├── hunt/
│   │   └── SKILL.md               # Primary orchestration command
│   ├── status/
│   │   └── SKILL.md               # Scan state reporter
│   └── triage/
│       └── SKILL.md               # Re-triage without re-scanning
├── examples/
│   └── fixtures/
│       └── planted-bugs/          # Test bed with planted bugs + EXPECTED.md
├── docs/
│   └── architecture.md            # Detailed architecture reference
├── README.md
└── LICENSE
```

### Verified Plugin Mechanics

| Mechanic | Verified Value |
|---|---|
| Manifest path | `.claude-plugin/plugin.json` |
| Manifest required fields | `name` only |
| Skill structure | `skills/<name>/SKILL.md` |
| Agent structure | `agents/<name>.md` |
| Model aliases | `haiku`, `sonnet`, `opus` (all valid) |
| Subagent invocation tool | `Agent` (renamed from `Task` in v2.1.63; `Task` still works) |
| Local dev loading | `claude --plugin-dir ./bughunter` |
| Validation | `claude plugin validate` |
| Plugin agent restrictions | No `hooks`, `mcpServers`, or `permissionMode` in frontmatter |

### Deviations from Original Prompt

| Original prompt assumed | Verified reality | Decision |
|---|---|---|
| `commands/hunt.md` | `skills/` recommended, `commands/` legacy | Use `skills/hunt/SKILL.md` |
| `model: haiku` not valid | `haiku` and `opus` are valid aliases | Use short aliases |
| `Task` tool for subagents | Renamed to `Agent`; `Task` still works | Use `Agent` in allowed-tools |

---

## Architecture

### Command Flow: `/bughunter:hunt`

```
Preflight
  │  Read CLAUDE.md, README.md, repo config
  │  Identify source vs vendor/generated dirs
  │  Check for resumable state in .bughunter/
  ▼
Inventory
  │  Build canonical file list → .bughunter/inventory.json
  │  Enforce max_files_in_scope (2,000)
  ▼
Chunking
  │  Dispatch code-explorer (Haiku) with inventory
  │  Receive chunk map → .bughunter/chunks.json
  │  Apply chunk-size rules
  ▼
Coverage Matrix Init
  │  Build .bughunter/coverage-matrix.json
  │  2D: {chunk_id: {lens_name: "pending"}}
  ▼
Scanner Loop
  │  Loop until every cell = "covered" or "skipped":
  │    Pick next batch (up to 4 parallel)
  │    Dispatch scanner agents via Agent tool
  │    Collect findings → .bughunter/candidates.jsonl
  │    Update coverage matrix
  │    Track invocation count vs cap
  ▼
Normalization & Dedup
  │  Read candidates.jsonl
  │  Apply dedup algorithm
  │  Write .bughunter/candidates-normalized.json
  ▼
Opus Verification
  │  For each normalized candidate:
  │    Dispatch bug-verifier (Opus) with candidate + file contents
  │    Collect verdict → .bughunter/verified.jsonl
  │    Handle second-opinion requests (max 1 per candidate)
  ▼
Consolidation
  │  Dispatch findings-consolidator (Opus)
  │  Receive final Markdown report
  │  Write bughunter-report.md at repo root
  │  Write .bughunter/run-log.md
  ▼
Done
    Print summary to chat
```

### Agent Inventory

| Agent | Role | Model | Tools | Responsibility |
|---|---|---|---|---|
| `code-explorer` | Planner | `haiku` | Read, Glob, Grep, LS | Maps the codebase: entry points, execution paths, subsystem boundaries, bug hot zones. Produces the chunk map. Does NOT emit findings. |
| `test-coverage-analyzer` | Scanner | `haiku` | Read, Glob, Grep, LS | Identifies under-tested critical paths, risky untested code, missing negative/error path tests, hypothesizes bug classes missing tests would catch. |
| `silent-failure-hunter` | Scanner | `haiku` | Read, Glob, Grep, LS | Finds swallowed exceptions, broad catches, misleading fallbacks, null/default returns suppressing failure, partial-state mutation without rollback, retry loops hiding problems. |
| `qa-agent` | Scanner | `haiku` | Read, Glob, Grep, LS | Thinks like a skeptical QA engineer. Simulates suspicious user flows, invalid sequences, partial completion, multi-step interaction bugs, state drift. |
| `code-fuzzing-agent` | Scanner | `haiku` | Read, Glob, Grep, LS | Identifies input surfaces worth fuzzing, malformed state/config cases, parser/protocol/serialization hazards. Generates concrete adversarial inputs. |
| `untested-code-tester` | Scanner | `haiku` | Read, Glob, Grep, LS | Correlates logic to testing blind spots. Finds weakly tested cleanup/failure branches, error paths, retries, feature flags, fallback chains. |
| `bug-verifier` | Reviewer | `opus` | Read, Glob, Grep, LS | Re-reads cited files, evaluates against classification rubric, emits verdict + rationale. Signals need for second opinion via `extra_context_needed` in response; the parent re-dispatches. |
| `findings-consolidator` | Reviewer | `opus` | Read, Glob, Grep | Takes verified candidates, produces the final three-section Markdown report per the report schema. |

### Chunking Strategy

| Repo size | Strategy |
|---|---|
| ≤50 source files | File-level chunks |
| 51-500 source files | Directory-level chunks |
| >500 source files | Subsystem-level chunks (~2,000 LOC each), planned by code-explorer |
| Any single file >1,500 LOC | Split by logical boundary (top-level class or function group) |

### Scanner Lenses

The coverage matrix tracks these 5 lenses (code-explorer is the planner, not a lens):

1. `test-coverage-analyzer`
2. `silent-failure-hunter`
3. `qa-agent`
4. `code-fuzzing-agent`
5. `untested-code-tester`

---

## Schemas

### Finding Schema

Every scanner agent emits findings as a JSON array inside a fenced `json` block. Every object conforms to:

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

**Field rules:**

- `agent`: scanner name, lowercase with hyphens
- `chunk_id`: must match a chunk_id from the coverage matrix
- `files`: relative paths from repo root
- `line_spans`: array of `[start, end]` inclusive line ranges
- `bug_label`: 1-6 words, lowercase
- `why_suspicious`: 1-4 sentences, concrete, evidence-based, references actual code logic
- `reproduction_sketch`: code snippet showing how to trigger the bug
- `reproduction_status`: exactly `"executed"` or `"reasoned"`. Scanners always emit `"reasoned"`.
- `confidence_hint`: exactly `"low"`, `"medium"`, or `"high"`. Hint to Opus only.
- `extra_context_needed`: array of paths or symbols. Empty array if none.

### Coverage Report Schema

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

`covered` is `false` only if the agent could not examine the chunk (file too large, binary, missing). `skipped_reason` is required when `covered` is `false`.

---

## Deduplication Algorithm

Two findings A and B collapse into one if ALL of:

1. They share at least one file in `files`.
2. Their `line_spans` overlap by at least one line on a shared file, OR one span is within 5 lines of another on a shared file.
3. Their `bug_label` strings, lowercased and stripped of stop words (`the`, `a`, `in`, `on`, `of`), share at least one content word OR one is a substring of the other.

When collapsing, the merged finding:
- Keeps the union of `files` and `line_spans`
- Keeps the longest `why_suspicious`
- Keeps the most detailed `reproduction_sketch`
- Records all source agents in a `flagged_by` array (replaces singular `agent`)
- Takes the highest `confidence_hint` among the merged set

Conservative by design: merges only when evidence strongly suggests the same bug.

---

## Opus Classification Rubric

The `bug-verifier` classifies each candidate using exactly these criteria:

- **Confirmed**: The failure mode is mechanically forced by the code as written. Reading the code in isolation is sufficient to see the bug. No reasonable missing context would exonerate it. Reproduction sketch is logically sound.
- **Likely**: The failure mode is plausible under stated assumptions. The assumptions are reasonable but unverified. A runtime check would resolve it.
- **Suspected but Unlikely**: The pattern looks bug-shaped but evidence is circumstantial, OR a plausible benign explanation exists, OR the "bug" depends on caller behavior contradicting apparent codebase conventions.
- **Rejected**: Does not meet the Suspected bar. Does not appear in the report.

The rubric is asymmetric: false positives are worse than missed speculative bugs.

---

## Final Report Schema

`bughunter-report.md` has exactly three top-level sections:

```markdown
# BugHunter Report

_Generated: <ISO timestamp>_
_Scope: <path or glob>_
_Chunks scanned: N | Scanner invocations: M | Candidates: K | Final findings: F_

## Confirmed Bugs

### <short bug-type label>
- **Files:** `path/to/file.ext`
- **Lines:** 142-168
- **Flagged by:** silent-failure-hunter, test-coverage-analyzer
- **Reproduction status:** reasoned
- **Summary:** 1-5 sentence summary, evidence-based and concrete.
- **Reproduction:**
  ```language
  // code snippet showing how to trigger the bug
  ```
- **Why Confirmed:** 1-2 sentence rationale from bug-verifier.
- **Suggested next step:** 1 sentence.

## Likely Bugs
<same structure; "Why Likely" instead of "Why Confirmed">

## Suspected but Unlikely Bugs
<same structure; "Why Suspected" instead of "Why Confirmed">
```

Empty sections render the header followed by `None.` on its own line.

**Honesty rule:** `Reproduction status` is `executed` only if BugHunter actually ran the snippet. In practice this is almost always `reasoned`.

---

## Cost and Scale Caps

| Cap | Default | Notes |
|---|---|---|
| `max_chunks` | 200 | Hard limit |
| `max_total_agent_invocations` | 600 | Triggers warning + pause for user confirmation |
| `max_files_in_scope` | 2,000 | Refuses without explicit `scope` argument if exceeded |
| `max_parallel_scanners` | 4 | Up to 4 Agent calls per batch |

---

## Persistence Layout

All state lives in `.bughunter/` at target repo root:

| File | Purpose |
|---|---|
| `inventory.json` | Canonical file list |
| `chunks.json` | Chunk map from code-explorer |
| `coverage-matrix.json` | 2D: `{chunk_id: {lens: status}}` |
| `candidates.jsonl` | Raw findings from scanners (one JSON per line) |
| `candidates-normalized.json` | Deduplicated candidates |
| `verified.jsonl` | Opus verdicts |
| `scan-state.json` | Run state for resume capability |
| `run-log.md` | Timestamp, scope, counts, classification breakdown |

Final human-facing report: `bughunter-report.md` at repo root.

---

## Guardrails

1. **Single-source repo context.** Parent reads files, passes content to children. Children must not re-discover the file tree.
2. **No fake coverage.** The matrix is the only source of truth. Final report includes matrix counts.
3. **No vague findings.** Reject any finding lacking `files`, `line_spans`, or non-trivial `why_suspicious`. Drop during normalization, log to run-log.md.
4. **No early stop on bug count.** Coverage is the only termination condition.
5. **No raw scanner output in report.** Everything passes through the verifier.
6. **No recursive subagent calls.** Verifier may request one second opinion per candidate; only the parent re-dispatches.
7. **Cost cap respected.** Parent halts and asks user when nearing max_total_agent_invocations.
8. **60-second evidence rule.** Every final-report entry must contain enough info for a reviewer to confirm or reject in under 60 seconds without rerunning BugHunter.

---

## Planted Fixture Test Bed

`examples/fixtures/planted-bugs/` — mixed Python and TypeScript codebase with planted bugs:

| ID | Bug class | Required |
|---|---|---|
| F1 | Swallowed exception in retry loop | Yes |
| F2 | Off-by-one in pagination boundary | Yes |
| F3 | Unvalidated input passed to parser | Yes |
| F4 | Critical path with zero test coverage | Yes |
| F5 | Partial state mutation on failure (no rollback) | Yes |
| F6 | Config/env assumption that breaks on missing key | Yes |
| F7 | Retry/fallback that masks the original error class | Yes |
| F8 | Race window between check and use | Stretch |
| F9 | Silent type coercion losing precision | Stretch |

### Acceptance Bar

- >=7 of 7 required bugs (F1-F7) in Confirmed or Likely
- <=2 false positives in Confirmed
- <=5 false positives across Confirmed + Likely combined
- Coverage matrix shows 100% covered or explicitly skipped
- Report follows schema exactly
- No agent invocation errors in run-log.md

---

## Model Choice Rationale

- **Scanners use Haiku**: Broad recall at low cost. Each scanner examines many chunks; Haiku is fast and cheap enough to cover the full matrix without budget concern. Its job is recall, not precision.
- **Verifier and consolidator use Opus**: Precision and judgment. These agents classify findings against a nuanced rubric and produce the final report. False positive filtering requires the strongest model.
- **Cost-precision tradeoff**: Haiku scans O(chunks x lenses) times cheaply; Opus reviews only O(candidates) times at higher cost. The two-stage design keeps total cost proportional to actual bug density, not repo size.
- **Coordination in parent, not children**: The parent owns the loop, the matrix, dedup, and dispatch. Children are stateless workers. This prevents state drift and makes resumption trivial.
- **60-second evidence rule**: Exists because the most common failure mode of automated bug-finding is a report full of plausible-sounding nonsense. Forcing concrete evidence per entry makes the report trustworthy.
