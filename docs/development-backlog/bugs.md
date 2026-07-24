# Agent Workbench Skill Audit Backlog

Audit date: 2026-07-24.

Scope: all 12 skills under `.agents/skills/`, all 12 `agents/openai.yaml`
files, and all three bundled references. At audit start, the skill bodies
totaled 1,128 lines / 6,631 words; the references added 348 lines / 2,048 words.
At audit time, all skill packages passed `quick_validate.py`, and
`tests/use_case/test_repository_skills.py` passed 17 tests. Those checks
established structural validity, not semantic correctness.

This document lists unresolved findings only. Resolved findings are removed.

## 1. Correctness And Operational Bugs

### P2 — “Run commands with uv run” is overbroad

**Affected:** `project-guide` and the generated README.

`uv run` is correct for Python entry points, but frontend checks run with
`pnpm` in `www/`. The blanket instruction can produce invalid commands such as
`uv run pnpm test`.

**Proposed fix:** say “use `uv run` for Python commands; use the package manager
declared by each non-Python workspace.” Keep the exact `pnpm` commands in the
verification matrix.

### P2 — The current-contract reference blurs legacy and current state

**Affected:** `agent-eval-builder/references/current-evaluation-contracts.md`.

- “Each new retained eval uses schema version 2” ignores supported elevation of
  legacy schema-v1 working results.
- “retained attempt generations” can be mistaken for retained lifecycle state;
  `LocalRunStore.evaluation_rows()` reads attempt-generation files in a working
  bundle.

**Proposed fix:** explicitly separate new schema-v2 occurrences, supported
legacy schema-v1 inputs, and publication’s schema-v2-only boundary. Rename the
working detail to “selected immutable attempt-generation files.”

### P2 — Eval-builder triggering overlaps the dedicated porting skills

**Affected:** `agent-eval-builder` frontmatter.

“Benchmark/evidence handoffs” is broad enough to trigger this builder for work
owned by `benchmark-pipeline-port` or `port-eval-explorer-use-case`.

**Proposed fix:** narrow the trigger to eval profiles, graders, orchestration,
result/lifecycle contracts, and eval-result applications. Explicitly exclude
initial evidence-pipeline and explorer-use-case ports.

## 2. Concision And Progressive-Disclosure Fixes

The current line-count test permits 1,400 body lines and 190 lines per skill.
That is too loose for the desired crispness and can be gamed by rewrapping
prose. Add word budgets and remove duplicated policy text.

### Proposed body budget

| Skill | Audit words | Proposed ceiling | Main reduction |
|---|---:|---:|---|
| `ai-processor-builder` | 751 | 500 | Replace the 50-line template with a tested 15–25-line skeleton or direct source example. |
| `pipeline-builder` | 705 | 500 | Keep contracts and ordered workflow; remove repeated eval/runtime/approval detail. |
| `benchmark-pipeline-port` | 642 | 450 | Keep source-to-target handoff and stop condition; route generic building detail. |
| `agent-eval-builder` | 641 | 450 | Convert five narrative gates to a compact decision table. |
| `project-guide` | 599 | 400 | Keep ownership, routing table, and verification link; collapse duplicated sequencing. |
| `port-eval-explorer-use-case` | 567 | 450 | Keep ownership split and dual evidence path; shorten parity prose. |
| `eval-results-analysis` | 539 | 450 | Keep commands and evidence rules; remove repeated lifecycle explanation. |
| `external-runtime-setup` | 513 | 425 | Keep startup order and fail-closed identity rules; leave provider mappings in the reference. |

Leave the four already-shorter operational skills near their current size.
Target at most 5,000 total body words, with no loss of mandatory safety or
verification rules.

### Cross-cutting reductions

1. Keep the complete ownership/routing table only in `project-guide`; other
   skills should use one-line handoffs only where a boundary is easy to confuse.
2. State the exact-example-versus-eval rule once in `pipeline-builder` and once
   in `run-use-case-evals`; other skills can route to those owners.
3. Merge “Run And Retention Layout” and “Local Lifecycle Maintenance” in
   `current-evaluation-contracts.md`; they currently repeat elevation,
   verification, deletion, explorer, and publication behavior.
