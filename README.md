# BugHunter

A Claude Code plugin that hunts for bugs across an entire repository using a staged multi-agent pipeline: cheap Haiku scanners for broad recall, careful Opus reviewers for precision.

BugHunter is **not** a PR review tool and **not** a linter. It scans a whole codebase (or a scoped subset), triages the raw findings, and produces a final report where every entry is concrete enough that a reviewer can confirm or reject it in under 60 seconds.

---

## Overview

Most automated bug-finding tools produce a stream of plausible-sounding noise that developers learn to tune out. BugHunter is designed around the inverse goal: **the final report should be short, trustworthy, and actionable.**

The design implements that goal in three mechanisms:

1. **Two-stage pipeline.** Five Haiku scanner agents (with different lenses) examine every chunk of the codebase for bug-shaped patterns. Their output is the *candidate pool*. Two Opus reviewer agents then classify each candidate and render the final report. Cost stays proportional to bug density, not repo size.
2. **Coverage matrix as the sole termination condition.** Every `(chunk, lens)` pair must be examined or explicitly skipped with a reason. No early stop because "we found enough bugs". No silent gaps.
3. **60-second evidence rule.** Every entry in the final report includes the file paths, line spans, a reproduction sketch, the scanners that flagged it, and the verifier's rationale — enough for a reviewer to confirm or reject without re-running BugHunter.

### How BugHunter differs from a PR review

PR reviews look at a diff. BugHunter looks at the whole tree. PR reviews are opinionated about style and "what changed". BugHunter is opinionated about *what's already broken*.

### How BugHunter differs from a linter

Linters flag syntactic or well-known structural patterns. BugHunter reasons about behavior: swallowed exceptions, partial-state mutations, untested critical branches, adversarial inputs, state drift between layers. A linter that finds these would have to be the size of BugHunter; BugHunter is the size of a few prompts.

---

## Installation / Local Development

BugHunter is a Claude Code plugin. To use it locally during development:

```bash
claude --plugin-dir /path/to/bughunter
```

To validate the plugin:

```bash
claude plugin validate
```

Or, from within Claude Code: `/plugin validate`.

For debugging load issues:

```bash
claude --debug
```

Once loaded, BugHunter registers three slash commands under the `bughunter:` namespace.

---

## Usage

### `/bughunter:hunt [scope]`

Run the full pipeline. With no argument, scans the entire repo (subject to `max_files_in_scope`). With an argument, restricts scope to a path or glob:

```
/bughunter:hunt
/bughunter:hunt src/payments
/bughunter:hunt 'src/**/*.ts'
```

When the run completes, `bughunter-report.md` is written to the repo root.

### `/bughunter:status`

Print the current state of the in-progress or most-recent scan: step, coverage matrix progress, candidate counts, and whether the report has been written.

### `/bughunter:triage`

Re-run only the Opus verification and consolidation stages against the saved normalized candidates. Useful when iterating on the verifier or consolidator prompts — the scanners' output is reused as-is.

---

## Architecture

```
Preflight → Inventory → Chunking → Coverage Matrix Init → Scanner Loop
  → Normalization + Dedup → Opus Verification → Consolidation → Done
```

### Agent inventory

- **`code-explorer`** (Haiku, planner) — Maps the codebase into chunks once per run. Identifies entry points, subsystems, and bug hot zones. Does not emit findings.
- **`test-coverage-analyzer`** (Haiku, scanner) — Under-tested critical paths.
- **`silent-failure-hunter`** (Haiku, scanner) — Swallowed exceptions, misleading fallbacks, partial mutations without rollback.
- **`qa-agent`** (Haiku, scanner) — Adversarial user flows, multi-step interaction bugs, state drift.
- **`code-fuzzing-agent`** (Haiku, scanner) — Input surfaces worth fuzzing, parser/serialization hazards.
- **`untested-code-tester`** (Haiku, scanner) — Logically distinct branches with no test coverage.
- **`bug-verifier`** (Opus, reviewer) — Classifies candidates as Confirmed / Likely / Suspected / Rejected.
- **`findings-consolidator`** (Opus, reviewer) — Renders the final three-section Markdown report.

### Chunking

| Repo size | Strategy |
|---|---|
| ≤ 50 source files | File-level chunks |
| 51–500 source files | Directory-level chunks |
| > 500 source files | Subsystem-level chunks (~2,000 LOC), planned by `code-explorer` |
| Any file > 1,500 LOC | Split by logical boundary |

### Coverage matrix

A 2D structure keyed `{chunk_id: {lens_name: "pending" | "covered" | "skipped"}}`. The scanner loop terminates only when every cell is `covered` or `skipped` with a reason.

### Deduplication

Two findings collapse into one if they share a file, their line spans overlap or are within 5 lines, and their labels share a content word or one is a substring of the other. Conservative by design — borderline cases stay separate.

### Opus verification

The rubric:

- **Confirmed**: Mechanically forced by the code as written. Reading the code in isolation is sufficient.
- **Likely**: Plausible under stated assumptions. A runtime check would resolve it.
- **Suspected but Unlikely**: Bug-shaped but circumstantial, OR a plausible benign explanation exists.
- **Rejected**: Not a bug. Does not appear in the report.

See [`docs/architecture.md`](docs/architecture.md) for full detail.

---

## Output Format

`bughunter-report.md` always has exactly three sections:

