# Agent Improvement Campaign

**Status:** Implemented MVP architecture

**Owning scope:** Root orchestration, generated-local campaign state, reusable
read-only explorer projection, and reusable eval UI

**Primary user:** Mesh FDE using Codex

**Related strategy:** Agent Improvement and continuous agent iteration

## Resolved Product Decisions

1. A concrete request that names the selected runtime configuration or
   configurations, benchmark scopes, repetitions, and maximum attempts
   authorizes model calls inside that envelope. If the envelope is incomplete,
   Codex resolves the available choices and asks once before paid work.
2. Every campaign requires `max_attempts`. Cost, elapsed-time, plateau, and
   target controls remain optional additional stops.
3. The user always chooses the published benchmark plus the research and
   qualification scopes. Codex recommends an obvious benchmark and relevant
   named slice when one exists, but it asks the user and does not start until
   the user confirms.
4. Codex and the user choose the starting agent version together, with the user
   having final say. The starting point may be the best-known agent or a
   deliberately different lineage intended to explore another strategy.
5. The user chooses one or more LLM runtime configurations before the campaign
   starts. The set is frozen for the campaign so the maximum number of eval
   occurrences and estimated cost are visible up front.
6. The evaluation review app gains read-only navigation between traditional
   eval runs and autoresearch campaigns. Campaigns show performance over time
   by runtime configuration and summaries of the changes between trials.
7. A traditional eval run and an autoresearch campaign are separate operator
   intents and separate skill routes. Codex must not turn one into the other
   without an explicit new user request.

## Decision

Build an **autoresearch-style, Codex-operated improvement campaign** on top of
the Workbench capabilities that already exist.

A campaign repeatedly:

1. starts from the exact agent version chosen by the user;
2. analyzes the current best candidate;
3. makes one focused change;
4. rejects broken changes with local validation;
5. evaluates the candidate on a fixed research scope using every selected
   runtime configuration;
6. keeps or discards it using a predeclared selection configuration and rule;
   and
7. continues from the best candidate until a termination condition is reached.

The best campaign candidate receives one qualification occurrence per selected
runtime configuration. Codex then stops and returns the evidence to the FDE. It
does not automatically elevate, publish, merge, package, or deploy anything.

This is intentionally a small orchestration layer. The MVP does **not** add an
Experiment database, optimization service, scheduler, or campaign mutation UI.
It adds only the read-only API projection and review page needed to visualize
the generated-local campaign ledger.

## Why This Is The Smallest Useful Product

The strategic job is not merely to run one candidate safely. It is to make the
cycle described in `docs/product-strategy/jobs-to-be-done.md` practical:

> Build, evaluate, improve, repeat.

The current repository already provides the important safety and provenance
primitives:

- content-addressed `agent_version_id` values;
- run-local immutable candidate manifests;
- working eval occurrences with exact benchmark, evidence, model, grading, and
  pricing identities;
- resume of an exact interrupted occurrence;
- bounded inspection of completed results; and
- explicit elevation that retains a completed eval with its exact agent
  candidate.

The missing capability is a protocol that coordinates those primitives across
multiple experimental attempts while remembering the incumbent, budget, and
results.

Karpathy's `autoresearch` is the operating-model reference:

- fixed experimental world;
- tightly bounded mutable source;
- repeated candidate measurements;
- keep, discard, or crash;
- continue from the best source state; and
- maintain a compact experiment log.

Agent Workbench needs a few additional safeguards because agent quality is
multidimensional, model calls have variable cost, and repeated benchmark
optimization can overfit.

## Goals

- Let one explicit campaign run multiple candidate attempts autonomously.
- Preserve the selected starting agent and its exact configuration baselines.
- Keep experimental candidates disposable until one proves meaningful.
- Hold benchmark, evidence, grader, runtime configurations, research scope, and
  acceptance rules fixed within a campaign.
- Advance only from candidates that improve the declared objective without
  violating guardrails.
- Resume an interrupted eval occurrence instead of silently allocating another.
- Bound paid work using an explicit campaign envelope.
- Produce an inspectable history of hypotheses, candidates, eval IDs, costs,
  and decisions.
- Require the user to choose the starting agent version, benchmark scopes, and
  one or more allowed LLM runtime configurations before the loop begins.
- Show campaign progress, configuration performance, and change summaries in
  the existing evaluation review app.
- Qualify the best candidate before presenting it for retention.
- Require explicit FDE direction for elevation and source integration.

## Non-Goals

- Automatic production deployment or package publication.
- Automatic eval elevation or agent-version promotion.
- Benchmark creation, label mutation, or Benchmark Studio writes.
- A hidden-label evaluation service.
- A generic hyperparameter-search framework.
- Parallel candidate search, agent swarms, Bayesian optimization, genetic
  search, or tournament selection.
- A durable multi-user campaign catalog.
- A generic comparison-artifact system.
- Starting, stopping, editing, elevating, or deleting campaigns from the UI.
- Automatic cleanup of working evals, retained evals, branches, or worktrees.
- Modifying reusable runtime, evaluation, or package behavior as an experiment
  inside a normal use-case campaign.

## Core Terms

