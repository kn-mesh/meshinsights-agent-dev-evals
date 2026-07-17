# Template Architecture

This repository defines the standard starting shape for a Mesh Insights consumer
project. It sits between the framework and an application-specific repository:

- `mesh.insights.core` owns runtime mechanics and reusable APIs
- `mesh.insights.templates` owns starter-project conventions
- the consumer repository owns domain-specific implementation

## Standard Layout

```text
data/
docs/
pipeline_configs/
src/
  actions/
  hydrators/
  objects/
  processors/
  retrievers/
  pipelines/
  evals/
  streamlit_apps/
```

## Why These Folders Exist

| Path | Purpose |
|---|---|
| `docs/use_case/` | Durable business and domain context |
| `README.md` | Starter onboarding doc that consumer repos are expected to rewrite |
| `docs/human_dev_guidance/` | Human-oriented project guidance that should survive implementation changes |
| `data/` | Local example data, rubrics, and supporting artifacts |
| `pipeline_configs/` | Declarative `.ppln` files that wire project components together |
| `src/retrievers/` | Source-system integrations that fetch raw data |
| `src/objects/` | Typed process/action/metadata containers |
| `src/hydrators/` | Stage-boundary normalization and receipt stamping |
| `src/processors/` | Compute and AI analysis logic |
| `src/actions/` | Final side effects or intentionally no-op terminal actions |
| `src/pipelines/` | Project entry points and pipeline runners |
| `src/evals/` | Evaluation orchestration and result handling |
| `src/streamlit_apps/` | Human inspection and debugging apps |

## What Is Conventional vs What Is Project-Specific

Conventional:

- keeping durable business context in `docs/use_case/`
- using `pipeline_configs/` for YAML pipeline definitions
- organizing implementation code under `src/`
- modeling the project around retrievers, hydrators, processors, and actions

Project-specific:

- the concrete class names and their contracts
- the exact number of pipeline variants
- the data sources and retrieval strategy
- the evaluation workflow and rubric shape
- the Streamlit interfaces and operator workflow

## Example Files vs Required Behavior

The files in this repo are starter material. They show expected shape and
workflow, but they are not a runnable substitute for a consumer project.

In particular:

- the template `.ppln` files show recommended YAML shape
- `docs/use_case/` is durable business context, not an implementation log
- the template `README.md` is scaffold guidance, not the desired final README shape for consumer repos
- consumer repos should document their own application-specific contracts and
  operating model

Consumer repos should replace the template README with an application README
that describes the real use case, main workflows, owned variants, and local
documentation map.

## Relationship To Framework Docs

Use the template docs when you need to know:

- what a standard Mesh Insights project repo should contain
- what teams are expected to customize first
- how to move from a blank repo to a project-specific pipeline
- where human developer docs end and coding-agent skills begin

Use `mesh.insights.core` docs when you need to know:

- how `PipelineBuilder.from_yaml()` works
- how the registry finds components
- what `PipelineReceipt` contains
- what the framework expects from base component types
