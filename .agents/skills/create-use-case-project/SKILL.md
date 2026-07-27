---
name: create-use-case-project
description: Create and validate a separate Agent Workbench use-case repository from an exact template revision. Use to bootstrap project identity, clear reference-use-case paths, preserve reusable source, and prepare pipeline and explorer ports.
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
   - `tests/test_repository_skills.py` was preserved and passes in the generated
     project after the reference-only `use_case/tests/` seam was cleared;
   - the single manifest-declared `use_case/` reference root was cleared and
     rebuilt as the neutral standard skeleton;
   - local evals, retained versions, credentials, caches, and build output were
     not copied;
   - `README.md`, `EvalRunbook.md`, `.env.example`, `models.yaml`, and
     `workbench.project.json` contain the new project identity;
   - reusable `model_pricing.yaml` remains valid and satisfies every
     `models.yaml` pricing reference without use-case identity; and
   - validation reports no reference-identity leakage.
   - the neutral frontend tests and build pass before project-specific explorer
     code is added.
6. Capture durable domain context in `use_case/docs/PROJECT_CONTEXT.md`.
   Treat the generated `EvalRunbook.md` as a marked bootstrap placeholder, not
   an executable eval guide.
7. Hand off evidence and control-pipeline work to
   `$benchmark-pipeline-port`, then use `$port-eval-explorer-use-case` for the
   project evidence view.

Use the
[repository verification matrix](../project-guide/references/verification-matrix.md)
for any template or bootstrap implementation change.

## Boundaries

- Keep every skill under root `.agents/skills/`.
- Keep `mi-core/` distinct; do not move unrelated Workbench code into it.
- Do not initialize over a non-empty destination.
- Do not use a branch in an existing use-case repository as the new project.
- Do not copy Benchmark Studio workflow code, mutable benchmark truth, secrets,
  local evals, or retained agent artifacts.
- Do not add package publishing, submodules, or automatic cross-repository
  upgrades for MVP.