| Term | Meaning |
|---|---|
| **Campaign** | One bounded sequence of autonomous candidate attempts against one frozen evaluation world. |
| **Starting agent** | The exact clean Git commit and `agent_version_id` selected jointly by Codex and the user, with the user making the final choice. It may be the best-known agent or a different strategic lineage. |
| **Baseline set** | The research-scope eval occurrence for each selected runtime configuration against the starting agent. It establishes trial-zero performance and never changes. |
| **Runtime configuration** | A frozen model, reasoning, and supported model-policy configuration selected before the campaign. |
| **Selection configuration** | The one selected runtime configuration whose metric drives keep/discard decisions. Other selected configurations provide fixed comparative evidence and guardrails. |
| **Incumbent** | The current best source commit and its research eval bundle within the campaign. It begins as the starting agent plus baseline set. |
| **Trial** | One committed candidate mutation plus its fixed bundle of research eval occurrences, one per selected runtime configuration. |
| **Kept trial** | An eligible trial that beats the incumbent under the frozen acceptance rule. It becomes the next incumbent. |
| **Discarded trial** | A completed trial that does not beat the incumbent. |
| **Crashed trial** | A candidate that cannot complete validation or its allocated eval occurrence. |
| **Campaign winner** | The final incumbent after campaign termination. It may still fail qualification. |
| **Qualified candidate** | A campaign winner that completes the fixed qualification bundle and satisfies the qualification guardrails. |
| **Retained version** | A qualified candidate whose user-selected exact qualification evals are explicitly elevated by the FDE. |

`keep` is a campaign-local research decision. It does not mean elevate,
promote, publish, merge, or deploy.

## Explicit Operator Routes

The normal eval workflow and the campaign workflow are different products.
Shared low-level eval mechanics do not make their user intent interchangeable.

| User intent | Route | Authorized outcome |
|---|---|---|
| “Run/evaluate this agent on this benchmark or slice.” | `$run-use-case-evals` | One new eval occurrence for the selected agent and configuration, or resume of one exact occurrence. |
| “Propose and test one improvement.” | Existing `$project-guide` single-candidate path | One isolated candidate, one requested measurement, comparison, and handoff. |
| “Start/run an autoresearch campaign,” “hill-climb this agent,” or “autonomously improve this agent across attempts.” | `$agent-improvement-campaign` | A bounded sequence of candidate mutations and eval bundles inside the confirmed campaign contract. |
| “Analyze/compare these completed evals.” | `$eval-results-analysis` | Read-only analysis; no eval and no campaign. |

Routing rules:

- A single-eval request must not create campaign state, a campaign branch, a
  worktree, candidate mutations, or follow-up eval occurrences.
- A campaign request must not be reduced to one ordinary eval followed by a
  handoff. It continues autonomously within the confirmed campaign envelope.
- `$run-use-case-evals` remains the low-level measurement step used by a
  campaign, but the campaign skill owns the multi-occurrence authorization,
  attempt budget, source mutations, and keep/discard loop.
- A user asking to “test,” “evaluate,” or “run an eval” has not authorized
  source changes or a campaign.
- A user asking to “improve” one candidate without words indicating repeated or
  autonomous search follows the existing single-candidate improvement path.
- If wording could reasonably mean either a single candidate or a campaign,
  Codex asks which path the user wants before changing source or allocating paid
  occurrences.
- Switching paths requires a new explicit user request. Codex does not infer
  permission from promising results, failures, remaining budget, or prior
  campaigns.

Repository skill routing tests must cover positive and negative examples for
both paths so future prompt changes cannot silently collapse them together.

## User Experience

### Starting A Campaign

Campaign initialization is a short joint decision between Codex and the user.
Codex investigates and recommends; the user has final say on every choice below.

#### 1. Choose The Starting Agent

Codex presents a bounded set of plausible starting points with:

- pipeline label and exact `agent_version_id`;
- clean Git commit and source path;
- available compatible eval IDs;
- benchmark, scope, runtime configuration, accuracy, reliability, coverage, and
  cost from those evals;
- known strengths and repeated failure clusters; and
- lineage or strategy, when known.

Codex recommends a starting point based on the campaign goal. Common choices
include:

- the highest-performing known agent, to continue exploiting the current
  strategy;
- an earlier or simpler agent, to test whether a cleaner lineage can surpass
  the leader;
- an agent optimized for a particular failure slice or cost profile; or
- a newly committed base strategy with no prior compatible eval.

Codex must not choose “highest accuracy” automatically. The user selects the
exact starting agent. If a new base has no compatible baseline eval, the
campaign envelope includes its baseline measurements before candidate attempts.

#### 2. Choose Benchmark Scopes

Codex always asks the user to confirm:

- published benchmark key and immutable version;
- fixed research scope; and
- fixed qualification scope.

When one benchmark or named section is clearly relevant—for example, a slice
containing only the targeted failure type—Codex recommends it and explains the
tradeoff. It still waits for the user's selection.

#### 3. Choose Runtime Configurations

The user selects one or more configurations. Each has:

- stable configuration ID;
- LLM model;
- reasoning effort;
- supported model-policy overrides;
- resolved pricing identity; and
- role: `selection` or `comparison`.

Exactly one configuration is the **selection configuration**. Its primary
metric drives keep/discard decisions. Any additional configurations are
comparison configurations: every trial measures them on the same research
scope, and regressions may make a trial ineligible, but they do not create
multiple competing incumbents.

This is deliberately simpler than maintaining a separate hill climb per model.
Adding, removing, or changing a runtime configuration requires a new campaign.

#### 4. Confirm The Envelope

The remaining fixed inputs are:

- mutable source paths;
- repetitions;
- acceptance rule;
- required `max_attempts`; and
- optional cost, elapsed-time, plateau, or target limits.

Before the first paid call, Codex reports:

- selected starting agent, source commit, and available baseline evals;
- benchmark and immutable version;
- research and qualification scopes;
- every runtime configuration and its frozen pricing basis;
- examples multiplied by repetitions per configuration;
- baseline occurrences still required;
- maximum research occurrences:
  `max_attempts × number_of_runtime_configurations`;
- reserved qualification occurrences:
  `number_of_runtime_configurations`;
- estimated baseline, research, qualification, and maximum total cost;
- optional elapsed-time limits; and
- the possible cost overshoot described under **Budget Semantics**.

If the user's request already authorizes that exact envelope, Codex starts.
Otherwise it asks once.

### During A Campaign

Codex operates autonomously inside the authorized envelope. It does not ask
after every trial.

It provides concise progress updates at useful boundaries:

- starting agent and configuration baselines established;
- a trial is being evaluated;
- a trial was kept, discarded, or crashed;
- the campaign stopped; and
- qualification completed or failed.

It does not stream full model or test output unless troubleshooting requires it.

### Campaign Handoff

The final handoff reports:

- campaign ID and termination reason;
- starting commit and agent version;
- baseline, winner, and qualification eval IDs and scores by runtime
  configuration;
- attempts used and outcome counts;
- total stored eval cost and pricing coverage;
- important regressions or uncertainties;
- campaign branch and worktree path; and
- exact next choices: inspect, elevate, integrate, continue with a new envelope,
  abandon, or explicitly clean up.

## Architecture

```text
FDE
 |
 v
Codex agent-improvement-campaign skill
 |-- Git branch + isolated linked worktree
 |-- generated-local campaign ledger
 |-- focused tests and exact-example pipeline runner
 |-- existing eval runner
 |-- existing eval inspection and analysis
 `-- optional explicit lifecycle elevation after handoff
             |
             v
Read-only evaluation review app
 |-- Evaluation runs
 `-- Autoresearch campaigns

Published benchmark + frozen evidence
        |
        v
Existing working eval occurrences
        |
        v
Existing retained eval + retained agent version
```

### New MVP Components

1. A generic repository skill:

   ```text
   .agents/skills/agent-improvement-campaign/
     SKILL.md
     agents/openai.yaml
   ```

2. Generated-local campaign state:

   ```text
   .workbench/improvements/<campaign-id>/
     campaign.json
     state.json
     trials.jsonl
   ```

3. A linked source worktree in a generated sibling directory. Its ignored
   `.workbench` path points to the primary repository's existing `.workbench`
   root so baseline and candidate evals remain visible to the same commands.

4. A read-only campaign projection isolated from existing eval mechanics in
   `workbench/apps/improvement_campaigns.py`, with thin delegation from the
   existing explorer backend:

   ```text
   GET /api/campaigns
   GET /api/campaigns/{campaign-id}
   ```

5. A persistent app sidebar with:

   ```text
   Evaluation runs
   Autoresearch campaigns
   ```

6. A campaign overview/detail page with a progress chart and stored change
   summaries.

7. Architecture, backend, API, and UI tests for the new contracts.

No campaign database, mutation API, or separate web app is required.

### Existing Components Reused

- `workbench.agent_versions` resolves immutable candidate identity.
- `workbench.evals.eval_orchestration` allocates, runs, and resumes working eval
  occurrences.
- `workbench.evals.inspection_cli` provides bounded result inspection.
- `$eval-results-analysis` classifies failures and compares exact results.
- `workbench.eval_lifecycle` explicitly elevates a selected complete eval with
  its exact candidate.
- `packages/eval-ui/web/src/timeseries-chart.tsx` proves the app already ships
  the Plotly dependency needed for a lightweight campaign progress chart.
- Use-case pipeline runners and tests reject broken source before paid evals.

## Ownership Boundaries

The first implementation changes:

- **root infrastructure:** the new campaign skill, `project-guide` routing and
  guidance, app composition tests, skill tests, and this specification;
- **generated local:** `.workbench/improvements/` campaign state;
- **reusable Workbench:** a read-only projection of generated-local campaigns
  in `workbench/apps/eval_explorer.py`;
- **reusable eval UI:** two read-only API methods/routes, shared TypeScript
  contracts, sidebar navigation, and the campaign page under
  `packages/eval-ui/`;
- **project explorer UI:** integration tests and styling/build verification
  under `apps/eval_explorer/web/`; and
- **reference use case:** only when an actual campaign changes an allowlisted
  use-case agent surface.

The app request makes the reusable explorer paths explicitly in scope. Focused
tests are required for the backend projection, FastAPI routes, reusable UI
contracts, sidebar routing, campaign empty/error states, chart series, and
change summaries.

It still does not require changes to:

- `packages/mi-core/`;
- `packages/eval-core/`;
- eval execution or lifecycle schemas; or
- use-case evidence adapters.

If implementation evidence later shows that skill-driven state is unreliable,
a thin use-case-neutral controller may be proposed separately. That would be a
reusable Workbench scope expansion and requires explicit approval.

## Source Isolation

### Starting Agent Requirement

For MVP, the selected starting agent must resolve to:

- a candidate with `source_tree_state: clean`;
- a Git commit available locally; and
- source whose resolved `agent_version_id` matches the user's selection.

Supporting a dirty-overlay starting agent would require reconstructing an evaluated
patch into a new commit and proving it has identical identity. Defer that until
a real campaign needs it.

