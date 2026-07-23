# Reusable Core Change Handoffs

## Purpose

Track approved reusable changes made while implementing a use case so they are
not stranded in one project repository. A reusable change is not complete until
it has an upstream reference or an explicit pending action.

## Pending

### Template ownership and reference reset

- **Local owner:** `src/project_bootstrap/`, `workbench.template.json`, and
  root `.agents/skills/`
- **Why reusable:** Every new use-case repository needs the same ownership
  contract, reference reset, generated project-neutral docs, skill approval
  gate, and leakage validation.
- **Validation:** `tests/test_project_bootstrap.py`,
  `tests/test_repository_skills.py`, full Python regression, and explorer
  frontend tests/build.
- **Canonical target:** The Agent Workbench template source recorded by
  `src.project_bootstrap.service.DEFAULT_TEMPLATE_SOURCE`.
- **Status:** Pending upstream publication after this codebase-alignment work is
  reviewed and committed.
- **Required follow-up:** Port the final manifest, bootstrap behavior, and root
  skills to the canonical template revision before initializing the next
  use-case repository.

### Protected evaluation workflow and model pricing

- **Local owner:** `src/evals/`, `src/model_configuration.py`,
  `model_catalog.py`, `EvalRunbook.md`, and the operational eval/runtime skills.
- **Why reusable:** Full/list/named-section scope, threaded-default execution,
  missing-only resume, frozen pricing, and aggregate unit-cost statistics are
  Workbench behaviors shared by every use case.
- **Validation:** `tests/test_eval_orchestration.py`,
  `tests/test_model_configuration.py`, `tests/test_schema_v1_operator_contracts.py`,
  full Python regression, Ruff, and basedpyright.
- **Canonical target:** The Agent Workbench template and reusable eval source;
  no `mi-core/` change was required.
- **Status:** Pending upstream publication after this codebase-alignment work is
  reviewed and committed.
- **Required follow-up:** Carry the supported CLI surface, run/result contracts,
  model configuration command, and updated skills into the canonical template.

### Working and retained eval lifecycle

- **Local owner:** `src/eval_lifecycle/`, `src/apps/eval_explorer.py`,
  `agent-dev-eval-ui/`, `www/`, and the lifecycle/analysis skills.
- **Why reusable:** Every use case needs the same full-run elevation, compact
  retained result, agent/evidence provenance, permanent deletion safeguards,
  and read-only working/retained explorer behavior.
- **Validation:** `tests/test_eval_lifecycle.py`,
  `tests/test_eval_orchestration.py`, `tests/test_eval_explorer.py`, frontend
  tests/build, full Python regression, Ruff, and basedpyright.
- **Canonical target:** The Agent Workbench template, reusable explorer backend,
  and `agent-dev-eval-ui`; no `mi-core/` change was required.
- **Status:** Pending upstream publication after this codebase-alignment work is
  reviewed and committed.
- **Required follow-up:** Publish the lifecycle package, explorer contracts,
  UI lifecycle filters, and `$eval-lifecycle` skill with the canonical template
  revision before bootstrapping the next use case.
