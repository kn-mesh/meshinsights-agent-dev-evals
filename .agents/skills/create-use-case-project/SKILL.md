---
name: create-use-case-project
description: Create and validate a separate Git repository for a new Agent Workbench use case from an exact template revision. Use when an FDE wants to bootstrap a project, clear the template reference seam, configure non-secret Benchmark Studio and model identities, verify reusable source was preserved, or hand the clean project to the benchmark pipeline and explorer port workflows.
---

# Create Use-Case Project

Create a clean use-case repository without editing or deleting reusable
libraries by hand.

## Workflow

1. Read `workbench.template.json` and confirm it classifies the reusable
   libraries, reusable Workbench paths, replaceable reference paths, root
   skills, and generated local state.
2. Review a non-secret bootstrap spec based on
   `bootstrap_configs/example.project.json`. Never put credentials in it.
3. Initialize a new, separate Git repository from an exact template revision:

   ```bash
   uv run python -m src.project_bootstrap.cli --json init <destination> \
     --spec <bootstrap-spec.json> \
     --template-source <template-repository> \
     --template-ref <tag-branch-or-commit>
   ```

4. Inspect the reported template revision and run validation:

   ```bash
   uv run python -m src.project_bootstrap.cli --json validate <destination>
   ```

5. Confirm:
   - reusable libraries and generic root skills were preserved;
   - manifest-declared reference paths were cleared;
   - local evals, retained versions, credentials, caches, and build output were
     not copied;
   - `README.md`, `EvalRunbook.md`, `.env.example`, `models.yaml`, and
     `workbench.project.json` contain the new project identity; and
   - validation reports no reference-identity leakage.
6. Capture durable domain context in `docs/use_case/PROJECT_CONTEXT.md`.
7. Hand off evidence and control-pipeline work to
   `$benchmark-pipeline-port`, then use `$port-eval-explorer-use-case` for the
   project evidence view.

## Reusable-Code Approval

Inspect reusable source when necessary, but do not modify it without explicit
user approval. Before editing `mi-core/`, `agent-dev-eval-core/`,
`agent-dev-eval-ui/`, reusable Workbench code, bootstrap, versioning, or generic
lifecycle mechanics:

1. show why the use-case layer cannot correctly satisfy the request;
2. identify the exact reusable paths and contracts;
3. explain the cross-use-case behavior and focused tests; and
4. ask the user for approval.

If an approved shared fix is made locally, record the canonical template or
library target and the upstream issue, PR, commit, or pending action before
calling the work complete.

## Boundaries

- Keep every skill under root `.agents/skills/`.
- Keep `mi-core/` distinct; do not move unrelated Workbench code into it.
- Do not initialize over a non-empty destination.
- Do not use a branch in an existing use-case repository as the new project.
- Do not copy Benchmark Studio workflow code, mutable benchmark truth, secrets,
  local evals, or retained agent artifacts.
- Do not add package publishing, submodules, or automatic cross-repository
  upgrades for MVP.
