# Spirax Pipeline Versions

The current runnable pipeline emits a structured `PulseFailureAnalysisResult` at
`act.metadata.agent_output`. It uses the shared
`use_case/evaluation_configs/spirax-failure-evaluation.eval.yaml` profile.

## `v0_2.ppln` — Campaign-Winning Text-First Lineage

- Pipeline: `use_case/pipeline_configs/v0_2.ppln`
- Agent policy: `use_case/agent_version_configs/v0_2.agent.yaml`
- Shape: one structured AI workflow call over non-overlapping historical period
  statistics, 30-day six-hour median telemetry, and 48-hour raw telemetry.
- Parent: the `v0_1` alternate lineage developed in campaign
  `imp_condensed_confident_v2_luna_low_20260729`.
- Hypothesis: preserve sustained one-sided deterioration and failure-onset
  evidence while narrowly exempting unfinished post-shutdown restarts.
- Selection evidence: 17/17 classification decisions on Condensed Confident v2
  with `azure:gpt-5.6-luna` at low reasoning.

## `v1_3.ppln` — One-Shot AI Workflow

- Pipeline: `use_case/pipeline_configs/v1_3.ppln`
- Agent policy: `use_case/agent_version_configs/v1_3.agent.yaml`
- Shape: deterministic 7-, 30-, and 365-day temperature charts followed by one
  structured AI workflow call.
- Parent: evolved from the earlier `v1_2` experiment, which is no longer a
  runnable pipeline in this repository.
- Hypothesis: using the reviewed `UseCase.md` domain guidance directly would
  preserve more SME context and avoid brittle prompt-specific rules.

Use `v1_3` as the reference when the prepared evidence can support one model
decision without runtime tool selection.

## Adding Another Variant

Keep the working parent pipeline. Add a new `.ppln`, change only the intended
design dimension, keep the structured receipt contract stable when practical,
and add a matching agent policy for AI variants. Record the parent, the short
hypothesis, and what changed in this file.

Run focused tests and one exact benchmark example through the pipeline runner
before considering an agent edit complete. Do not create a one-example eval as
a prerequisite to a wider eval; run the requested evaluation scope directly
after unit-level pipeline validation. The pipeline name is the human working
label; `agent_version_id` identifies exact executable content and `run_id`
identifies an evaluation.
