# Selective Cloud Publication Of Eval Results Plan

## Status

Approved from product-owner decisions and implemented in Agent Workbench on
2026-07-23. Phases 1-4 are complete in this repository. Phase 5 requires the
external Azure infrastructure owner to provision the dedicated container,
assign RBAC, select the immutability/recovery policy, and run the documented
live verification. Phase 6 remains intentionally deferred.

## Outcome

An FDE can explicitly publish a complete elevated evaluation to durable Azure
storage. Each publication is an immutable record of one observed agent
evaluation against one published benchmark version. Mesh operators, the
originating FDE, and eventually customer-facing Benchmark Studio views can read
the same versioned contract without giving Agent Workbench permission to change
Benchmark Studio data.

Publication is not an approval or signoff workflow. A completed eval is factual
evidence of what the identified agent occurrence produced and how the
configured graders scored it. Elevation selects results worth retaining;
publication makes an elevated result durably available.

Benchmark Studio remains the source of truth for benchmark membership,
approved labels, label schemas, and frozen evidence. Published evals remain
Agent Workbench observations about that truth.

## Product Decisions

1. Publish only explicitly elevated evals. Never upload working evals
   automatically.
2. Every actual eval execution has a unique occurrence identity, even when its
   resolved inputs and configuration match another execution.
3. Keep the deterministic resolved-run-specification hash as a separate
   configuration identity. Do not use it as the eval occurrence ID.
4. Every publish action creates a new immutable publication event, including
   when the same retained eval was published before.
5. Do not add approval, annotation, editing, recommendation, or supersession
   state to evals or publication events.
6. A publishable eval must record a clean agent-version surface and exact Git
   commit at execution time. Dirty or untracked content in that captured
   surface remains valid for local working/elevated experimentation but cannot
   be published. Unrelated repository changes and the publisher's current
   working-tree state do not affect the immutable recorded provenance.
7. Publish full unit-level expected outputs, final AI responses, extracted
   outputs, validation status, grading outcomes, errors, usage, and cost.
8. Publish aggregate timing sufficient to answer how long the evaluation took.
   Do not publish retries, tool traces, model-call timing, invocation logs, or
   per-stage/per-attempt latency detail.
9. The cloud representation may be a verified subset of the richer local
   retained representation.
10. Store eval results in a destination logically and permission-wise separate
    from Benchmark Studio's benchmark and frozen-evidence storage contract.
11. Refuse publication unless every canonical selected unit has
    `execution_status: completed`. Completed units with invalid output, an
    incorrect valid output, a grader error, or an unscored result remain
    publishable and distinguishable.

## Assessment Of The Current Output

The current working/retained separation is the right publication foundation:

- retained evals are compact aggregate artifacts rather than file-per-unit
  trees;
- benchmark version, source-state hash, selected examples, label schemas,
  evidence references, agent version, model, pricing, grader, and configuration
  are preserved;
- expected and actual outputs remain separately inspectable;
- attempt and retained artifact integrity is hashed and verified; and
- disposable traces and detailed performance observations are already
  separated from durable evaluation evidence.

Two changes are required before cloud publication:

1. **Eval identity is currently configuration identity.** `run_id` is derived
   from `run_spec`, so an identical command resolves to the same run and resumes
   it. That cannot represent multiple nondeterministic observations of the same
   agent/configuration.
2. **High-level timing is pruned during elevation.** The retained contract must
   preserve an aggregate active evaluation duration before disposable
   performance records are removed.

Cloud publication should build on the corrected retained contract. It should
not upload the current rich working directory or introduce a second eval
scoring representation.

## Identity Model

Keep four identities explicit:

| Identity | Meaning | Behavior |
|---|---|---|
| `run_spec_sha256` | Exact resolved agent, benchmark, scope, model, runtime, grader, and harness configuration | Deterministic; equal specifications have equal hashes |
| `eval_run_id` | One actual evaluation occurrence | Unique for every newly started eval |
| `retained_eval_id` | The compact elevated representation of one eval occurrence | Stable for that elevated occurrence |
| `publication_id` | One cloud publication event | New for every publish action |

