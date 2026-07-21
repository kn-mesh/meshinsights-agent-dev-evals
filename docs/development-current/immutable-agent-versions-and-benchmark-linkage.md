# Immutable Agent Versions And Benchmark Linkage

**Status:** Implemented for MVP

**Implementation summary:** Deterministic candidate manifests, Git plus exact
dirty overlays, conservative runtime-surface capture, component prompt/skill/
tool/schema/evidence/action declarations, per-pipeline model override policy,
local content-addressed storage, promotion/alias records, verification and
reconstruction, and schema-v3 eval/run/attempt linkage are implemented. Cloud
publication, signing, deletion/reference lifecycle, and portable production
packaging remain separate features.

**Backlog feature:** `docs/development-backlog/features.md` → Immutable Agent
Versions And Benchmark Linkage

**Related active designs:**

- `docs/development-current/reproducible-eval-execution-and-model-comparison.md`
- `docs/development-current/schema-driven-evaluation-and-scoring.md`

## Outcome

Give every evaluation an exact, inspectable agent-version identity and let an
FDE explicitly promote a useful candidate without copying the repository by
hand.

The finished workflow will:

- resolve a deterministic candidate agent-version manifest before the first
  model call;
- give the same resolved agent content, source representation, and override
  policy the same content-addressed version ID;
- make every schema-v3 eval result link that exact version to immutable Azure
  benchmark, example-selection, model/runtime, grader, and result-schema
  identities;
- promote a candidate by retaining and cataloging its existing manifest and
  content-addressed objects, rather than recopying its source tree;
- use a clean Git revision as the efficient source anchor and store only
  non-Git assets or an explicitly accepted dirty overlay as additional blobs;
- verify pipeline wiring, registry resolution, prompts, skills, tools, schemas,
  action policy, dependency/runtime versions, and evidence-recipe provenance;
- reject ambient defaults, missing assets, mutable external references,
  secrets, and unsupported runtime overrides before execution or promotion;
  and
- reconstruct and inspect the complete version from its Git base plus verified
  content-addressed objects.

The immutable ID is the scientific identity. A pipeline filename or its
displayed `version` remains a useful human label but is not an agent version.

## Non-Goals

This feature does not:

- move benchmark ownership, labels, membership, or source evidence out of
  Benchmark Studio and Azure;
- publish agent versions or eval results to cloud storage;
- define the later portable production-agent package;
- sign releases or provide a customer approval workflow;
- package credentials, provider secrets, unrestricted model traffic, or Azure
  benchmark evidence;
- make the local workbench a production runtime;
- infer production readiness from promotion;
- make arbitrary Python execution hermetic across operating systems; or
- delete versions, results, or referenced content-addressed objects. Those
  lifecycle operations belong to the adjacent Local Version And Result
  Lifecycle feature.

Promotion means “retain this exact working version as a named, inspectable
development milestone.” It does not mean deployment approval.

## Current Foundations And Gaps

The repository already has most of the raw identities needed by this feature:

- `src/evals/run_specs.py` hashes a conservative execution-relevant source
  manifest and records Git revision plus `clean|dirty|unavailable` tree state;
- `src/evals/eval_orchestration.py` resolves pipeline YAML, runtime model and
  reasoning overrides, benchmark source-state identity, scoring identity,
  dependency files, and result schema version into a deterministic run spec;
- `src/evals/run_store.py` persists an immutable run manifest and append-only
  attempt generations;
- the component registry resolves YAML class names to import and source paths;
- `uv.lock` and the three project package versions identify the Python
  dependency environment;
- Agent Skills expose their source paths, while prompts, tools, and structured
  output schemas are currently embedded in component Python source; and
- published benchmark models already contain benchmark name/key, immutable
  version ID/number, source-state hash, label-schema hashes, exact selected
  examples, and immutable raw-artifact hashes.

The remaining gaps are material:

- `--agent-version` is a free-form nullable label and has no verification
  contract;
- the current source manifest is intentionally broad but cannot explain which
  resolved pipeline component or asset each file supplies;
- registry `ComponentRecord.hash` identifies class name/path/line, not source
  content, so it is not an integrity hash;
- no contract enumerates embedded prompts, external prompt files, Agent
  Skills, tools, schemas, evidence recipes, or action assumptions;
- default component configuration and permitted model/runtime overrides are
  not frozen as an agent-version policy;
- a Git commit alone does not preserve dirty working bytes, untracked assets,
  or files from installed distributions;
- eval results do not carry an immutable agent-manifest hash; and
- no explicit promotion, verification, inspection, or reconstruction command
  exists.

## Decisions

### Candidate resolution and promotion are separate

Every eval resolves an immutable **candidate agent version**. Promotion does
not create a different version; it changes retention and catalog state for the
same immutable ID.

This solves two otherwise competing needs:

- experimentation remains one command and does not require naming every trial;
- every result still references exact agent content, rather than an
  uninspectable pipeline filename; and
