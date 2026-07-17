# Project Lifecycle

The recommended development sequence for a Mesh Insights consumer project is:

1. durable use-case documentation
2. data inspection and visualization
3. baseline YAML pipeline
4. compute-only baseline
5. AI processor only if needed
6. eval loop and operator tooling

## 1. Durable Use-Case Documentation

Before implementation, capture the durable business context in `docs/use_case/`.
This should describe:

- the connected system
- the target output
- important domain terminology
- the data shape and expected quality
- rubric labels or analyst outcomes

## 2. Data Visualization

Build a visualization-first path to confirm:

- the data can be retrieved consistently
- the important signals are present
- the team understands what a healthy vs problematic example looks like

This step should reduce guesswork before business logic or prompts are locked in.

## 3. Baseline YAML Pipeline

Once the project shape is clear, add a YAML-driven control path that wires:

- retriever(s)
- retrieve hydrator
- processor(s)
- process hydrator
- action(s)
- final hydrator

The goal is a repeatable, runnable pipeline shape, even if the internal logic is
still basic.

## 4. Compute-Only Baseline

If deterministic logic can solve the task well enough, prefer that first. It is
usually easier to debug, cheaper to run, and easier to explain than an AI-first
solution.

## 5. AI Only When Needed

Add an AI workflow or agent when:

- the task requires interpretation that compute logic cannot express cleanly
- deterministic rules become too brittle
- a structured model output adds value that offsets the added complexity

Prefer workflow over agent unless tool use materially improves the task.

## 6. Eval Loop And Operator Tooling

After outputs stabilize:

- add rubric-based evaluation
- add result inspection tooling
- compare variants with evidence rather than intuition

This is also the point to make operator-facing docs explicit in the consumer
repo.