Compatible completed evals are useful selection evidence but are not required.
After the user chooses the starting agent and runtime configurations, the
campaign must have one research-scope baseline occurrence per configuration.
It may reuse an existing occurrence only when benchmark, version, scope, model,
reasoning, repetitions, grader, evidence, and agent identity exactly match.
Otherwise it allocates the missing baseline occurrences inside the confirmed
campaign envelope before trial one.

Unrelated changes in the FDE's main checkout do not block a campaign as long as
the selected starting commit is available and the campaign worktree can be
created without touching those changes.

### Campaign Branch And Worktree

Create:

```text
branch:   codex/improve/<campaign-id>
worktree: <repo-parent>/.workbench-worktrees/<repo-name>/<campaign-id>/
```

The linked worktree begins at the exact starting-agent commit. All candidate edits,
commits, validation, eval runs, and inspection happen from that worktree. The
FDE's main checkout and starting commit remain unchanged.

The current eval and lifecycle commands resolve artifacts through a
repository-relative `.workbench` path. To avoid splitting the baseline and
candidate across two artifact stores, create this ignored link inside the
campaign worktree:

```text
<campaign-worktree>/.workbench -> <primary-repo>/.workbench
```

Validate both absolute paths before creating the link. Refuse an existing
non-link target or a link that resolves anywhere except the selected primary
repository's `.workbench` directory. This small setup step avoids a new output
root option or campaign controller.

The worktree is kept after campaign completion. It is not automatically
removed because it may contain working evals needed for review or elevation.

### Mutable Surface

Every campaign records an explicit allowlist. The normal surface is the
selected agent's use-case-owned behavior, such as:

- selected `.ppln` and matching `.agent.yaml`;
- prompts and behavior-bearing assets;
- use-case processors, tools, actions, hydrators, retrievers, or schemas named
  by the hypothesis; and
- focused use-case tests and agent documentation.

Frozen by default:

- published benchmark membership, labels, and frozen evidence objects;
- evaluation profiles and graders;
- campaign research and qualification scopes;
- selected runtime configurations, selection configuration, repetitions, and
  pricing identities;
- `workbench/`;
- `packages/`;
- publication and production-runtime code; and
- the campaign skill and its ledger schema.

Changing a frozen dimension ends the current campaign. The FDE may start a new
campaign that declares that dimension as the experimental variable.

## Campaign State

### `campaign.json`

Written once before the first trial. It is the frozen campaign contract.

Minimum logical fields:

```json
{
  "schema_version": 1,
  "campaign_id": "imp_<opaque-id>",
  "created_at_utc": "<timestamp>",
  "starting_agent": {
    "git_commit": "<sha>",
    "agent_version_id": "av_<id>",
    "selection_summary": "<why the user selected this starting point>"
  },
  "source": {
    "pipeline": "use_case/pipeline_configs/<name>.ppln",
    "agent_policy": "use_case/agent_version_configs/<name>.agent.yaml",
    "mutable_paths": ["<explicit path>"],
    "worktree_path": "<absolute generated sibling path>",
    "shared_workbench_path": "<absolute primary .workbench path>"
  },
  "world": {
    "benchmark_key": "<key>",
    "benchmark_version": 1,
    "evaluation_profile": "<path>",
    "research_scope": {"section": "<name>"},
    "qualification_scope": {"all_examples": true},
    "runtime_configurations": [
      {
        "id": "primary",
        "role": "selection",
        "model": "<provider:model>",
        "reasoning_effort": "<value>",
        "model_policy_overrides": {},
        "pricing_identity": "<resolved identity>",
        "maximum_primary_metric_regression": 0.0
      },
      {
        "id": "comparison",
        "role": "comparison",
        "model": "<provider:model>",
        "reasoning_effort": "<value>",
        "model_policy_overrides": {},
        "pricing_identity": "<resolved identity>",
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
    "require_complete_occurrence": true,
    "minimum_scoring_coverage": 1.0,
    "maximum_critical_regressions": 0
  },
  "limits": {
    "max_attempts": 8,
    "max_total_cost": null,
    "max_elapsed_minutes": null,
    "max_consecutive_non_improving": null,
    "target_primary_metric": null
  }
}
```

The values above illustrate shape, not product defaults. MVP does not expose a
generic predicate language. The skill records a small fixed acceptance schema
and a human-readable statement for any use-case-specific critical slice.

### `state.json`

Mutable recovery state:

```json
{
  "schema_version": 1,
  "status": "establishing_baselines",
  "baseline_evaluations": [
    {
      "configuration_id": "primary",
      "eval_id": "eval_<id>",
      "primary_metric": 0.8,
      "scoring_coverage": 1.0,
      "cost": 4.1
    }
  ],
  "incumbent_commit": "<sha>",
  "incumbent_agent_version_id": "av_<id>",
  "incumbent_evaluations": {
    "primary": "eval_<id>",
    "comparison": "eval_<id>"
  },
  "qualification_evaluations": [
    {
      "configuration_id": "primary",
      "eval_id": "eval_<id-or-null>",
      "primary_metric": 0.84,
      "scoring_coverage": 1.0,
      "cost": 4.21
    }
  ],
  "current_trial_number": 3,
  "current_trial_commit": "<sha-or-null>",
  "current_eval_ids": {
    "primary": "eval_<id-or-null>",
    "comparison": "eval_<id-or-null>"
  },
  "attempts_finished": 2,
  "consecutive_non_improving": 1,
  "stored_total_cost": 12.34,
  "termination_reason": null
}
```

Write each entry in `current_eval_ids` immediately after the stateful eval
dry-run allocates that occurrence and before execution starts. This makes
interruption resume the same occurrence for the same runtime configuration.