- promoting a useful run is fast and idempotent because its manifest and blobs
  already exist.

Candidate/promoted state is catalog metadata and is excluded from version
identity. Re-promoting identical content returns the same version ID.

### Use Git plus a small content-addressed overlay

The primary source anchor is a Git commit and its tree. For a clean version,
tracked project and local `mi-core` source are already content-addressed by Git;
the version store does not duplicate those files.

The local version store retains only:

- the canonical agent-version manifest;
- assets not guaranteed by the Git tree, such as permitted external files or
  installed-distribution metadata;
- dirty working-tree bytes and deletion tombstones when dirty promotion is
  explicitly allowed; and
- optional normalized inspection documents derived from the manifest.

The resolver still records SHA-256 for each resolved execution asset, even
when Git owns its bytes. Git is the reconstruction mechanism; SHA-256 is the
uniform validation and cross-store integrity mechanism.

### Identity is content based, not label based

Canonical JSON is encoded as UTF-8 with sorted object keys, compact separators,
JSON scalar validation, normalized repository-relative POSIX paths, and no
timestamps. Derive:

```text
agent_version_manifest_sha256 = sha256(canonical_identity_manifest)
agent_version_id = av_<first 24 lowercase hex characters>
```

Persist the full hash and compare it on every open. The short ID is only a path
and CLI token. Fail closed on a full-hash mismatch or truncated-ID collision.

Display names, release notes, promoter identity, promotion time, and aliases
live in catalog records outside the identity manifest. An optional
`source_pipeline.display_version` is part of provenance but never substitutes
for the immutable ID.

### The version freezes behavior; the eval freezes one allowed execution

An agent version contains:

- a default model/runtime configuration; and
- an explicit override policy describing which fields may vary and their
  allowed values or constraints.

An eval result contains the exact effective model/runtime configuration used.
Changing an allowed model or reasoning effort produces a different `run_id`
but not a different `agent_version_id`. Changing the override policy or an
otherwise frozen setting produces a different agent version.

No ambient environment variable may change versioned behavior silently.
Credentials and endpoints selected by deployment may remain external, but the
semantic provider, API family, model/deployment selector, backend policy, and
override boundary must be explicit.

### Benchmark identity stays outside the agent version

An agent version can be evaluated against multiple published benchmarks. The
benchmark is therefore not part of `agent_version_id`.

The eval run is the immutable linkage record between:

- agent version;
- Azure-owned published benchmark and selected examples;
- effective model/runtime configuration;
- evaluation profile and graders; and
- result/execution contract versions.

The agent version may record optional provenance such as the source pipeline or
eval run from which it was promoted. That provenance is not a claim that the
agent is valid only for that benchmark.

### Resolution must be explainable and extensible

Do not rely only on repository-wide globs or static import analysis. Resolve
the YAML through the same forced registry scan and schema validation used by
`PipelineBuilder.from_yaml`, then produce a typed component graph.

Add a generic, side-effect-free `VersionAssetProvider` contract in `mi-core`
for a component to declare behavior-bearing resources not represented by its
own source file. The provider receives validated component configuration and
returns typed declarations; it must not contact a model, source system, or
secret store.

The built-in declaration roles are:

- `prompt`;
- `skill`;
- `tool_definition`;
- `agent_asset`;
- `input_schema`;
- `output_schema`;
- `action_policy`;
- `evidence_recipe`;
- `transform`;
- `model_policy`; and
- `runtime_contract`.

Embedded prompts, nested tool functions, and Python-defined schemas point to
the supplying source asset plus a qualified symbol. External files receive
their own content entry. Components with undeclared dynamic file loading fail
strict promotion preflight.

### Project-owned version policy is explicit

Current `.ppln` files intentionally omit default model selection, while evals
accept model and reasoning overrides. Do not derive the agent's model policy
from whichever eval CLI flags happened to be used first.

Add a small versioned descriptor under
`agent_version_configs/<pipeline-stem>.agent.yaml`, or accept an explicit
`--agent-policy` path. It contains only declarations that are not properties of
one component:

- source-pipeline path;
- default model/reasoning configuration;
- permitted override keys and constraints;
- extra version assets or version-surface exclusions;
- project-level trigger, action, evidence, and compatibility assumptions; and
- a policy schema version.

The descriptor is itself a hashed version asset. Component declarations remain
authoritative for component-owned prompts, skills, tools, schemas, and files;
the descriptor must reference or augment them, not duplicate their contents.
An AI pipeline without an explicit model policy may be inspected as an
incomplete candidate, but it cannot run a newly linked eval or be promoted.

## Identity Model

Keep these identities distinct:

### `agent_version_id`

Hash of the canonical, behavior-bearing version manifest. It is stable across
promotion state, aliases, annotations, and eval runs.

### `agent_candidate_id`

There is no second content identity. “Candidate” is a lifecycle state of an
`agent_version_id`. Run-local candidate manifests use the same validation and
ID rules as promoted versions.

### `run_id`