### Eval occurrence identity

Create an occurrence seed before executing any work:

```json
{
  "schema_version": 1,
  "created_at_utc": "<UTC timestamp>",
  "nonce": "<cryptographically random value>",
  "run_spec_sha256": "<resolved specification SHA-256>"
}
```

Derive `eval_run_id` from the canonical seed hash. Store the complete seed in
the manifest. The timestamp is useful for display; the random nonce prevents
collisions and makes two starts in the same clock interval distinct.

Starting an eval creates a new occurrence by default. Resuming requires an
explicit exact `eval_run_id`. Resume must verify that the stored specification
matches any supplied configuration before executing missing work. A fresh run
with the same inputs creates new work-item IDs and new model calls.

Cloud publication does not introduce a new local rerun policy. If the supported
local workflow produces a later terminal generation for a previously failed or
cancelled work item, retained materialization selects the canonical terminal
generation under the existing result contract. Publication preflight evaluates
those verified retained unit records: every selected unit must have
`execution_status: completed`. Earlier local generations remain disposable
working detail and are not published.

Do not overload invocation IDs as eval occurrence IDs. Invocations remain
operator/execution history within one resumable occurrence.

### Retained identity

Derive `retained_eval_id` from a non-circular canonical retained-identity seed
containing:

- retained schema version and lifecycle state;
- the corrected `eval_run_id` and `run_spec_sha256`;
- complete benchmark identity and source-state hash; and
- agent-version ID and manifest identity.

Do not include retained artifact hashes in this seed and do not derive the ID
from any artifact that embeds `retained_eval_id`. After deriving the ID, bind it
into the retained artifacts and record the SHA-256 and byte size of every
artifact in the retained manifest. The manifest is the integrity root for the
artifact set. Two different eval occurrences remain different retained evals
even if their outputs happen to match.

### Publication identity

Every publish operation creates a publication seed containing:

- publication schema version;
- publication timestamp and random nonce;
- project key;
- source `retained_eval_id` and `eval_run_id`;
- benchmark key, version ID, version number, and source-state hash;
- agent-version ID and clean Git commit; and
- the SHA-256 and byte size of every published payload artifact.

Derive `publication_id` from the canonical seed hash. Re-publishing the same
retained eval creates a new seed and therefore a new event. There is no
event-level deduplication, update, annotation, or supersession.

## Retained Contract Change

Bump the affected eval and retained manifest schemas rather than giving new
meaning to schema version 1.

The retained `result.json` must add:

```json
{
  "run": {
    "eval_run_id": "<unique occurrence>",
    "run_spec_sha256": "<deterministic configuration>",
    "started_at_utc": "<timestamp>",
    "completed_at_utc": "<timestamp>"
  },
  "summary": {
    "timing": {
      "evaluation_active_wall_seconds": 0.0
    }
  }
}
```

`evaluation_active_wall_seconds` is the sum of wall-clock durations for
work-bearing eval invocations. It excludes time between interrupted/resumed
invocations and excludes no-op resume or rematerialization passes. It is an
aggregate observation, not part of `run_spec_sha256`.

Do not retain:

- individual invocation events;
- individual attempt or stage duration;
- model-call duration distributions;
- retry telemetry; or
- tool/intermediate trace timing.

## Published Artifact Contract

Use a small versioned bundle under one immutable publication prefix:

```text
<eval-results-container>/
  projects/<project-key>/
    benchmarks/<benchmark-key>/v<benchmark-version>/
      publications/<publication-id>/
        publication-manifest.json
        result.json
        units.json
        evidence-references.json
        agent-provenance.json
```

### `publication-manifest.json`

This is the discovery and integrity root. It contains:

- `published-eval/v1` contract identifier;
- `publication_id` and publication timestamp;
- project and use-case identity;
- source retained-eval and eval-occurrence identity;
- complete published benchmark identity and source-state hash;
- agent-version ID and clean Git commit;
- resolved specification hash and selected-example-scope hash;
- counts for selected units, execution states, output-contract states, and
  scoring states;