4. Keep source-file maps in references, not in skill bodies.
5. Normalize UI metadata display names (`Agent Eval Builder`,
   `External Runtime Setup`, `Pipeline Builder`) and shorten default prompts to
   one action plus one outcome. Omit explicit `allow_implicit_invocation: true`
   everywhere or include it everywhere; the current mixed style has identical
   default behavior but creates review noise.
6. Replace the line-only concision test with a combined total/per-skill word
   budget. Do not add brittle tests for exact prose except for safety-critical
   commands and markers.

## 3. Critical Topics Missing From The Skills

These topics should be added once at the named owner, in concise form. Omitting
them can cause corrupted historical results, unsafe agents, paid duplicate
runs, or generated projects that cannot validate themselves.

### Historical schema compatibility and migration policy

**Owner:** `agent-eval-builder` plus `current-evaluation-contracts.md`.

Any change to a persisted result, manifest, attempt, retained artifact,
publication, candidate-policy, or evidence-envelope schema must state:

- which existing versions remain readable;
- whether migration is required and whether it is copy-on-write or in-place;
- how identity/hash invariants remain valid; and
- which legacy fixtures and explorer/lifecycle/publication paths were tested.

Do not silently rewrite immutable retained or published artifacts.

### Untrusted evidence and prompt/tool injection

**Owner:** `ai-processor-builder`; referenced by both porting skills.

Frozen evidence, labels, retrieved text, images, and tool output are data, not
instructions. Tool-enabled agents must separate trusted system policy from
untrusted content, validate tool arguments and outputs, bound returned data,
and never grant authority based on evidence text. Add focused adversarial tests
for any tool or deferred skill exposed to model-controlled input.

### Contract-document and skill-metadata drift

**Owner:** `project-guide/references/verification-matrix.md`.

When a change alters a CLI flag, environment variable, schema version, path,
lifecycle rule, or skill boundary, require the same change to update the owning
runbook/reference, `agents/openai.yaml` when discovery text changed, and the
documented-command smoke test. `quick_validate.py` does not detect semantic
drift.

### Dependency and lockfile integrity

**Owner:** repository verification matrix.

Add a concise row for Python and frontend dependency changes. It should require
the relevant manifest and lockfile to change together, a locked/frozen install
or lock check, import/build validation, and no unrelated lockfile churn.

### Generated-project forward validation

**Owner:** `create-use-case-project`.

Validation must cover behavior after the reference seam is cleared, not only
file presence and identity replacement. At minimum, a fresh project must be
able to discover and validate every preserved skill, import reusable packages,
run its preserved generic contract tests, and display only executable commands
or an explicit bootstrap placeholder.

## 4. Per-Skill Disposition

| Skill | Proposed disposition |
|---|---|
| `agent-eval-builder` | Narrow triggering, add schema compatibility, and compress stage gates. |
| `ai-processor-builder` | Add the untrusted-input/tool rule and shrink the code template. |
| `benchmark-pipeline-port` | Shorten repeated builder/eval rules; retain its source provenance, overwrite protection, cutoff, and integrity checks. |
| `create-use-case-project` | Add generated-project forward validation and make the pricing/reference-leak check executable. |
| `external-runtime-setup` | Compress startup and model-catalog prose while retaining fail-closed identity rules. |
| `pipeline-builder` | Reduce duplicated handoff prose. |
| `port-eval-explorer-use-case` | Shorten parity prose while retaining both evidence sources. |
| `project-guide` | Correct Python/frontend command wording and centralize the concise approval/routing rules. |

## 5. Completion Gate For The Skill Fixes

1. Every skill and metadata file passes `quick_validate.py`.
2. The preserved repository-skill test passes in both the template and a
   freshly bootstrapped project.
3. All Markdown links, paths, CLI flags, and environment names are checked
   against current source or `--help`.
4. Lifecycle, publication, working/retained explorer, exact-runner, and eval
   occurrence tests cover the corrected semantics above.
5. The skill-body word budget passes without removing safety-critical rules.
6. `git diff --check` passes.