Hash of the resolved eval specification. It includes the exact
`agent_version_id`, manifest hash, effective allowed overrides, benchmark,
selected examples, scoring contract, repetition plan, and execution policy.

### `promotion_id`

Occurrence identity for an append-only promotion event. It records who, when,
source run, alias, notes, and policy warnings. It is audit metadata, never an
agent or scientific identity.

### Asset `content_sha256`

Full SHA-256 of the exact bytes or canonical structured value represented by
an asset. Identical blobs deduplicate across versions and runs.

## Agent-Version Manifest Contract

Use manifest schema version 1. Keep identity-bearing content under `identity`;
put occurrence metadata in a separate catalog/promotion record so accidental
timestamps cannot change the ID.

Conceptual example:

```json
{
  "schema_version": 1,
  "agent_version_id": "av_0123456789abcdef01234567",
  "manifest_sha256": "0123456789abcdef...",
  "identity": {
    "source": {
      "repository_id": "meshinsights-agent-dev-evals-mvp",
      "git_revision": "<40-hex commit>",
      "git_tree": "<git tree object id>",
      "tree_policy": "clean_version_surface",
      "tree_state": "clean",
      "dirty_overlay_sha256": null
    },
    "source_pipeline": {
      "path": "pipeline_configs/v2.ppln",
      "name": "pulse_alarm_failure_analysis_v2",
      "display_version": "2.0.0",
      "source_sha256": "...",
      "canonical_config_sha256": "...",
      "resolved_graph_sha256": "..."
    },
    "components": [],
    "assets": [],
    "contracts": {
      "structured_input": {},
      "structured_output": {},
      "action_policy": {},
      "evidence_recipe": {}
    },
    "dependencies": {
      "python": "3.13.x",
      "lock_path": "uv.lock",
      "lock_sha256": "...",
      "project": {"name": "mesh.insights.template", "version": "0.3.0"},
      "eval_core": {"name": "agent-dev-eval-core", "version": "0.1.0"},
      "mi_core": {"source": "git_tree", "content_sha256": "..."}
    },
    "model_policy": {
      "defaults": {},
      "permitted_overrides": {},
      "policy_sha256": "..."
    },
    "runtime_contract": {
      "agent_version_contract_version": 1,
      "pipeline_execution_contract_version": 1,
      "compatible_result_schema_versions": [3]
    }
  }
}
```

`manifest_sha256` is computed over `identity`, plus `schema_version`, using the
shared canonical JSON helper. The stored envelope fields are then verified
against that result. Nested `*_sha256` values make subsections independently
inspectable but do not replace the whole-manifest hash.

### Source and dirty overlay

Record:

- repository identity, Git revision, and root tree object;
- tree policy and resolved version-surface roots;
- clean/dirty/unavailable state for that surface;
- every included dirty path as `add|modify|delete`, base object identity when
  present, replacement blob SHA-256/size/media type when present, and file mode;
- a canonical overlay hash; and
- ignored dirty paths and the reason they cannot affect execution.

Never store a textual patch as the only dirty artifact. Exact replacement
bytes plus deletion tombstones reconstruct deterministically and do not depend
on patch context.

### Pipeline and component graph

Record the source YAML bytes and canonical parsed configuration separately.
The resolved graph contains ordered stage entries for metadata type, process
and action objects, retrievers, hydrators, processors, and actions. Each entry
contains:

- stage, order, configured class name, qualified import path, and registry
  source locator;
- canonical effective constructor configuration after defaults and relative
  path resolution, with secret fields rejected/redacted before hashing;
- source asset reference and content hash;
- component package/distribution and version when outside the Git tree; and
- declared version assets and contracts.

The existing registry's class/path/line hash may be retained as scanner
metadata but is not used as source integrity.

Runtime example metadata, benchmark artifact locations, logger verbosity, and
temporary `.runtime.*.ppln` paths are excluded. The resolved graph represents
the pipeline before example-specific metadata injection.

### Code, prompts, skills, tools, and assets

Every asset entry contains:

- stable role and logical name;
- origin: `git`, `overlay`, `cas`, or `distribution`;
- repository-relative path or distribution-qualified locator;
- qualified symbol when embedded in Python;
- byte size, media type, SHA-256, and executable/file-mode bit where relevant;
- supplying component IDs; and
- whether the content is required for reconstruction or only inspection.

For current pipelines:

- Python methods such as `_build_system_prompt` are frozen by their component
  source file and identified as embedded prompt symbols;
- v2 `SKILL.md` files are separate `skill` assets;
- nested `@ai_tool` definitions are identified as embedded tool symbols and
  frozen by processor source;
- Pydantic input/output classes are identified as schema symbols and frozen by
  their source, with normalized JSON Schema also stored for inspection; and
- chart rendering or other deterministic support code is part of the component
  source graph and transform/evidence-recipe declaration.

Duplicate byte content is stored once but may have multiple logical roles.

### Structured contracts and action policy

Persist normalized, inspectable contract documents for:

- trigger and structured input type, required identity fields, and decision
  timestamp assumptions;
- output schema identity and normalized JSON Schema;
- receipt location for final `agent_output`;
- allowed terminal action(s), including `NoOpAction` semantics;
- escalation, confidence, safety, and side-effect assumptions exposed by the
  component declaration; and
- compatibility with evaluation-profile output paths.

Promotion fails if an action can produce an external side effect but does not
declare its action policy. The contract describes assumptions; it does not
copy use-case business logic out of code.

### Dependency and runtime identity

Record:

- `uv.lock` bytes and SHA-256;
- root, `agent-dev-eval-core`, and `mi-core` package name/version/source;
- Python implementation and supported major/minor version;
- registry schema version and agent-version resolver version;
- exact installed distribution name/version/direct-URL identity for any
  resolved component outside the repository; and
- platform-sensitive native dependencies when a declared component says they
  affect behavior.

The lock is the dependency resolution source of truth. Do not inline the whole
lock into the manifest. Promotion fails when the active environment cannot be
reconciled with the lock for a behavior-bearing external distribution.

### Default model and permitted overrides

Normalize model policy per AI component, including:

- default model catalog key, provider, API family, and deployment/model ID;
- default reasoning effort and semantic backend options;
- timeout, transport retry, output retry, tool retry, turn, tool-call, and token
  policies;
- allowed override keys;
- enumerated values, catalog selectors, or bounded constraints for each key;
  and
- explicitly frozen fields.

An omitted default that falls back to ambient configuration is a promotion
error. Secrets, credentials, regional endpoints, tracing destinations, and
worker count are not model-policy values. Runtime/concurrency remains part of
the eval run spec where it affects observed reliability and timing.

### Source-pipeline provenance and evidence recipe

The source pipeline section records its path/name/display version, canonical
configuration hash, resolved graph hash, and optional source run ID.

The evidence-recipe contract identifies:

- retriever and retrieve hydrator components;
- required benchmark example/source-snapshot metadata fields;
- raw artifact kinds and integrity requirements;
- transform/normalization components and effective configuration;
- decision-time/window assumptions;
- source/tool capabilities available to the agent; and
- the resulting recipe hash.

Do not embed Azure benchmark rows or Blob objects. At eval time, the recipe is
combined with the selected example's immutable source-snapshot and raw-artifact
hashes in attempt evidence.

## Version Surface And Dirty-Worktree Policy

### Version surface

Define a conservative execution surface in project configuration, initially:

- `pipeline_configs/` source pipeline files, excluding generated
  `.runtime.*.ppln` files;
- `src/` use-case code and runtime assets;
- `mi-core/core/src/mi/`;
- `agent-dev-eval-core/evaluation/` only where the pipeline runtime imports it;
- `pyproject.toml`, `uv.lock`, `models.yaml`, and `model_catalog.py`;
- every file returned by a `VersionAssetProvider`; and
- explicitly registered external assets.

The resolved component and asset graph is the authoritative included subset;
the configured roots are the conservative guardrail used to detect undeclared
dirty content. Generated eval results, caches, temporary runtime YAML, logs,
docs, tests, eval/benchmark operator code not imported by the runtime, `.env*`,
credentials, and repository metadata are excluded. A dirty file under a broad
root is not automatically included: it must be reachable from the resolved
runtime graph, returned by a provider, explicitly listed by the version policy,
or proven to be a non-execution exclusion. Ambiguous reachability fails closed.

### Default policy: clean version surface

`agent-version resolve` and eval candidate resolution may observe dirty content,
but `agent-version promote` defaults to `clean_version_surface`:

- every tracked path on the resolved version surface must match `HEAD`;
- no untracked execution asset may be required;
- dirty files outside the surface are allowed only when they match an explicit
  non-execution exclusion and are reported; and
- missing/unavailable Git identity fails promotion.

This is stricter than the current run manifest because promoted reconstruction
should normally be a Git checkout plus a small manifest.

### Explicit dirty promotion

Support `--dirty-policy capture` for useful work that should not be lost before
a commit. It must be an explicit operator action and promotion record warning.

Under this policy:

1. Resolve the base `HEAD` revision and complete version surface.
2. Classify every dirty path as included overlay or approved non-execution
   exclusion.
3. Reject ambiguous, secret-like, outside-repository, ignored-but-required, or
   oversized files unless a typed asset policy explicitly permits them.
4. Store exact included replacement bytes/deletion tombstones in the CAS.
5. Re-resolve the pipeline against a reconstructed temporary tree and require
   the same agent-version ID.
6. Record `tree_state: dirty`, overlay hash, paths, and explicit policy in the
   immutable manifest.

Dirty capture is fully reproducible but intentionally more visible and less
portable than a clean version. A later clean commit containing identical bytes
produces a different source representation and therefore a different agent
version; an optional catalog relation may mark it as content-equivalent at the
resolved behavior layer, but identities are never rewritten.