- artifact SHA-256, byte size, media type, and relative blob name; and
- publisher tool contract version.

The manifest contains no mutable title, annotation, approval, status,
recommendation, or supersession fields.

### `result.json`

Publish the retained aggregate result containing:

- accuracy, reliability, and scoring coverage;
- token usage and frozen cost calculations;
- aggregate active evaluation wall time;
- model provider, model ID, API mode, reasoning/configuration values, and
  frozen pricing snapshot;
- grader IDs, versions, and configuration;
- agent-version and clean source revision;
- benchmark identity, source-state hash, label-schema identities, scope hash,
  and selected example IDs; and
- evaluation profile, pipeline, evidence-recipe, and harness identity needed to
  explain the result.

### `units.json`

Publish one entry per selected example and repetition with:

- example, unit, decision timestamp, and source-snapshot identity;
- expected benchmark values and applicable fields;
- full final AI response;
- extracted/normalized actual values and confidence values where configured;
- output-contract validation result and errors;
- field-level grader result and complete-evaluation correctness;
- execution and scoring status;
- token usage and cost for the attempt where available; and
- repetition identity within the eval occurrence.

Do not include exact request payloads, tool traces, intermediate model
responses, retry histories, or detailed timing. Publication performs typed
contract validation but does not scan, redact, or reinterpret the benchmark
values or final AI decision content.

### `evidence-references.json`

Preserve the existing immutable evidence references, sizes, SHA-256 values,
source snapshot IDs, recipe identity, and decoding contract. Do not copy frozen
benchmark evidence into the eval-results container.

### `agent-provenance.json`

Publish only the clean-commit provenance captured by the evaluated
agent-version manifest:

- repository identity;
- Git commit;
- pipeline, prompt/asset, output-schema, evaluation-profile, grader,
  dependency-lock, model-policy, evidence-recipe, and source-manifest hashes;
  and
- agent-version manifest identity.

Do not publish `agent.patch`. Its presence, a recorded agent-version
`tree_state` other than `clean`, a missing recorded Git commit, or a captured
dirty overlay causes publication preflight to fail. Publication preflight uses
this immutable recorded provenance; it does not inspect or constrain the
publisher's current working tree or unrelated files outside the captured
agent-version surface.

## Publication Workflow

Add one non-interactive, scriptable Workbench command:

```bash
uv run python -m src.eval_publication.cli publish \
  <retained-eval-id> \
  --yes \
  --json
```

Also provide a dry run:

```bash
uv run python -m src.eval_publication.cli publish \
  <retained-eval-id> \
  --dry-run \
  --json
```

The workflow:

1. resolves one exact retained eval;
2. runs existing retained-artifact verification;
3. verifies that the source eval is complete;
4. refuses the eval unless every canonical selected unit has
   `execution_status: completed`;
5. requires clean recorded agent-version provenance with an exact commit;
6. validates all required benchmark, evidence, model, pricing, grader, scope,
   unit, cost, usage, and aggregate timing fields;
7. derives the cloud subset from retained artifacts;
8. computes every payload artifact identity;
9. during dry run, shows the destination parent, retained/eval IDs, artifact
   list, counts, byte sizes, excluded categories, and that no publication event
   or `publication_id` has been allocated;
10. for an actual publish, creates the timestamp and random nonce, derives the
    unique `publication_id`, and resolves its immutable prefix;
11. uploads payload artifacts using create-only conditional writes;
12. downloads and verifies every payload artifact hash and byte size;
13. uploads `publication-manifest.json` last using a create-only conditional
    write as the commit marker;
14. downloads and verifies the committed manifest; and
15. reports the publication ID and immutable prefix.

If a failure occurs before the manifest commit marker exists, the prefix is
incomplete and must not be discoverable as a publication. A retry creates a new
publication event; it does not mutate or complete the abandoned event in place.
Operational cleanup of incomplete prefixes is separate from the published-eval
contract and must target an exact prefix.

