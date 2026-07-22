# Spirax Pipeline Versions

The current runnable variants make the same decision and emit the same
structured `PulseFailureAnalysisResult` at
`act.metadata.agent_output`. They use the shared
`evaluation_configs/spirax-failure-evaluation.eval.yaml` profile.

## `v1_3.ppln` — One-Shot AI Workflow

- Pipeline: `pipeline_configs/v1_3.ppln`
- Agent policy: `agent_version_configs/v1_3.agent.yaml`
- Shape: deterministic 7-, 30-, and 365-day temperature charts followed by one
  structured AI workflow call.
- Parent: evolved from the earlier `v1_2` experiment, which is no longer a
  runnable pipeline in this repository.
- Hypothesis: using the reviewed `UseCase-V2.md` domain guidance directly would
  preserve more SME context and avoid brittle prompt-specific rules.

Use `v1_3` as the reference when the prepared evidence can support one model
decision without runtime tool selection.

## `v2.ppln` — Progressive Tool-Using Agent

- Pipeline: `pipeline_configs/v2.ppln`
- Agent policy: `agent_version_configs/v2.agent.yaml`
- Parent: `v1_3`.
- Shape: deterministic 30- and 365-day overview charts, a structured case-brief
  workflow, and a bounded investigation agent that selects a focused date
  window through the steam-trap analysis skill.
- Hypothesis: a cheap orientation pass plus one focused, model-selected
  investigation can provide more relevant evidence than always supplying the
  same fixed chart windows.

Use `v2` as the reference only when adaptive evidence selection is useful. A
new use case does not need an agent if a deterministic processor or one-shot
workflow is sufficient.

## Adding Another Variant

Keep the working parent pipeline. Add a new `.ppln`, change only the intended
design dimension, keep the structured receipt contract stable when practical,
and add a matching agent policy for AI variants. Record the parent, the short
hypothesis, and what changed in this file.

Run one exact benchmark example and a one-example eval before widening scope.
The pipeline name is the human working label; `agent_version_id` identifies
exact executable content and `run_id` identifies an evaluation.