### Candidate evals from dirty source

An eval may automatically create a dirty candidate manifest using the same
overlay rules so its result remains exact. If classification or secret checks
fail, the eval preflight fails rather than falling back to the current broad
source hash. `--require-clean-agent-version` allows CI or release workflows to
reject dirty candidates.

## Local Storage Layout

Use one project-local content-addressed store:

```text
agent_versions/
  manifests/
    av_<id>.json
  objects/
    sha256/<prefix>/<full-hash>
  catalog/
    promotions/<promotion-id>.json
    aliases/<normalized-alias>.json
```

Run-local candidates are first written inside the durable run directory:

```text
eval_results/<pipeline>/<benchmark>/v<version>/runs/<run-id>/
  manifest.json
  agent-version.json
  objects/sha256/...
  result.json
```

Promotion verifies the run-local candidate, hard-links or atomically copies
missing blobs into `agent_versions/objects`, writes the global manifest with
exclusive create-if-absent semantics, then appends promotion and alias records.
On filesystems without hard-link support, copy-and-verify is acceptable.

Do not create a mutable manifest index as the source of truth. Catalog views
are derived from immutable manifests, promotion records, aliases, and run
references. Object garbage collection is deferred to the lifecycle feature.

## Resolution And Promotion Workflow

### Resolve a candidate

Before eval scheduling or explicit inspection:

1. Parse and schema-validate the source `.ppln`.
2. Force a component registry scan and reject ambiguous component names.
3. Resolve effective component config including constructor defaults and
   repository-relative file paths.
4. Load and validate the pipeline's project-owned agent policy; never infer it
   from eval CLI overrides.
5. Ask each resolved component for version-asset and contract declarations.
6. Normalize structured schemas, action policy, evidence recipe, model defaults,
   and override policy.
7. Resolve Git/dependency/runtime identities and classify the version surface.
8. Validate and capture any permitted dirty overlay.
9. Hash every asset and canonical subsection.
10. Build the canonical manifest and derive `agent_version_id`.
11. Re-read referenced bytes and verify hashes before returning preflight.

Candidate resolution is side-effect-free except for writing a run-local
manifest/CAS after preflight succeeds. `--dry-run` prints the complete identity
and warnings without retaining it.

### Promote from a pipeline

```text
uv run python -m src.agent_versions.cli resolve \
  --pipeline pipeline_configs/v2.ppln \
  --agent-policy agent_version_configs/v2.agent.yaml \
  --json

uv run python -m src.agent_versions.cli promote \
  --pipeline pipeline_configs/v2.ppln \
  --alias pulse-v2-investigation-1 \
  --dirty-policy reject
```

The command resolves and verifies once, prints the ID and source state, and
atomically promotes the candidate. `--expected-agent-version-id` supports
automation without a time-of-check/time-of-use gap.

### Promote from an eval run

```text
uv run python -m src.agent_versions.cli promote \
  --from-run eval_<id> \
  --alias pulse-v2-investigation-1
```

This is the preferred workflow after an FDE identifies a useful result. It
loads the candidate embedded in the immutable run manifest, verifies its
objects and Git base, and retains the same version ID. It never resolves
against the operator's current checkout.

Promotion from a run fails when the candidate was created by an unsupported
resolver version, has missing objects, violates the requested dirty policy, or
the run manifest contradicts its agent identity.

### Inspect, verify, and reconstruct

Support stable structured commands:

```text
... agent_versions.cli inspect av_<id> --json
... agent_versions.cli verify av_<id> --mode available
... agent_versions.cli verify av_<id> --mode reconstruct
... agent_versions.cli reconstruct av_<id> --destination <empty-directory>
```

- `available` verifies the manifest, local objects, current Git object
  availability, dependency locators, and referential integrity without writing
  a checkout.
- `reconstruct` creates an isolated temporary tree from the Git revision plus
  overlay, resolves it again, and requires the same full manifest hash.
- explicit reconstruction writes only to a new/empty destination and never
  modifies the operator's checkout.

## Validation And Fail-Closed Rules

Candidate resolution and promotion must reject:

- missing or malformed pipeline/configuration files;
- ambiguous registry names or a resolved source path outside allowed roots;
- source/config bytes changing during resolution;
- undeclared dynamic assets or mutable URL-only assets;
- missing, unreadable, or hash-mismatched prompts, skills, tools, schemas, or
  agent assets;
- unversioned installed components or active packages inconsistent with
  `uv.lock`;
- ambient model defaults, unsupported override keys, or secret fields inside
  identity-bearing configuration;
- an output schema that cannot be normalized or whose declared receipt path is
  inconsistent with the pipeline handoff;
- an external action without an explicit action-policy declaration;
- an evidence recipe without source-snapshot integrity requirements;
- Git-unavailable promotion under the clean or capture policy;
- dirty surface paths under `reject`, or unclassified paths under `capture`;
- symlinks escaping the repository/version store, special device files, or
  unsafe path traversal;