A dry run is a pure preview, not a publish action. It does not create a
publication seed, reserve a prefix, upload blobs, or return a
`publication_id`. A later actual publish is a new action and creates its event
identity only after preflight succeeds.

Do not add publish, delete, annotate, or edit actions to the eval explorer.

## Azure Storage And Authorization

Provision or select a dedicated eval-results container. Do not place published
evals in `source-snapshots` and do not grant the publisher a Benchmark Studio
database write role.

Required access boundaries:

- the supported Workbench command performs only conditional create operations
  in the eval-results destination;
- the publisher continues to read published benchmark/evidence inputs through
  the existing read-only identities;
- the future Benchmark Studio API identity receives read-only access to the
  eval-results container;
- browser clients never receive storage write credentials or direct publisher
  authority; and
- the publication code uses Entra credentials, not account keys, SAS tokens,
  connection strings, or stored client secrets.

Azure built-in data roles do not make the publisher credential itself
create-only. Conditional blob creation, unique content-bound prefixes, and
manifest/artifact verification enforce create-only behavior in the supported
application path. If storage-enforced mutation resistance is required, the
deployment must also configure an Azure immutable-storage policy with an
explicit durability period. Without that policy, blob versioning and soft
delete are operational recovery controls only; they do not make the credential
incapable of overwrite or deletion. Application overwrite and deletion remain
unsupported in either configuration.

Container identity belongs in project/deployment configuration, not in the
scientific run specification. Publication destination changes must not change
`run_spec_sha256`.

## Read Contract For Benchmark Studio

Cloud publication is implemented in Agent Workbench first. The later Benchmark
Studio page is a separate consumer feature, but it should consume this contract
without reshaping scientific truth.

The future FastAPI boundary should:

- list only prefixes with a valid committed `publication-manifest.json`;
- scope results to the configured project and use case;
- verify publication ID, artifact size, and SHA-256 before returning content;
- expose summary/list responses separately from full unit detail;
- paginate unit results without recalculating stored grades, costs, or timing;
- retrieve frozen evidence through existing Benchmark Studio evidence
  authorization rather than trusting a browser-supplied storage reference; and
- remain read-only for publications.

The future customer UI may present a curated progress-oriented view, while
FDE/internal views expose deeper unit inspection. Presentation differences do
not create different eval truth, mutate publications, or require different
stored publication artifacts.

## Implementation Sequence

### Phase 1: Correct eval occurrence identity

Change:

- `agent-dev-eval-core/evaluation/identity.py`
- `src/evals/run_store.py`
- `src/evals/eval_orchestration.py`
- `src/evals/comparisons.py`
- inspection/explorer contracts that currently assume deterministic `run_id`
- run, resume, lifecycle, comparison, and explorer tests

Deliver:

- deterministic `run_spec_sha256`;
- unique `eval_run_id` per new eval;
- explicit exact-ID resume;
- fresh identical-spec execution as a new occurrence; and
- paired comparison across separate occurrences.

This phase is a prerequisite. Do not hide the identity mismatch inside the
publisher.

### Phase 2: Retain aggregate timing and clean provenance status

Change the result materialization and elevation contract to preserve aggregate
active wall time and make clean/dirty provenance an explicit retained field.
Keep detailed performance disposable. Update retained schema verification and
the local explorer's high-level timing display as needed.

### Phase 3: Define and validate the cloud subset

Add typed/versioned publication models and one pure transformation from a
verified retained eval to the proposed published artifacts. Keep this phase
storage-independent. Add fixture/golden-contract tests covering complete,
invalid, grader-error, unscored, and partially costed unit outcomes, plus a
preflight test that refuses an eval whose canonical selected units include any
missing, failed, or cancelled result.

### Phase 4: Add Azure create-only publication

Add `src/eval_publication/` with the preflight, dry-run, publisher, verifier,
and CLI. Reuse the repository's Azure Identity conventions. Keep publication
storage separate from the frozen-evidence reader abstraction because it has
different permissions and semantics.

### Phase 5: Provision and live-verify the destination

