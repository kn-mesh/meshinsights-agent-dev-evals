# Development Bugs

This backlog records correctness, security, and reproducibility defects found
while reviewing the features documented in `docs/development-current/`.

## Findings

### Evaluation result integrity does not cover result content

**Priority:** P1  
**Area:** reproducible eval execution and comparison  
**Status:** Resolved by the shared durable-store materializer

`src/evals/result_integrity.py` binds `result.json` to the adjacent run ID and
validates identities for rows that are present, but it does not require every
planned work item, verify semantic run dimensions, or recompute summary values
from immutable attempt records. Inspection and comparison can consequently
accept a result after a row, score, summary, or model dimension has been edited.

**Expected:** schema-v3 materialization has one canonical implementation based
on the immutable manifest and latest attempt generations. Consumers either
rematerialize that view or verify the complete materialized value against it.

### Agent-version capture can retain secret-bearing files

**Priority:** P1  
**Area:** immutable agent versions  
**Status:** Resolved by the shared sensitive-path policy

Agent-version path checks reject only a small exact-name set. Common names such
as `api_key.json`, `client-secret.pem`, `private-key.txt`, and `azureauth.json`
can enter a dirty overlay or explicitly declared asset and be retained in the
content-addressed store.

**Expected:** all local artifact workflows share a conservative sensitive-path
policy, and secret-like assets fail closed before their bytes enter a manifest
or content-addressed store.

### Unrelated dirty files alter agent-version identity

**Priority:** P1  
**Area:** immutable agent versions  
**Status:** Resolved by explicit dirty-path classification

Every non-excluded dirty path under broad `src/` and `mi-core` roots is added as
a `version_surface_guard` asset. Unreachable operator packages such as project
bootstrap can therefore change a pipeline's agent-version ID and be copied into
its dirty-overlay CAS.

**Expected:** the resolved component/asset graph is the included version
surface. Every other dirty path is classified as an explicit non-execution
exclusion or rejected as ambiguous; it is never silently included.

### Direct PostgreSQL loading fabricates publication identity

**Priority:** P2  
**Area:** published benchmark consumption  
**Status:** Resolved by the strict shared v2 adapter

The direct PostgreSQL adapter does not select the published-contract schema
version or published label-schema hash. Its normalizer defaults a missing
contract version to v2 and derives a missing hash locally, allowing an older or
incomplete response to look like the immutable v2 contract.

**Expected:** hosted and direct loaders feed one strict v2 normalizer. The
trusted database boundary explicitly derives the v2 contract metadata it owns;
hosted responses must supply it, and contradictory values fail closed.

### Alarm evidence can reveal post-decision state

**Priority:** P1  
**Area:** frozen benchmark evidence  
**Status:** Resolved by frozen-window alarm validation

Alarm normalization and selection must remain bounded by the benchmark decision
timestamp. A selected or historical alarm carrying a later detected or resolved
timestamp can expose outcome information that would not have been available at
decision time.

**Expected:** every alarm timestamp is validated against both the frozen
evidence window and the decision timestamp before normalization; post-decision
records fail closed and are never exposed to the pipeline.

### Agent-version aliases do not verify their recorded target hash

**Priority:** P2  
**Area:** immutable agent versions  
**Status:** Open

Alias loading follows `agent_version_id` but ignores the alias document's
recorded alias and `manifest_sha256`. Modifying an alias file can silently point
it at another valid stored manifest.

**Expected:** alias documents are strictly validated and their target ID and
full manifest hash must agree with the loaded immutable manifest.