- CAS blobs whose size/hash differs from the manifest; and
- a short-ID collision or an existing manifest with contradictory canonical
  content.

Warnings that do not block exploratory candidate resolution become promotion
errors unless explicitly named by policy. `--force` must not bypass integrity,
secret, ambiguity, or unsupported-contract failures.

## Eval Linkage Contract

### Run specification

Replace the current free-form `agent: {version: <string|null>}` with:

```json
{
  "agent": {
    "agent_version_id": "av_...",
    "manifest_sha256": "...",
    "manifest_schema_version": 1,
    "lifecycle_state_at_run": "candidate",
    "source_tree_state": "clean",
    "resolved_graph_sha256": "...",
    "evidence_recipe_sha256": "...",
    "model_policy_sha256": "..."
  }
}
```

The run spec also keeps exact effective overrides in its existing `model` and
`execution` dimensions. Preflight verifies those values against the version's
override policy before deriving `run_id`.

Promotion after execution does not mutate historical run/result lifecycle
state. Catalog joins can show that the referenced immutable version is now
promoted.

### Result schema v3 `run_config`

Every newly produced schema-v3 result records:

- exact agent version ID, full manifest hash/schema, source state, resolved
  graph hash, evidence-recipe hash, and model-policy hash;
- benchmark name, key, immutable version ID and number, publication time,
  published-contract schema version, and source-state SHA-256;
- sorted selected example IDs plus canonical selection/scope hash;
- referenced label-schema identities and hashes;
- exact effective provider/model/API/reasoning/backend options and semantic AI
  policies;
- execution runtime, worker/concurrency, and error policy;
- evaluation profile ID/version/hash, resolved scoring-contract hash, grader
  IDs/versions/configuration and grader-set hash, and slice-definition hash;
- run ID/spec hash and repetition plan;
- `eval_result_schema_version: 3`, execution-contract version, telemetry schema
  version, and version-resolver contract version; and
- content hashes for the materialized result and immutable attempt records as
  already defined by the run-store design.

The benchmark source-state hash is required for new linked runs. A published
contract response without it fails preflight rather than producing a weaker
link.

### Per-example and per-attempt linkage

Per-example results continue to contain the complete benchmark labels,
label-schema identity, source snapshot, raw-artifact manifest, and named
slices. Per-attempt evidence adds or verifies:

- agent version ID and run ID inherited from the run manifest;
- exact source-snapshot content hash and raw-artifact hashes;
- actual prompt/tool/evidence artifact hashes when captured; and
- effective model execution policy and receipt identity.

Do not duplicate the full agent-version manifest into every attempt. Reference
the immutable run-local/global manifest by ID and hash.

### Exploratory compatibility and migration

Historical schema-v3 results with a nullable/free-form agent label remain
readable as `legacy_unversioned`; never synthesize an agent-version ID from
their incomplete fields.

After this feature is enabled, all new eval runs resolve a candidate version
automatically. Keep `--agent-version` temporarily as a rejected/deprecated
alias unless it resolves to a real manifest; add `--agent-version-id` and
`--require-promoted-agent-version` for explicit workflows.

An eval may run directly from a stored version without consulting current
working files:

```text
... eval_orchestration --agent-version-id av_<id> ...
```

It verifies/reconstructs that version, obtains its source pipeline, applies only
permitted overrides, then derives the run ID.

## Code Ownership And Expected Changes

### `mi-core/core/src/mi/`

Own reusable mechanics:

- typed resolved pipeline/component graph generation;
- a side-effect-free `VersionAssetProvider` and standard asset/contract roles;
- normalized effective component configuration after Pydantic defaults;
- uniform source/distribution locators; and
- built-in declarations for core objects, no-op actions, AI config/model
  policy, structured schemas, Agent Skills, and tool definitions.

Do not put Spirax domain assumptions or local filesystem catalog policy in
`mi-core`.

### `agent-dev-eval-core/evaluation/`

Own only framework-neutral identity helpers if needed:

- canonical manifest envelope hashing;
- typed agent-version reference embedded in generic run/result models; and
- validation that run/attempt records agree on immutable agent identity.

It must remain independent of Git, the project registry, Spirax, and Azure.

### `src/agent_versions/`

Add project orchestration and local storage:

```text
src/agent_versions/
  models.py
  resolver.py
  git_source.py
  assets.py
  policies.py
  store.py
  verifier.py
  cli.py
```

This layer composes registry resolution, project version surface, Git/lock
identity, dirty overlay, CAS, promotion events, aliases, and reconstruction.

### Use-case components

Add explicit version declarations where behavior cannot be inferred safely:

- v1.3 and v2 processors declare embedded prompt/output-schema symbols;
- the v2 investigation agent declares four skill files and nested tool symbols;
- Azure evidence retriever and retrieve hydrator declare the evidence recipe
  and immutable source-snapshot requirements;
- process/action hydrators declare the structured handoff and receipt path; and
- `NoOpAction` declares no-side-effect action policy.