```markdown
# BugHunter Report

_Generated: 2026-04-22T14:02:11Z_
_Scope: src/payments_
_Chunks scanned: 4 | Scanner invocations: 20 | Candidates: 6 | Final findings: 3_

## Confirmed Bugs

### swallowed retry exception
- **Files:** `src/payments.py`
- **Lines:** 20-40
- **Flagged by:** silent-failure-hunter, test-coverage-analyzer
- **Reproduction status:** reasoned
- **Summary:** `charge_card` retries up to 3 times with a bare `except:` that catches every exception class, then returns None after the loop exhausts. Callers cannot distinguish "gateway declined" from "network down" from "we crashed" — all three look like a successful charge that returned nothing.
- **Reproduction:**
  ```python
  result = charge_card("tok_123", 500)
  if result is None:
      # caller has no way to know whether to retry, alert, or fail the order
      ...
  ```
- **Why Confirmed:** The `except:` on line 32 catches all exceptions and the `return None` after the loop is indistinguishable from legitimate empty success; callers in api.ts check `if result is None` with no exception branch.
- **Suggested next step:** Replace `except:` with `except PaymentGatewayError as e` and re-raise after logging; have callers distinguish success-with-data from failure via exception.

## Likely Bugs

None.

## Suspected but Unlikely Bugs

None.
```

If a section is empty, the header is followed by `None.` on its own line.

---

## Known Limitations

- **Static reasoning only.** BugHunter reads code; it does not execute it. Every `reproduction_status` field will almost always be `reasoned`, never `executed`. For bugs that depend on runtime state, an assertion "this is a bug" is always conditional on caller behavior matching your assumptions.
- **Opus-classified ≠ ground truth.** A finding in "Confirmed" is Opus's best judgment that the failure is mechanically forced by the code. It is a very good judgment, but it is not execution. Treat Confirmed findings as "almost certainly worth fixing", not as "proven at runtime".
- **Cost scales with candidate density.** The Haiku scanner phase is inexpensive per chunk; the Opus verifier phase is proportional to how many candidates survive dedup. A codebase with many suspicious patterns will cost more to verify. The 600-invocation default cap is conservative; raising it is fine if you've triaged the warning prompt.
- **Language-agnostic, but best with mainstream languages.** Scanners are prompted with pattern families (swallowed exceptions, off-by-one, unvalidated input) that apply across languages. They work best on mainstream imperative languages; they work less well on heavily meta-programmed DSLs or on languages the Haiku training data under-represents.
- **Not a security audit.** BugHunter will often flag security-adjacent issues (unvalidated input, unsafe deserializers, missing auth checks) but it is not a substitute for a dedicated security review.

---

## Design Decisions

- **Why scanners are Haiku.** Haiku is cheap and fast; scanners are tuned for recall, not precision. Over-flagging is the correct behavior for this stage — the downstream Opus reviewer filters aggressively.
- **Why verifier and consolidator are Opus.** Opus owns classification against a nuanced rubric and renders the final report. Both require the strongest model because false positives here survive into the user's field of view.
- **Cost-precision tradeoff.** Haiku's job is to find everything suspicious. Opus's job is to be right. Separating recall from precision lets each stage specialize.
- **Why coordination lives in the parent.** The parent skill owns the loop, the matrix, dedup, dispatch, and state. Children are stateless workers. This prevents state drift and makes resumption trivial — you can always re-enter the pipeline at the next step in `scan-state.json`.
- **Why the 60-second evidence rule exists.** The worst failure mode of automated bug-finding is a report full of plausible-sounding nonsense that developers learn to ignore. Forcing concrete evidence per entry — file, lines, reproduction, rationale, next step — makes the report actionable instead of decorative. The consolidator enforces this rule per entry; the parent enforces it by feeding complete candidate records to the consolidator.

---

## Persistence and Resume

All scan state lives in `.bughunter/` at the target repo root:

| File | Purpose |
|---|---|
| `inventory.json` | Canonical in-scope file list |
| `chunks.json` | Chunk map from `code-explorer` |
| `coverage-matrix.json` | Per-`(chunk, lens)` coverage status |
| `candidates.jsonl` | Raw findings from scanners |
| `candidates-normalized.json` | Deduplicated candidates |
| `verified.jsonl` | Opus verdicts |
| `scan-state.json` | Current step + counters for resume |
| `run-log.md` | Timestamps, counts, dropped findings |

The final report lives at `bughunter-report.md` at the repo root.

**Resume:** If `/bughunter:hunt` is interrupted, re-run it. If `.bughunter/scan-state.json` exists, the skill offers to resume from the last completed step.

**Iteration:** After a successful scan, use `/bughunter:triage` to re-classify and re-render without re-scanning. This is the right loop when tuning verifier or consolidator prompts.

---

## Fixture Test Bed

`examples/fixtures/planted-bugs/` is a small Python + TypeScript codebase with 7 required planted bugs (F1–F7) and 2 stretch bugs (F8–F9). Every planted bug is documented in `examples/fixtures/planted-bugs/EXPECTED.md` with file, line range, and expected classification.

### Using the fixture for regression testing

After any change to scanner prompts, the verifier rubric, or the consolidator template:

1. Delete `.bughunter/` in the fixture directory (clean state).
2. From within Claude Code in the fixture directory, run `/bughunter:hunt`.
3. Compare `bughunter-report.md` to `EXPECTED.md`.

### Acceptance bar

A fixture run is acceptable if **all** of:

- ≥ 7 of 7 required bugs (F1–F7) appear in Confirmed or Likely.
- ≤ 2 false positives in Confirmed.
- ≤ 5 false positives across Confirmed + Likely combined.
- Coverage matrix shows 100% covered or explicitly skipped with reason.
- Report follows the schema exactly.
- No agent invocation errors in `run-log.md`.

If the bar is not met, iterate on prompts (especially `silent-failure-hunter`, `bug-verifier`, and `findings-consolidator`). Do not relax the bar.

---

## License

MIT — see [LICENSE](LICENSE).