Provision the dedicated container and exact RBAC assignments through the
repository that owns the relevant Azure infrastructure. Verify:

- publisher write and post-write read;
- publisher cannot write Benchmark Studio PostgreSQL or `source-snapshots`;
- consumer read-only access;
- account-key/SAS-free operation;
- conditional create refusal for an existing blob;
- the selected storage immutability or operational-recovery configuration and
  its exact guarantees;
- committed-manifest discovery; and
- full download/hash verification.

### Phase 6: Add the Benchmark Studio consumer later

Implement a read-only FastAPI adapter and customer/FDE views only when that
feature is scheduled. Do not block Workbench publication on the final customer
presentation design.

## Existing Data And Compatibility

Inventory current meaningful retained evals before changing schema. Prefer:

- leaving disposable schema-v1 working runs local and deletable;
- rerunning/elevating a meaningful result under the unique occurrence schema;
  and
- refusing cloud publication for legacy retained artifacts that lack unique
  occurrence identity, aggregate timing, or clean-commit proof.

Do not build a generalized migration or compatibility layer solely to publish
old exploratory runs. If a specific legacy retained eval must be preserved,
decide its one-time conversion explicitly from its verified source artifacts.

## Validation

### Identity

- Two new evals with identical resolved specs have equal
  `run_spec_sha256` and different `eval_run_id` values.
- An exact resume retains its `eval_run_id` and executes only missing work.
- Resume refuses a conflicting resolved specification.
- A repeated publish of one retained eval produces a different
  `publication_id`.

### Publication gates

- Working, incomplete, corrupt, or unknown evals are refused.
- Any eval whose canonical selected units are not all
  `execution_status: completed` is refused.
- A recorded dirty agent-version surface, captured dirty overlay or patch, and
  missing recorded Git commit are refused; unrelated repository changes at
  publication time are ignored.
- Missing model, pricing, grader, benchmark hash, evidence identity, selected
  IDs, usage/cost coverage state, or aggregate timing is refused.
- No approval or annotation data is required.

### Content

- Full expected values and final AI responses survive publication.
- Valid/incorrect, invalid, grader-error, and unscored completed outcomes remain
  distinguishable.
- Aggregate metrics match the verified retained source exactly.
- Published artifacts omit tool traces, retries, invocation logs, detailed
  latency, patches, and local evidence copies.
- Publication does not scan or redact benchmark values or final AI decision
  content.

### Integrity and storage

- Artifact hashes and byte sizes verify after upload.
- The publication ID verifies against its seed and artifact identities.
- A prefix without its manifest commit marker is not discoverable.
- Existing blob names cannot be overwritten by the supported publisher.
- Wrong project prefix, corrupt blob, missing blob, and unauthorized access
  fail closed.
- Publishing never writes Benchmark Studio PostgreSQL or benchmark/evidence
  blobs.

### Consumer contract

- Summary discovery does not require downloading all unit results.
- Full unit retrieval returns expected values, final AI output, validation,
  grading, model/configuration, price/cost, usage, and high-level timing.
- Customer and FDE presentation adapters read the same immutable publication.

## Explicit Non-Goals

- automatic publication after elevation;
- cloud publication of working evals;
- approval or signoff workflows;
- eval annotations, edits, recommendations, or supersession;
- publication deduplication;
- cloud mutation or deletion UI;
- detailed performance, retries, tool traces, or intermediate model messages;
- copying frozen evidence into the eval-results container;
- recalculating historical grades, costs, or timing during reads;
- browser-direct writes;
- portable agent packaging or production deployment; and
- making eval publications part of Benchmark Studio benchmark truth.

## Completion Criteria

The feature is complete when two identical-spec eval executions produce two
independently retainable occurrences; a clean, complete retained occurrence can
be explicitly published as a new immutable cloud event only when every
canonical selected unit completed execution; the uploaded subset contains all
unit-level and aggregate information required for future customer/FDE review;
the bundle verifies after download; and the publisher has no path to mutate
Benchmark Studio benchmark truth.