Prefer small declarative class methods or typed descriptors. Do not duplicate
prompt or skill text into version-specific metadata.

### `src/evals/`

- resolve or load an agent version before building the run spec;
- verify effective overrides against its policy;
- replace free-form agent label fields with the typed reference;
- persist the run-local candidate manifest/objects;
- add benchmark name/publication time and canonical selected-example scope hash
  where absent; and
- materialize the exact linkage into schema-v3 result JSON.

Reuse the candidate source manifest as the version/source dimension instead of
maintaining two independent file-discovery algorithms. The run spec may retain
a compatibility projection of `source_manifest`, derived from the agent
manifest during migration.

### Project configuration and docs

- add version-surface include/exclude and secret/size policy to a dedicated
  project-owned configuration file;
- add `agent_version_configs/v1_3.agent.yaml` and `v2.agent.yaml` with explicit
  default model settings and permitted eval overrides;
- ignore `agent_versions/` local artifacts by default while documenting their
  retention importance;
- update `EvalRunbook.md`, `README.md`, and relevant repo skills with stable
  non-interactive commands after implementation; and
- document that generated `.runtime.*.ppln` files are never version inputs.

## Implementation Sequence

### Phase 1: Freeze manifest and golden fixtures

- Define schema-v1 models, canonicalization, identity envelope, asset roles,
  source locators, model override policy, and dirty overlay contract.
- Build golden clean and dirty manifests for `v1_3.ppln` and `v2.ppln`.
- Reconcile the typed agent reference with run/result schema v3.
- Add migration fixtures for legacy unversioned results.

Exit criterion: independent readers derive the same full hash and reject every
single-field or blob mutation.

### Phase 2: Resolved component and asset graph

- Extend `mi-core` registry/pipeline resolution to return the typed graph and
  normalized effective config.
- Add the generic version-asset provider contract and built-in declarations.
- Add use-case declarations for prompts, skills, tools, schemas, evidence, and
  action policy.
- Validate external distribution and `uv.lock` identities.

Exit criterion: both current pipelines produce complete, explainable graphs
without executing a benchmark, model, or external action.

### Phase 3: Git source, dirty overlay, and local CAS

- Implement version-surface policy, Git tree resolution, dirty classification,
  exact overlay capture, secret/path/size checks, and CAS writes.
- Implement immutable manifest storage and collision validation.
- Implement available/reconstruct verification in isolated trees.

Exit criterion: clean promotion copies no tracked source bytes; dirty capture
reconstructs byte-for-byte and re-resolves to the same version ID.

### Phase 4: Eval integration

- Resolve a candidate before model calls and store it with the run.
- Include the typed reference and allowed effective overrides in `run_id`.
- Extend result schema-v3 linkage with complete benchmark name/version/source,
  scope, model/runtime, grader, and harness identities.
- Require benchmark source-state hash for new linked runs.
- Support execution from `--agent-version-id`.

Exit criterion: every new result navigates to an exact verified candidate or
promoted manifest, and any manifest/override mismatch fails preflight.

### Phase 5: Promotion and inspection CLI

- Add resolve, promote-from-pipeline, promote-from-run, inspect, verify, and
  reconstruct commands with human and JSON output.
- Add append-only promotion/alias records and idempotent promotion.
- Update operator documentation and repository skills.

Exit criterion: an FDE can promote a useful eval in one non-interactive command
without copying files or changing its immutable identity.

### Phase 6: Migration and hardening

- Label historical results `legacy_unversioned` without synthesizing identity.
- Deprecate/reject free-form `--agent-version`.
- Add interruption, concurrent promotion, collision, symlink, secret, and
  corruption tests.
- Measure manifest/CAS size and resolution latency on both current variants.

## Testing Strategy

### Identity and canonicalization

- key ordering, path separators, timestamps, aliases, and promotion metadata do
  not accidentally change identity;
- every behavior-bearing field does change identity;
- same resolved version is stable across repeated resolution;
- short-ID collision and full-hash mismatch fail closed; and
- clean Git and captured-dirty representations remain intentionally distinct.

### Component and asset completeness

- YAML order/config/default changes affect the resolved graph;
- registry ambiguity or source-content changes fail verification;
- embedded prompts/tools/schemas point to the correct source hashes;
- all four v2 skills and their tool bindings are present;
- external asset changes affect identity;
- undeclared dynamic assets fail strict resolution; and
- normalized JSON Schema is stable and inspectable.

### Dirty and security policy

- modified, added, deleted, renamed, executable, and symlink paths are handled
  deterministically;
- dirty docs/eval results are excluded and reported without blocking;
- dirty execution files fail `reject` and are captured by `capture`;
- unclassified/secret-like/outside-root/oversized files fail;
- no credentials or secret values appear in manifests or CAS; and
- reconstruction cannot escape its destination.

### Dependencies and runtime

- `uv.lock`, project/eval-core/mi-core versions, Python version, registry
  version, and external distributions are recorded;
