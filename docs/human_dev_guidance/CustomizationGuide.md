# Customization Guide

Use this guide when turning the template into a real consumer project.

## Change First

1. Update `pyproject.toml` with the real project name and dependencies.
2. Rewrite `README.md` so it describes the real application, its main workflows,
   and its documentation map instead of reading like the template README.
3. Fill out `docs/use_case/` with durable domain context.
4. Add or document your data and rubric sources under `data/`.
5. Implement the project's metadata, objects, retrievers, hydrators,
   processors, and actions under `src/`.
6. Replace the example `.ppln` files with project-specific pipeline variants.
7. Add evaluation and operator tooling only after the core pipeline shape is
   clear.

## Rewrite The Consumer README Early

The template `README.md` is scaffold/orientation material. Consumer repositories
should replace it early with an application README that explains:

- what the application does
- what it does not own
- the main entry points and workflows
- the currently supported pipeline variants
- the project-specific documentation map

Do not leave a consumer repo with a lightly edited copy of the template README.
That usually creates ownership confusion between the framework, template, and
application layers.

## How To Fill Out `UseCase.md`

The files in `docs/use_case/` should answer durable questions that future
developers and coding agents need to know before touching implementation:

- what the connected solution does
- what business outcome the pipeline is trying to produce
- what the final pipeline outputs mean
- what the input data looks like
- what rubric labels mean
- what domain knowledge matters for interpretation

Do not use the files in `docs/use_case/` as implementation logs.

## What To Build Under `src/`

### `src/objects/`

Create typed metadata, process, and action objects that make your stage
contracts explicit.

### `src/retrievers/`

Add source-specific integrations that fetch raw data. Keep them focused on data
 acquisition, not cross-source normalization.

### `src/hydrators/`

Use hydrators to:

- normalize raw retrieval output into process-stage state
- condense process-stage state into action-stage decisions
- stamp compact, durable metadata onto receipts

### `src/processors/`

Start with compute-only processors whenever practical. Add AI processors only
when deterministic logic is insufficient or too brittle.

### `src/actions/`

Use actions for side effects. If the durable output is a receipt summary rather
than an external side effect, a no-op action plus a final hydrator is a valid
pattern.

## How To Evolve Pipeline Variants

Start simple:

1. visualization-only path
2. baseline YAML pipeline
3. deterministic processor baseline
4. AI workflow if needed
5. agent variant only when targeted tool use materially helps
6. evaluation loop after outputs are stable enough to compare

Keep the consumer repo's docs clear about which variants are exploratory and
which are operator-facing.

## What Should Stay Generic

Keep in the template or framework layer:

- general repo structure guidance
- framework mechanics
- YAML conventions
- stage responsibilities

Keep in `docs/human_dev_guidance/`:

- human-oriented template guidance
- customization and lifecycle guidance
- repo navigation for developers

Keep in `.agents/skills/`:

- coding-agent implementation playbooks
- task-specific procedural guidance
- reusable agent workflows

Keep in the consumer repo:

- the application README
- prompts
- business rules
- source-system joins
- domain labels and interpretation rules
- variant-specific operational guidance
