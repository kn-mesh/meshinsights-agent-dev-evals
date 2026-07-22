# Test Suite Review And High-Value Gaps

## Outcome

The repository test suite was reviewed on 2026-07-21 against the current
source, the contracts in `docs/development-current/`, and the durable Spirax
context in `docs/use_case/`.

After the focused additions in this pass, the suite currently collects 307
tests:

- 114 use-case and Agent Workbench tests under `tests/`;
- 28 shared evaluation tests under `agent-dev-eval-core/tests/`; and
- 165 reusable framework and CLI tests under `mi-core/tests/`.

The default run passes 301 tests and skips six credential-dependent provider
smoke tests. The skipped workflow and agent tests remain useful as opt-in live
integration checks, but they do not provide default CI protection.

Every existing test protects a meaningful behavior, compatibility boundary,
failure mode, security invariant, package artifact, or release operation. No
test should be removed solely to shorten the suite. In particular:

- parameterized model parsing, provider prerequisites, and invalid-config
  cases protect distinct compatibility or fail-closed branches;
- mock-heavy telemetry tests protect global idempotency, sampler behavior, and
  subprocess hook selection rather than merely mirroring implementation;
- packaging and changelog tests protect shipped assets and release automation;
- `test_default_grader_registry_resolves_profile_graders` is useful even
  without a direct assertion because resolving every configured grader is the
  asserted operation; and
- the live provider smoke tests delegate their detailed assertions to the
  workflow and agent orchestrators and should remain explicitly optional.

Do not replace these tests with broad snapshots or tests that only assert
implementation details. New tests should exercise a user-visible contract,
irreversible evidence boundary, or expensive failure mode.

## Baseline Coverage Signal

Statement coverage captured during the initial 299-test audit is a diagnostic
signal, not a target:

| Surface | Statements exercised |
|---|---:|
| Root `src/` | 76.4% |
| `agent-dev-eval-core/evaluation/` | 88.1% |
| `mi-core/core/src/` | 68.1% |
| `mi-core/cli/src/` | 0.0% |

The zero CLI number is real: the suite verifies that monitor CSS is packaged,
but it does not execute the reusable `mi` CLI modules. Coverage alone does not
justify tests for trivial accessors, import files, display formatting, or every
defensive branch. The gaps below are selected because they protect documented
product behavior.

## P0 Missing Tests

### Process execution, interruption, and durable recovery

Related plan:
`reproducible-eval-execution-and-model-comparison.md`.

Current tests cover serial and threaded planning, cooperative cancellation,
durable attempt commits, resume, failed-generation reruns, and an injected
interruption. They do not exercise a real process executor through the durable
run store.

Add one end-to-end process-mode test that:

1. runs a small injected benchmark with more work than workers;
2. interrupts after at least one terminal callback;
3. proves worker processes never write shared run state directly;
4. resumes only missing work without duplicating completed executions; and
5. materializes the same logical ordering and scoring as serial execution.

This single test covers the highest-risk promises around process isolation,
crash recovery, and exactly-once durable evidence. Separate low-level tests for
each executor helper would provide less value.

### Agent-version dirty state and retained-byte security

Related plan: `immutable-agent-versions-and-benchmark-linkage.md`.

Current tests cover deterministic clean resolution, v2 prompt/skill/tool/schema
completeness, model override rejection, manifest identity mutation,
idempotent promotion/reconstruction, and alias conflict behavior. The most
important dirty-worktree and retained-object rules are not covered.

Add a table-driven repository test covering modified, added, deleted, renamed,
executable, and symlinked execution assets. It must prove that:

- `reject` fails before promotion;
- `capture` changes the agent version and retains the exact permitted bytes;
- secret-like, outside-root, and oversized assets fail closed without being
  written to either run-local or global CAS; and
- reconstruction cannot escape its destination.

Add a focused corruption test that changes or removes a retained CAS object and
proves `verify` and `reconstruct` fail before reporting success. These tests are
more valuable than additional clean-manifest snapshots because the dirty and
corrupt paths are where reproducibility can silently fail.

Implemented 2026-07-21: a dirty pipeline asset is captured into CAS, then
corrupted; both verification and reconstruction are required to fail. The
broader dirty-operation and secret-path matrix remains open.

### Review capture is observational and integrity checked

Related plan: `evidence-first-eval-result-inspection.md`.

Current tests cover run-scoped deduplication, redaction of structured values,
manifest/result correlation, basic inspection filters, review-only purge,
symlink rejection, and interrupted-purge recovery. They do not prove that
capture cannot change model behavior or that the captured model transcript is
complete.

Add workflow and tool-using-agent backend tests that verify chronological
request/messages, image bytes, tool-call/result correlation, raw output,
parsed output, and output-validation retry history. The same tests should
inject a capture-sink exception and prove that successful agent output and
normalized telemetry are unchanged while capture status becomes partial or
failed.

Add one tamper test for each retained boundary: execution manifest, externalized
text, and binary object. `verify` and resolved inspection must reject changed
content or byte length. Also test that diagnosis Markdown cannot persist a
credential-shaped value; structured diagnosis redaction alone is insufficient
to establish that safety property.

Implemented 2026-07-21: manifest and externalized-object tampering are rejected,
diagnosis Markdown is checked for embedded credentials, and a regression test
ensures small inline-text thresholds cannot externalize manifest control
identities. Transcript completeness and capture-sink failure isolation remain
open.

