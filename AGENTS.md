# Agent Workbench Repository Guidance

## Ground Work In Repository Evidence

Read the request, applicable nested instructions, `docs/use_case/`, current
source and configuration, focused tests, and runnable entry points before
changing behavior. Treat current coherent code as the local contract. Use
`README.md` for on-ramp context, not as stronger evidence than source or tests.

Use `uv run` for Python commands. Use the package manager declared by each
non-Python workspace.

## Respect Ownership Boundaries

Use `workbench.template.json` as the authoritative ownership and path inventory:

- `reusable_library`: shared library mechanics such as `mi-core/`.
- `reusable_workbench`: shared evaluation, explorer, bootstrap, versioning,
  lifecycle, publication, storage, and runner mechanics.
- `reference_use_case`: replaceable project data, rules, prompts, pipelines,
  evidence projection, and UI composition.
- `root_infrastructure`: repository-wide configuration, skills, and guidance.
- `generated_local`: local outputs that are not template source.

Before changing a reusable library or reusable Workbench path, state the owning
scope and focused tests. Proceed when the request clearly requires a change in
that named reusable scope. If the request is project-local or the ownership
expansion is ambiguous, identify the exact reusable paths and contracts and ask
once before expanding scope. Record the canonical upstream target or pending
action for an approved shared fix.

Keep use-case meaning in manifest-declared reference paths. Make behavior
reusable only when cross-use-case evidence supports the same semantics.

## Verify Every Changed Layer

For implementation work, read
`.agents/skills/project-guide/references/verification-matrix.md` and run every
row touched by the change. Start with focused checks, run the broader gate when
shared contracts or multiple layers changed, and finish with `git diff --check`.

Do not claim a skipped check passed. Report the reason, residual risk, and any
integration check blocked by credentials, cost, or authorization.

For repository-skill changes, validate each changed skill with the installed
`skill-creator` `quick_validate.py`, then run
`uv run pytest tests/test_repository_skills.py -q`.
