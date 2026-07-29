# Campaign Ledger Contract

The ledger is schema-versioned, generated-local, and read by the campaign skill
and read-only explorer. Eval artifacts remain authoritative.

## `campaign.json`

Write once before paid work:

```json
{
  "schema_version": 1,
  "campaign_id": "imp_example",
  "created_at_utc": "2026-07-28T12:00:00Z",
  "starting_agent": {
    "git_commit": "abc123",
    "agent_version_id": "av_example",
    "selection_summary": "User selected the simpler alternate lineage."
  },
  "source": {
    "pipeline": "use_case/pipeline_configs/example.ppln",
    "agent_policy": "use_case/agent_version_configs/example.agent.yaml",
    "mutable_paths": ["use_case/processors/example"],
    "worktree_path": "/absolute/generated/worktree",
    "shared_workbench_path": "/absolute/project/.workbench"
  },
  "world": {
    "benchmark_key": "benchmark",
    "benchmark_version": 1,
    "evaluation_profile": "use_case/evaluation_configs/example.eval.yaml",
    "research_scope": {"section": "development"},
    "qualification_scope": {"all_examples": true},
    "runtime_configurations": [
      {
        "id": "primary",
        "role": "selection",
        "model": "provider:model",
        "reasoning_effort": "medium",
        "model_policy_overrides": {},
        "pricing_identity": "pricing-id",
        "maximum_primary_metric_regression": 0.0
      }
    ],
    "runs_per_example": 1,
    "selection_configuration_id": "primary"
  },
  "acceptance": {
    "primary_metric": "complete_evaluation_accuracy",
    "direction": "maximize",
    "minimum_improvement": 0.0,
    "minimum_scoring_coverage": 1.0,
    "maximum_critical_regressions": 0
  },
  "limits": {"max_attempts": 8}
}
```

## `state.json`

Rewrite atomically as the recovery pointer. Use configuration-keyed maps and
the exact field names in this canonical shape:

```json
{
  "schema_version": 1,
  "status": "research_complete",
  "termination_reason": "target_achieved",
  "baseline_evaluations": {
    "primary": {
      "configuration_id": "primary",
      "eval_id": "eval_baseline",
      "primary_metric": 0.8,
      "scoring_coverage": 1.0,
      "cost": 4.1
    }
  },
  "incumbent": {
    "git_commit": "def456",
    "agent_version_id": "av_candidate",
    "eval_ids": {"primary": "eval_candidate"},
    "primary_metric": 0.84
  },
  "current_trial": null,
  "qualification_evaluations": {},
  "qualification_decision": {
    "status": "pending",
    "proposed_scope": {"all_examples": true},
    "estimated_cost_usd": 4.2
  },
  "finished_attempts": 1,
  "consecutive_non_improving": 0,
  "stored_total_cost": 8.3,
  "new_spend_usd": 4.2
}
```

Use `active` while research can continue, `research_complete` while awaiting
the post-research qualification decision, and `complete` after qualification
is either finished or declined. Store an optional qualification evaluation
object under each configuration key after it runs.

The `qualification_decision` status must be `pending`,
  `authorized`, or `declined`. Add the decision timestamp and confirmed scope
when applicable.

Set qualification to `pending` only after research has produced a winner.
Qualification reserve and a proposed scope in `campaign.json` do not authorize
an occurrence. Record `authorized` before allocating an eval ID, or `declined`
when the user stops with the research winner.

Each baseline or qualification evaluation map value uses:

```json
{
  "configuration_id": "primary",
  "eval_id": "eval_example",
  "primary_metric": 0.8,
  "scoring_coverage": 1.0,
  "cost": 4.1
}
```

## `trials.jsonl`

Append one finalized JSON object per candidate. Do not rewrite prior lines:

```json
{
  "trial": 1,
  "parent_commit": "abc123",
  "candidate_commit": "def456",
  "agent_version_id": "av_candidate",
  "hypothesis": "Clarify the closed-failure rule.",
  "change_summary": "Added one decision rule and its focused test.",
  "changed_paths": ["use_case/processors/example/prompt.py"],
  "evaluations": [
    {
      "configuration_id": "primary",
      "eval_id": "eval_candidate",
      "primary_metric": 0.84,
      "scoring_coverage": 1.0,
      "critical_regressions": 0,
      "cost": 4.2
    }
  ],
  "decision": "keep",
  "decision_summary": "Accuracy improved without a guardrail regression."
}
```

Allowed decisions are `keep`, `discard`, `inconclusive`, and `crash`.