### Evaluation profile and grader failure semantics

Related plan: `schema-driven-evaluation-and-scoring.md`.

Current tests establish stable profile hashes, declarative predicates,
duplicate-key rejection, default grader resolution, type-sensitive exact
grading, string normalization, one absolute-tolerance boundary, generic result
materialization, conditional root-cause applicability, slices, partial output,
and execution failure accounting.

Add one compact, table-driven preflight test for bad receipt paths, wrong output
types, unsupported predicates, unknown grader versions, and invalid grader
configuration. Add grader tests for relative tolerance, integer/float and
boolean boundaries, aliases, unknown normalization options, duplicate custom
registration, and a custom grader exception becoming `grader_error` without
entering the accuracy denominator.

These cases directly protect scoring correctness. Do not add separate tests
for every Pydantic field constraint already owned by the validation library.

Implemented 2026-07-21: a deterministic grader exception is preserved as a
contract-valid `grader_error` attempt with its actual output retained and no
accuracy contribution. The remaining preflight and grader boundary matrix is
still open.

### Real command entry points and failure exit behavior

Related plans: `repeatable-project-bootstrap.md`,
`immutable-agent-versions-and-benchmark-linkage.md`,
`evidence-first-eval-result-inspection.md`, and
`reproducible-eval-execution-and-model-comparison.md`.

Current tests call selected `main()` functions in-process, but the reusable
`mi-core/cli/src/cli/` package is not executed and the agent-version and eval
commands are not covered as installed commands.

Add a small installed-command smoke matrix that invokes temporary-project
versions of:

- project validation or bootstrap;
- pipeline registry build and one deterministic pipeline run;
- eval dry-run followed by resume or failed-only rerun;
- agent-version resolve, promote, verify, and reconstruct; and
- review summary, one filtered drill-down, and purge dry-run.

Assert exit code, machine-readable output, and fail-closed behavior for an
invalid path or identity. Prefer this cross-command contract test over unit
tests for argument-parser construction or terminal presentation.

## P1 Missing Tests

### Hosted and direct benchmark adapter equivalence

Related plan: `schema-driven-evaluation-and-scoring.md` and
`published-benchmark-and-frozen-evidence-consumption.md`.

The two adapters are well covered independently, including immutable schema
and artifact identity, but no test feeds an equivalent publication through
both adapters and compares the resulting `BenchmarkVersion`. Add one shared
fixture equivalence test, plus one hosted-command failure test for a nonzero
exit, malformed JSON, and missing publication identity. This guards the
documented adapter-neutral boundary without testing transport-library details.

### Bootstrap rollback after a mid-operation failure

Related plan: `repeatable-project-bootstrap.md`.

Current tests prove that an initially non-empty destination is unchanged and
that secret-shaped template files are excluded. Add a failure-injection test
after copying/rendering but before final validation or Git initialization. It
should prove that the destination is either absent or clearly incomplete and
that a retry cannot mistake partial output for a valid project.

### Version-aware historical result reading

Related plan: `schema-driven-evaluation-and-scoring.md`.

The plan promises that schema-v2 fixtures remain readable without inferring
schema-v3 fields, but the suite contains no historical v2 fixture test. Add a
single golden v2 result and assert explicit version detection, preserved known
values, and `unknown` or absent treatment for fields introduced in v3. Do not
duplicate the full v3 orchestration suite for v2.

### Comparison drill-down identities

Related plans: `evidence-first-eval-result-inspection.md` and
`reproducible-eval-execution-and-model-comparison.md`.

Current comparison tests validate declared dimensions, child manifests,
aligned aggregate metrics, and foreign-result rejection. Add a paired
baseline/candidate test where improved, regressed, unchanged, failed, and
missing work coexist. Assert that drill-down identities exactly reconcile to
the aggregate counts and select the correct execution generation.

### Core pipeline stage and executor contract

The use-case eval tests simulate retrieve, process, and act failures, but
`mi-core` directly tests only process-stage telemetry failure and selected
subprocess telemetry hooks. Add a reusable framework test that runs a minimal
pipeline through successful retrieve/process/act and one failure at each stage,
then compares receipt identity, preserved partial data, error-chain details,
and terminal status across serial, threaded, and process orchestration.

## P2 And Explicitly Deferred Tests

The following additions are lower value unless the corresponding behavior is
being changed:

- exhaustive tests for terminal art, colors, animations, and prompt wording;
- line-coverage tests for `__init__` modules, abstract methods, and trivial
  model accessors;
- a unit test per CLI parser option when an installed-command contract already
  covers the workflow;
- live Azure, database, or model-provider calls in the default unit suite; and
- broad snapshots of manifests or result files that obscure which invariant
  failed.

Keep live provider and Azure checks opt-in. Default CI should continue using
injected repositories, deterministic model backends, temporary Git
repositories, and local content-addressed stores.

## Recommended Implementation Order

1. Process execution plus interruption/resume.
2. Dirty agent-version security and CAS corruption.
3. Review-capture failure isolation and transcript integrity.
4. Profile/grader failure semantics.
5. Installed-command smoke matrix.
6. Adapter equivalence, historical v2 reading, comparison drill-down, and
   bootstrap rollback.

After each addition, rerun the complete suite. Do not establish a blanket
coverage threshold until subprocess measurement and the intentionally optional
provider smoke tests are accounted for.