### `trials.jsonl`

Append one finalized record per measured or crashed trial:

```json
{
  "trial": 3,
  "parent_commit": "<sha>",
  "candidate_commit": "<sha>",
  "agent_version_id": "av_<id>",
  "hypothesis": "<short statement>",
  "change_summary": "<what changed from the parent>",
  "changed_paths": ["<path>"],
  "evaluations": [
    {
      "configuration_id": "primary",
      "eval_id": "eval_<id>",
      "primary_metric": 0.84,
      "scoring_coverage": 1.0,
      "critical_regressions": 0,
      "cost": 4.21
    },
    {
      "configuration_id": "comparison",
      "eval_id": "eval_<id>",
      "primary_metric": 0.82,
      "scoring_coverage": 1.0,
      "critical_regressions": 0,
      "cost": 2.73
    }
  ],
  "decision": "keep",
  "decision_summary": "<why this trial was kept or discarded>"
}
```

Allowed decisions are `keep`, `discard`, `inconclusive`, and `crash`.
`inconclusive` does not advance the incumbent.

The existing eval artifacts remain authoritative. The ledger is orchestration
memory, not another result store.

## Evaluation Strategy

### Level 1: Local Validation

Before a paid research eval:

1. run focused tests for changed paths;
2. resolve the pipeline and candidate identity;
3. run one exact, explicitly versioned published example through the pipeline
   runner; and
4. confirm the structured output contract.

This is not an eval occurrence and does not consume a measured trial. A
candidate that cannot pass local validation may be repaired within the same
hypothesis before measurement. If Codex abandons it, log a local `crash`
without allocating a paid eval.

### Level 2: Research Evaluation

Every measured trial uses the exact research scope frozen in `campaign.json`.
Prefer:

- a named use-case section containing the targeted failure cluster plus
  regression sentinels; or
- an explicit fixed list of example IDs.

Do not change the research scope to favor a later hypothesis. Every candidate
gets one new occurrence per selected runtime configuration. Together those
occurrences are one trial bundle. Run them serially for MVP so state, cost, and
interruption handling remain simple. If an occurrence is interrupted, resume it
by exact `run_id`; do not allocate a replacement.

Do not decide keep/discard until the complete trial bundle is available. If a
comparison configuration fails, the frozen eligibility rule determines whether
the trial is ineligible or can be marked inconclusive; Codex does not silently
drop that configuration.

### Level 3: Qualification Evaluation

When campaign termination leaves an incumbent better than the starting-agent
baseline set, run one new qualification occurrence per selected runtime
configuration using the user-confirmed qualification scope.

Qualification:

- does not participate in further hill climbing;
- uses the benchmark and scope explicitly chosen by the user at campaign start;
- must preserve each runtime configuration, repetitions, grader, and benchmark
  identity;
- determines whether the winner is suitable to present for elevation; and
- may reject a research-slice winner because of broader regressions.

If the winner fails qualification, the campaign ends as
`qualification_failed`. Codex does not silently resume search under the same
envelope.

## Acceptance Rule

Agent quality is not one scalar. Apply the decision in two stages.

### Eligibility

A trial is eligible only when:

- every required configuration occurrence completed;
- scoring coverage meets the frozen minimum for every configuration;
- the structured output contract is no worse than the incumbent on any
  configuration;
- critical regressions do not exceed the frozen maximum on any configuration;
- benchmark, evidence, grader, runtime configuration, scope, and repetitions
  match the campaign world; and
- results have usable pricing coverage when cost is part of the decision.

### Keep Or Discard

Keep an eligible trial when:

- the selection configuration's primary metric improves by at least
  `minimum_improvement`; or
- that metric ties within the declared tolerance and the candidate is
  materially cheaper or materially simpler.

Comparison configurations are guardrails and evidence, not separate
incumbents. Their configured regression tolerance must be satisfied for a keep.

Use tie-breakers in this order:

1. fewer critical errors;
2. better complete-evaluation accuracy;
3. better reliability and scoring coverage;
4. lower stored model cost; and
5. simpler source change.

Changes inside an undeclared or obvious measurement-noise range are
`inconclusive`, not improvements.

For MVP, Codex performs this comparison from exact eval results using
`$eval-results-analysis`. A machine-enforced scoring engine is deferred.

## Trial State Machine

```text
incumbent
   |
   v
create one hypothesis and candidate commit
   |
   v
local validation --------failed--------> crash -> restore incumbent
   |
 passed
   v
allocate exact research eval bundle
   |
   +----interrupted----> resume same configuration occurrence
   |
 completed
   v
compare complete bundle against incumbent bundle
   |
   +----eligible improvement----> keep -> candidate becomes incumbent
   |
   `----otherwise---------------> discard/inconclusive -> restore incumbent
