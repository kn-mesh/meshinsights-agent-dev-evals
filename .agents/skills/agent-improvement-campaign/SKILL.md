---
name: agent-improvement-campaign
description: Run a bounded autoresearch-style campaign that repeatedly changes and evaluates an agent. Use only for explicit autonomous, repeated, hill-climbing, or campaign improvement. Do not use for one eval, read-only analysis, or one measured candidate.
---

# Agent Improvement Campaign

Run a user-authorized sequence of measured candidates while preserving the
starting agent, frozen evaluation world, cost envelope, and exact eval
occurrences. Keep the orchestration generated-local and disposable.

## Keep Operator Intent Separate

- Route a plain request to run or resume one eval to `$run-use-case-evals`.
- Route read-only comparison to `$eval-results-analysis`.
- Route one proposed-and-measured improvement through `$project-guide`.
- Use this skill only for an explicit multi-attempt campaign or hill climb.
- Ask which path the user wants when "improve" could mean one candidate or a
  campaign. Never upgrade one path into another implicitly.

## Establish The Campaign

Before paid work:

1. Inspect a bounded set of plausible starting agents and compatible completed
   evals with `$eval-results-analysis`.
2. Recommend a starting point based on the stated goal, including a different
   lineage when useful. The user makes the final choice.
3. Ask the user to confirm the published benchmark/version and fixed research
   scope. Resolve an optional proposed qualification scope for planning, but do
   not treat it as authorization to run qualification.
4. Ask the user to choose one or more runtime configurations. Freeze model,
   reasoning, supported overrides, and pricing identity. Choose exactly one
   selection configuration; other configurations are comparison guardrails.
5. Require `max_attempts`. Resolve repetitions, acceptance rule, mutable paths,
   optional cost/time/plateau limits, and an optional qualification reserve.
   Qualification reserve is planning capacity, not authorization.
6. Report the maximum planned research occurrence count, the optional
   qualification occurrence count, and estimated baseline, research,
   qualification, and total cost. Start only when the research envelope is
   authorized. Always reconfirm qualification after research completes.

Require a clean, committed starting agent. Do not reconstruct dirty baselines
for MVP.

## Isolate Source And State

Create `codex/improve/<campaign-id>` in a linked worktree outside the primary
checkout. Point only that worktree's ignored `.workbench` path at the primary
repository's `.workbench` directory after validating both absolute paths.

Write:

```text
.workbench/improvements/<campaign-id>/
  campaign.json
  state.json
  trials.jsonl
```

Follow [the campaign ledger contract](references/campaign-ledger.md). Treat eval
artifacts as authoritative and the ledger as orchestration state.

Allow changes only to the user-confirmed use-case-owned agent surface. Freeze
benchmark truth, evidence objects, eval profile, graders, scopes, runtime
configurations, acceptance rule, limits, `workbench/`, and `packages/`. Stop
and request reusable-scope approval if a hypothesis needs shared behavior.

## Run The Hill Climb

1. Establish one exact research-scope baseline occurrence per runtime
   configuration. Reuse only an occurrence whose complete dimensions match.
2. Analyze incumbent failures with `$eval-results-analysis`. Identify the
   decision-relevant evidence for the use case, then directly inspect that
   evidence and published reviewer context for a bounded, representative set
   covering each material error cluster. When the agent consumes charts,
   images, audio, documents, or other rich artifacts, inspect the exact
   captured artifacts rather than relying only on row summaries or the
   model's explanation. For chart-led use cases, include the long- and
   short-window charts needed to interpret the alarm-adjacent pattern.
3. Quantify reviewer-note and verification coverage before forming the
   hypothesis. If notes are expected but missing from the frozen published
   contract, report the evidence-integrity limitation and investigate the
   publication boundary; do not silently treat `null` notes as proof that no
   rationale exists in the source labeling product.
4. State one focused, evidence-grounded hypothesis. Keep reviewer rationale as
   diagnostic benchmark context; never copy example-specific label rationale
   into agent behavior.
5. Change the allowlisted source and commit one candidate.
6. Run focused tests and one exact-example pipeline validation before paid
   evaluation. Repair within the hypothesis or log a local crash.
7. Allocate and run one research occurrence per configuration with
   `$run-use-case-evals`. Record each stateful dry-run ID before execution.
8. Resume interrupted occurrences by exact ID. Never replace them silently.
9. Compare the complete bundle with `$eval-results-analysis`. Directly review
   the relevant evidence for representative regressions, improvements, and
   unchanged errors, including every material outcome-change cluster.
10. Keep only when the selection configuration improves under the frozen rule
   and every comparison guardrail passes. Otherwise mark discard,
   inconclusive, or crash.
11. Append the finalized trial, update state, and continue from the kept
   incumbent or restore only the isolated worktree to the prior incumbent.
12. Check the attempt, cost, time, plateau, target, interruption, and ownership
    stops between trials.

Run configuration occurrences serially for MVP. Do not create independent
incumbents per model.

## Qualify And Stop

After the research attempts finish, report the winner, research metrics, cost,
and proposed qualification scope and estimate. Ask the user to choose whether
to:

- stop with the research winner and skip qualification;
- run at most one qualification occurrence per selected configuration on the
  proposed frozen scope; or
- confirm a different qualification scope and revised cost envelope.

Do not allocate or run qualification until the user explicitly confirms after
research, even when the initial campaign request included a qualification
reserve or scope. Qualification is optional and does not restart the hill
climb. When the user skips it, complete the campaign with a
`qualification_skipped` termination detail rather than treating the campaign
as incomplete.

Return the campaign ID, termination reason, starting and winning identities,
per-configuration baseline/research/qualification eval IDs and metrics, trial
outcomes, total stored cost, worktree, and uncertainties.

Do not automatically elevate, publish, integrate, clean up, package, or deploy.
Use `$eval-lifecycle` or `$publish-retained-eval` only after a new explicit
post-campaign request.

## Resume Safely

Load the frozen contract, state, and finalized ledger; verify the branch,
worktree, incumbent commit, and agent identity; then finish or resume every
recorded current eval occurrence before proposing another candidate. Never
infer replacement permission from an orphaned or failed run.

When research is complete and no qualification decision is recorded, report
the research winner and ask for the qualification choice. Never infer
qualification authorization from the original campaign envelope.

For implementation changes to this workflow, use the
[repository verification matrix](../project-guide/references/verification-matrix.md).
