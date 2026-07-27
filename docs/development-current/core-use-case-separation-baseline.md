# Core And Use-Case Separation Baseline

**Captured:** 2026-07-27

This is the Activity 1 cutover record for
`core-use-case-separation-refactor.md`. It records the last verified
old-layout state and the inventories that must be preserved through the
refactor.

## Verification Baseline

- Full Python suite: 428 passed, 6 skipped.
- Focused pipeline, profile, explorer, and agent-version suite: 39 passed.
- Frontend unit suite: 13 passed.
- Frontend production build: passed, including the evidence-bundle check.
- Repository skill suite: 26 passed.
- Known non-failing warning: one `LogfireNotConfiguredWarning` in the
  `mi-core` failed-processor telemetry test.

## Eval Cutover Inventory

All discovered local evals are fully materialized. No incomplete occurrence
needs resumption before the path cutover. Preserve these artifacts unchanged:

| ID | State | Attempts | Agent version | Model |
|---|---|---:|---|---|
| `eval_e17565025c5196a10500f166` | working | 70/70 | `av_3057bd7f5869e2007ee5fa53` | `google:gemini-3.6-flash` |
| `eval_3f95e9ee577f980e17c2e864` | working | 70/70 | `av_3057bd7f5869e2007ee5fa53` | `google:gemini-3.5-flash-lite` |
| `eval_4ffc7266285ea7564b220f9e` | working | 70/70 | `av_666fe01a1a7ed6819e0a2d16` | `google:gemini-3.6-flash` |
| `ret_0c04da94528c80d073856724` | retained | 210/210 | `av_666fe01a1a7ed6819e0a2d16` | `azure:gpt-5.6-luna` |
| `eval_3661928cf8c47b810cb124d0` | working | 210/210 | `av_74773b001c27cd570da0a358` | `azure:gpt-5.6-luna` |
| `eval_e8fac1662689cf231a9a190b` | working | 70/70 | `av_f5e15fca47b95b27248cb621` | `azure:gpt-5.6-sol` |
| `eval_7c5689433157e88f874e20c4` | working | 70/70 | `av_1274d657332f675e425966c7` | `azure:gpt-5.6-terra` |

Their recorded pipeline path is `pipeline_configs/v1_3.ppln`. Post-cutover
verification must prove they remain listable and inspectable without rewriting
that historical identity.

## Test Ownership Classification

The following suites were moved from `tests/use_case/` to reusable `tests/`
before the source-layout cutover:

- agent-version resolution, storage, provenance, and reconstruction;
- benchmark compatibility;
- explorer API, storage, lifecycle, pagination, and injected-adapter behavior;
- eval orchestration, result integrity, cost, resume, and lifecycle behavior;
- model-catalog behavior;
- operator documentation and CLI contracts; and
- fail-closed hosted identity validation.

These reusable suites may use a self-contained Spirax fixture, but they must not
import a project-owned default merely to test reusable mechanics.

The remaining `tests/use_case/` suites are reference-owned:

- Spirax frozen-evidence decoding;
- v1_3 pipeline construction, runner, and workflow behavior;
- Pulse process-object telemetry;
- the Spirax evaluation profile;
- reference-skill integration.

## Current Ownership Gaps

The schema-v1 manifest does not currently assign an effective owner to these
tracked surfaces:

- root infrastructure: `.env.example`, `.gitignore`, `pyproject.toml`,
  `uv.lock`, and `workbench.template.json`;
- template-authoring documents under `docs/development-*` and
  `docs/product-strategy/`;
- reusable script `scripts/verify_live_provider_costs.py`;
- reusable package marker `src/__init__.py`; and
- the `www/` composition/build harness outside `www/src/use_case/`.

Activity 2 must make the current layout exhaustive without switching reference
ownership to `use_case/`. Activity 3 will then atomically replace the scattered
reference entries with the single `use_case/` owner.

## Old-Path Consumer Inventory

The path cutover affects:

- reusable consumers in `src/agent_versions`, `src/evals`,
  `src/project_bootstrap`, and pipeline registry configuration;
- the schema-v1 ownership/reset manifest;
- reference pipeline, evaluation, agent policy, evidence, domain-object,
  processor, retriever, hydrator, action, and explorer paths;
- root `README.md`, `EvalRunbook.md`, frontend composition, and build
  configuration;
- reusable and reference tests; and
- repository skills for project creation, project orientation, pipeline
  building/porting, eval building, and explorer porting.

The detailed old-to-new mapping remains authoritative in Activity 3 of the
refactor plan.

## Skill Impact Inventory

At minimum, review these skills during the cutover:

- `project-guide`;
- `create-use-case-project`;
- `benchmark-pipeline-port`;
- `pipeline-builder`;
- `agent-eval-builder`; and
- `port-eval-explorer-use-case`.

Also search every other skill, linked reference, `agents/openai.yaml`, and
skill-routing fixture at each activity gate. Activity 1 changes only test
ownership and this implementation record, so no operational skill instruction
changes are required yet.