```

After a discard, inconclusive result, or crash, reset only the isolated
campaign worktree to the recorded incumbent commit. Before resetting, verify:

- the current path is the recorded campaign worktree;
- the campaign branch is checked out;
- the candidate commit and result are recorded in the ledger; and
- no paths outside the campaign mutable surface have uncommitted changes.

Never reset or clean the FDE's main checkout.

## Termination

Check termination conditions between trials. Do not terminate a healthy
in-flight eval merely because a wall-clock boundary passed.

Stop when the first applicable condition occurs:

- `max_attempts` reached;
- stored total cost reached or exceeded `max_total_cost`;
- elapsed time reached or exceeded `max_elapsed_minutes`;
- consecutive non-improving attempts reached the plateau limit;
- target primary metric reached;
- no valid new hypothesis remains;
- frozen-world integrity cannot be verified;
- credentials or external services prevent reliable evaluation;
- FDE interrupts the campaign; or
- Codex encounters a safety or ownership boundary requiring new authority.

An external failure does not authorize a replacement occurrence. Resume the
same occurrence when possible. If a source change or new occurrence is needed,
finalize the current trial as `crash` before continuing within the remaining
attempt budget.

## Budget Semantics

`max_attempts` is the simple hard control. One attempt means one candidate that
reaches local rejection or one allocated research eval bundle. A full research
bundle contains one occurrence per selected runtime configuration.

Before authorization, calculate the maximum planned occurrence count:

```text
missing starting-agent baselines
+ (max_attempts × runtime configuration count)
+ (qualification configuration count when a winner exists)
```

Stored model cost is known only after calls complete. Therefore:

- check the cumulative stored cost before starting each new trial;
- estimate the next full trial bundle from the baseline set or latest
  comparable occurrences;
- do not start when the estimate would exceed the remaining budget;
- disclose that actual variable usage can overshoot `max_total_cost` by at most
  the difference between one trial bundle's estimate and actual cost; and
- never start qualification if its estimate exceeds the remaining authorized
  budget unless qualification was separately reserved in the envelope.

If a strict no-overshoot financial cap is required, use a conservative
`max_attempts` and scope size. Building real-time token cancellation is outside
MVP.

Local validation model calls must be disclosed in the envelope. They do not
create eval occurrences, but their cost still counts when usage is available.

## Resume And Recovery

On campaign restart:

1. load and validate `campaign.json`;
2. load `state.json` and the finalized ledger;
3. verify the campaign branch and worktree;
4. verify the incumbent commit and source identity;
5. inspect every populated `current_eval_ids` entry;
6. resume missing work for the same configuration occurrences when eligible;
7. finalize the complete trial bundle before proposing another candidate; and
8. recheck remaining limits.

Do not infer campaign state from Git history alone. Do not treat an orphaned
working eval as permission to start over.

## Qualification, Elevation, And Integration

These are separate operations:

1. **Keep:** advance the campaign incumbent.
2. **Qualify:** measure the final incumbent on the fixed qualification scope
   for every selected runtime configuration.
3. **Elevate:** explicitly retain one or more user-selected complete
   qualification evals and their exact candidate through
   `workbench.eval_lifecycle`.
4. **Integrate:** explicitly bring the tested source commit into the FDE's
   development branch.
5. **Publish:** explicitly publish an already retained eval.
6. **Deploy/package:** outside this MVP.

The safest order after a successful campaign is:

```text
inspect qualification result
-> elevate user-selected exact qualification occurrences if meaningful
-> integrate exact tested commit
-> verify the integrated tree resolves to the same agent identity
```

File renaming or source cleanup after qualification can produce a different
agent identity. Any behavior-bearing change after qualification requires a new
measurement.

## Overfitting Boundary

Repeatedly selecting changes using one labeled scope turns that scope into
development data.

MVP mitigations:

- freeze the research scope for the whole campaign;
- include regression sentinels in that scope;
- use a separate, broader qualification scope;
- limit attempts;
- report every attempted hypothesis, not only winners; and
- do not expose qualification results as permission to continue hill climbing
  inside the same campaign.

A genuinely sealed, hidden-label promotion set is not currently a Workbench
capability. Do not claim that qualification prevents benchmark overfitting.
Hidden promotion evaluation, rotating development slices, and benchmark refresh
policy belong to a later Benchmark Studio and product design.

## Evaluation Review App

The current app presents evaluation runs in one top-level view and uses URL
query parameters for selection. Extend that shell instead of creating a new
application or adopting a routing framework.

### Sidebar And Navigation

Add a persistent left sidebar beneath the existing Agent Workbench header:

```text
Evaluation runs
Autoresearch campaigns
```

Use URL state:

```text
?view=runs
?view=runs&run=<eval-id>
?view=campaigns
?view=campaigns&campaign=<campaign-id>
```

Default to `view=runs` so existing bookmarks and behavior continue to work.
The sidebar remains visible on overview and detail pages and collapses to a
compact selector on narrow screens.

The names reinforce the operator-path boundary:

- **Evaluation runs** contains traditional independent working and retained
  eval occurrences.
- **Autoresearch campaigns** contains only campaign histories from
  `.workbench/improvements/`.

The UI never treats a collection of ordinary evals as an inferred campaign and
never hides campaign eval occurrences from the traditional eval list.

### Read-Only Backend Projection

Extend the existing `ExplorerBackend` protocol and FastAPI shell with:

```text
GET /api/campaigns
GET /api/campaigns/{campaign-id}
```

`ProjectExplorerBackend` reads `campaign.json`, `state.json`, and
`trials.jsonl` directly from each generated-local campaign directory. The
projection:

- validates campaign IDs and prevents path escape;
- skips temporary or unrelated files;
- returns a typed finding for a malformed campaign instead of failing the
  entire list;
- preserves exact agent-version and eval IDs for drill-down;
- does not rewrite campaign state;
- does not create comparison artifacts; and
- does not scan Git history or infer missing ledger events.

The list response contains enough data for one row per campaign:

- campaign ID and status;
- creation time and termination reason;
- starting agent version and selection summary;
- benchmark/version and research/qualification scopes;
- selected runtime configuration labels;
- attempts used versus maximum;
- baseline and best selection-configuration score;
- outcome counts; and
- stored total cost and pricing coverage.

The detail response adds:

- all baseline points;
- all trial records in sequence;
- one metric series per runtime configuration;
- keep/discard/inconclusive/crash state;
- hypothesis, `change_summary`, changed paths, and `decision_summary`;
- exact eval IDs and costs for each configuration;
- incumbent transitions;
- qualification points; and
- any missing or unavailable linked evals.

### Campaign Page

The campaign overview lists campaigns newest first with filters for status,
starting agent, benchmark, and runtime configuration. It provides a clear empty
state when no campaigns exist.

The campaign detail page contains:

1. **Campaign summary**
   - starting agent and why it was selected;
   - benchmark and scopes;
   - runtime configurations and selection configuration;
   - attempt, cost, and termination summary.
2. **Performance over time**
   - x-axis: baseline at trial `0`, then trial number;
   - y-axis: frozen campaign primary metric;
   - one line per selected runtime configuration;
   - markers styled by keep, discard, inconclusive, crash, and qualification;
   - tooltip with agent version, model/configuration, score, cost, and decision;
   - click-through from a measured point to its traditional eval-run detail.
3. **What changed**
   - chronological trial rows;
   - hypothesis and stored `change_summary` relative to the parent;
   - changed paths;
   - before/after score by configuration;
   - cost;
   - keep/discard decision and `decision_summary`; and
   - exact commit, agent version, and eval links.

Reuse the app's existing Plotly dependency. Add one small campaign progress
chart component rather than generalizing the evidence-specific time-series
component or introducing another chart library.

The app is strictly observational. It does not start, stop, resume, modify,
delete, elevate, publish, merge, or deploy a campaign.

## Skill Coordination

The new campaign skill owns the multi-attempt authorization and loop. It routes
each step to existing narrow skills:

1. `$eval-results-analysis` — baseline failure clusters and exact comparisons.
2. `$pipeline-builder` — use-case pipeline and deterministic behavior changes.
3. `$ai-processor-builder` — only when the hypothesis changes AI workflow
   internals.
4. `$run-use-case-evals` — allocate, execute, resume, and verify each exact
   occurrence.
5. `$agent-eval-builder` — implement and verify the read-only campaign
   projection, API routes, sidebar, and page.
6. `$eval-lifecycle` — only after explicit post-campaign elevation direction.
7. `$publish-retained-eval` — only after explicit publication direction.

The ordinary eval-running rule remains valid: one direct eval request creates
at most one occurrence unless the user explicitly requests more. An authorized
campaign is such an explicit request for multiple occurrences inside a declared
envelope.

`project-guide` should route autonomous or repeated improvement requests to the
campaign skill. Its current single measured candidate workflow may remain as
the path for a user who explicitly requests one candidate only.

The campaign skill must never be triggered by a plain request to run one eval.
The eval runner must never initiate campaign setup, select a starting agent,
change source, or repeat measurements unless it is called from an already
authorized campaign.

## Failure Handling

| Failure | MVP behavior |
|---|---|
| Starting agent cannot resolve to the user-selected clean identity | Do not start; return to starting-agent selection. |
| Selected runtime configuration or pricing identity cannot resolve | Do not authorize the campaign until the user changes or removes it. |
| Focused test fails | Repair before measurement or record local crash. |
| Exact-example validation fails | Repair before measurement or record local crash. |
| Candidate identity cannot resolve | Record crash; do not run eval. |
| Eval interrupted | Resume the same occurrence. |
| One configuration occurrence fails | Preserve completed sibling occurrences; resume or finalize the bundle under the frozen eligibility rule. |
| Eval completes with execution failures | Compare only if eligibility permits; otherwise discard/crash. |
| Pricing unavailable | Continue only if cost is not a decision or hard limit; report incomplete coverage. |
| Frozen dimension changes | Stop the campaign. |
| Reusable-core change appears necessary | Stop and request reusable-scope approval. |
| Research winner fails qualification | End as `qualification_failed`. |
| User interrupts | Preserve state and report exact resume point. |

## Security And Safety

- Never place credentials, model responses, or benchmark evidence in Git.
- Keep campaign state and eval artifacts under ignored `.workbench/` paths.
- Verify that the campaign worktree's `.workbench` link resolves to the
  selected primary repository's generated-local `.workbench` directory.
- Do not modify published benchmark truth or frozen evidence packages.
- Do not allow a candidate to modify its evaluation profile, grader, acceptance
  rule, runtime configurations, campaign ledger schema, or termination limits.
- Do not automatically delete working or retained artifacts.
- Do not automatically elevate, publish, merge, or deploy.
- Validate exact paths before resetting or removing a campaign worktree.
- Treat source integration as a separate authorized action.

## Implementation Plan

### Increment 1: Skill-Driven Campaign

1. Add `agent-improvement-campaign/SKILL.md` and UI metadata.
2. Update `project-guide` routing and routing cases to distinguish:
   - one traditional eval occurrence;
   - one explicitly requested candidate improvement; and
   - a bounded multi-attempt autoresearch campaign.
3. Add negative routing tests proving a single-eval request cannot start a
   campaign and a campaign request cannot collapse to one eval.
4. Document the generated-local three-file ledger.
5. Require user-confirmed starting agent, benchmark scopes, runtime
   configurations, selection configuration, and attempt envelope.
6. Record nested per-configuration baseline, trial, and qualification evals
   plus change summaries.
7. Add architecture tests that enforce:
   - user-final starting-agent selection;
   - frozen benchmark scopes and runtime configurations;
   - explicit mutable paths;
   - multiple attempts within one envelope;
   - one occurrence per configuration in a trial bundle;
   - exact occurrence resume;
   - keep is not elevation;
   - qualification is separate from research;
   - no automatic publication or deployment; and
   - reusable-scope escalation.
8. Run one supervised, low-attempt campaign and record operational friction.

### Increment 2: Read-Only Campaign Review

This is part of the MVP, not deferred follow-on scope.

1. Extend `ExplorerBackend` and the reusable FastAPI app with list/detail
   campaign routes.
2. Project generated-local ledgers in `ProjectExplorerBackend` without creating
   a campaign database or mutation service.
3. Add shared TypeScript campaign contracts.
4. Add the persistent **Evaluation runs / Autoresearch campaigns** sidebar.
5. Add campaign overview, empty/error states, and detail URL state.
6. Add the Plotly progress chart with one line per selected runtime
   configuration and eval-run drill-down.
7. Render stored hypothesis, change, path, outcome, and decision summaries.
8. Verify that traditional eval navigation and deep links remain unchanged.
9. Add backend/API tests plus UI tests for:
   - sidebar routing;
   - no cross-routing between ordinary evals and campaigns;
   - campaign list/detail projection;
   - malformed-ledger findings;
   - model/configuration chart series;
   - change summaries;
   - eval-run links; and
   - read-only behavior.

### Increment 3: Harden Only Observed Gaps

After real campaign use and UI review, add the smallest missing helper for
observed failures. Possible examples:

- validate `campaign.json` and `state.json`;
- append/finalize ledger records safely;
- compute remaining attempts, occurrences, and stored cost; or
- verify frozen result dimensions.

Do not build a controller speculatively. A helper belongs in reusable Workbench
only when both campaign execution and the review projection need the same
validated contract.

### Deferred

- multi-candidate parallelism;
- unattended multi-agent research;
- automatic hypothesis generation services;
- durable campaign services, catalogs, and mutation APIs;
- UI campaign creation, control, lifecycle mutation, or cleanup;
- sealed promotion evaluation;
- adaptive research-scope selection;
- automatic cleanup;
- cross-project campaign learning; and
- production feedback ingestion.

## Acceptance Criteria

The MVP architecture is successful when:

- an FDE can authorize one concrete multi-attempt campaign envelope;
- Codex presents plausible starting agents and the user selects the exact
  starting version;
- the selected starting commit and agent version remain unchanged;
- every selected runtime configuration has an exact starting-agent baseline;
- Codex edits only an explicit use-case-owned mutable surface;
- every measured candidate resolves to a distinct immutable agent identity;
- every trial records its hypothesis, change summary, commit, per-configuration
  eval IDs, metrics, cost, and decision summary;
- benchmark, evidence, grader, runtime configurations, selection configuration,
  research scope, qualification scope, and repetitions remain frozen;
- interrupted evals resume by exact occurrence ID;
- discarded and crashed candidates do not advance the incumbent;
- kept candidates advance only the campaign-local incumbent;
- termination occurs at a declared boundary;
- the final incumbent receives at most one qualification occurrence per
  selected runtime configuration;
- qualification failure does not silently restart search;
- a traditional eval request creates no campaign state or source mutation;
- a campaign request executes the bounded campaign path rather than silently
  stopping after one ordinary eval;
- the review app has separate **Evaluation runs** and **Autoresearch campaigns**
  navigation;
- the campaign detail page charts performance by runtime configuration and
  shows stored change summaries with exact eval links;
- the campaign API and UI remain read-only;
- no candidate is elevated, published, merged, packaged, or deployed
  automatically;
- a successful campaign returns exact qualification evals and the source commit
  for explicit FDE action; and
- no new Experiment database, optimization service, scheduler, or mutation API
  is introduced.

## Verification Plan For Implementation

This document alone requires only link/path validation and
`git diff --check`.

Implementing Increment 1 changes repository skills, so it must run:

```text
quick_validate.py for each changed skill
uv run pytest tests/architecture/test_repository_skills.py -q
git diff --check
```

Implementing Increment 2 changes reusable explorer and project UI contracts, so
it must also run:

```text
uv run pytest <focused explorer backend/API tests> -q
uv run pytest -q
cd apps/eval_explorer/web && pnpm test
cd apps/eval_explorer/web && pnpm build
git diff --check
```

Any later Python helper must add focused tests for its owning layer and follow
the repository verification matrix. The full Python suite remains required
because the campaign projection crosses reusable Workbench, FastAPI, and UI
contracts.

## References

- `docs/product-strategy/company-ai-strategy-overview.md`
- `docs/product-strategy/jobs-to-be-done.md`
- `docs/product-strategy/mvp-scope.md`
- `use_case/docs/PipelineVersions.md`
- `.agents/skills/project-guide/SKILL.md`
- `.agents/skills/agent-eval-builder/SKILL.md`
- `.agents/skills/run-use-case-evals/SKILL.md`
- `.agents/skills/eval-results-analysis/SKILL.md`
- `.agents/skills/eval-lifecycle/SKILL.md`
- `packages/eval-ui/agent_eval_ui/app.py`
- `packages/eval-ui/web/src/eval-explorer-app.tsx`
- `workbench/apps/eval_explorer.py`
- [Karpathy autoresearch](https://github.com/karpathy/autoresearch)
- [Karpathy autoresearch program](https://github.com/karpathy/autoresearch/blob/master/program.md)