- an installed distribution inconsistent with the lock fails;
- changing relevant lock/runtime identity changes the version; and
- irrelevant host metadata does not.

### Model and override policy

- explicit defaults are frozen;
- each permitted override succeeds and changes run identity only;
- frozen, unknown, or out-of-range overrides fail before model calls;
- ambient defaults fail promotion; and
- secrets/endpoints are excluded while semantic API/backend options remain.

### Promotion and storage

- promoting from a run preserves the candidate ID;
- repeated promotion is idempotent and can append distinct promotion events;
- aliases cannot silently retarget without an explicit lifecycle operation;
- concurrent identical promotion converges; contradictory content fails;
- missing/corrupted CAS or Git objects fail verification; and
- clean versions do not duplicate tracked source bytes.

### Eval linkage

- every new schema-v3 result has a verified agent reference;
- benchmark name/key/version ID/number/source hash, exact sorted examples,
  model/runtime, graders, and schema versions round-trip;
- run identity changes for agent version, benchmark, scope, effective override,
  grader, or execution-policy changes;
- promotion after a run does not mutate historical result bytes;
- attempt records cannot contradict run-level agent identity; and
- legacy results remain readable only as `legacy_unversioned`.

### End-to-end

- resolve and eval clean v1.3 candidate, promote from run, verify, reconstruct,
  and rerun to the same agent ID;
- repeat for v2 including deferred skills and tools;
- evaluate one promoted version with two permitted models, producing one agent
  version and two run IDs linked to the same Azure benchmark; and
- capture a dirty prompt/skill change, prove a new agent ID, promote it with an
  explicit warning, and reconstruct its exact bytes.

Live Azure reads are useful for a smoke test but unit tests use injected
benchmark repositories and never require write access to Benchmark Studio.

## Acceptance Criteria

The feature is complete when:

- every new eval run resolves or loads one immutable agent-version manifest
  before the first model call;
- `agent_version_id` and full manifest hash are deterministic, verified, and
  present in run manifest and result schema v3;
- manifests freeze the complete resolved pipeline/component graph, code/assets,
  prompts, skills, tools, schemas, action/evidence/model policies, dependency
  lock, and relevant runtime/core versions;
- clean promotion uses a Git revision plus hashes and does not copy tracked
  source files;
- dirty promotion is explicit, captures exact bytes/tombstones, rejects
  unclassified or sensitive paths, and reconstructs deterministically;
- promotion from a useful run preserves the candidate ID and requires no
  manual file copying;
- stored versions can be inspected, verified, and reconstructed without using
  the current working tree;
- only permitted runtime overrides execute, with exact effective configuration
  in run identity and results;
- every result links the exact version to benchmark name/key/published
  version/source-state hash, selected examples, model/runtime, grader config,
  and result-schema version;
- Benchmark Studio and Azure remain the only benchmark/evidence truth and are
  read-only from this workflow;
- historical incomplete results are labeled, not fabricated; and
- golden, corruption, dirty, security, eval-linkage, and end-to-end tests pass.

## Risks And Mitigations

### Asset discovery can miss dynamic behavior

Mitigation: resolve through the real registry, use conservative version-surface
guards, require typed asset declarations for dynamic files, and fail strict
promotion on undeclared loading. Reconstruct and re-resolve before accepting a
dirty version.

### Git objects may later be pruned or repository access lost

Mitigation: local MVP verification reports Git-object availability and the
later portable/cloud publication feature must materialize or bundle required
source. Do not claim the local manifest alone is a durable off-repository
package.

### Dirty capture can retain secrets or very large files

Mitigation: reject secret-like paths/values, enforce allowed roots/media/size,
require complete dirty classification, and never provide a force bypass for
security checks.

### Defaults and installed packages can drift

Mitigation: normalize Pydantic defaults, freeze `uv.lock`, reconcile installed
external distributions, record Python/core versions, and reject ambient model
defaults.

### An override policy can make one version too broad

Mitigation: require explicit per-field allowlists/bounds, freeze all unlisted
fields, store exact effective settings in each run, and treat policy changes as
a new version.

### Candidate manifests can add storage overhead to every run

Mitigation: manifests are small, Git owns clean source, CAS deduplicates blobs,
and run-local/global promotion uses hard links where supported. Measure size and
resolution time before enabling broad artifact capture.

### Promotion could be confused with readiness approval

Mitigation: use explicit `candidate|promoted` development lifecycle language,
keep promotion notes outside identity, and reserve deployment/signing/readiness
gates for the portable agent package feature.

## Decisions To Revisit After MVP

- signing and attestation of manifests and promotion events;
- cloud publication and tenant-aware retention;
- alias supersession and deletion/reference policies;
- OCI, wheel, archive, or other portable package materialization;
- cross-platform/native dependency reproducibility;
- richer prompt/tool request-response artifact retention and redaction; and
- whether clean promoted versions should proactively mirror Git-owned blobs for
  resilience before portable packaging exists.
