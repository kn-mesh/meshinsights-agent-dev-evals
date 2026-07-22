# Spirax Pipeline Versions

The current runnable pipeline emits a structured `PulseFailureAnalysisResult` at
`act.metadata.agent_output`. It uses the shared
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

## Adding Another Variant

Keep the working parent pipeline. Add a new `.ppln`, change only the intended
design dimension, keep the structured receipt contract stable when practical,
and add a matching agent policy for AI variants. Record the parent, the short
hypothesis, and what changed in this file.

Run one exact benchmark example and a one-example eval before widening scope.
The pipeline name is the human working label; `agent_version_id` identifies
exact executable content and `run_id` identifies an evaluation.
