# Repository Verification Matrix

Use every row touched by the change. Start focused, then run the broader gate
when the change affects shared contracts or multiple layers. Do not claim a
check passed when it was skipped; report the reason and residual risk.

| Changed layer | Required focused checks | Broader completion gate |
|---|---|---|
| Python behavior | `uv run pytest <nearest-test-paths> -q` | `uv run pytest -q` for reusable, cross-cutting, or multi-package changes |
| Python style or types | `uv run ruff check <changed-python-paths>` | `uv run basedpyright` when typed source or public contracts changed |
| Pipeline registry or `.ppln` | Build through the real registry and run nearest pipeline contract/runner tests | Run one exact, explicitly versioned published example using `EvalRunbook.md`; do not replace it with a one-example eval |
| Reusable `mi-core` | After explicit approval, run focused `uv run pytest mi-core/tests/<area> -q` plus affected root tests | Run the relevant `mi-core` package suite when shared behavior changed broadly |
| Eval core, lifecycle, bootstrap, or explorer API | Run the focused package/root contract tests for every changed boundary | Run the full Python suite when schemas or cross-package contracts changed |
| Project explorer UI | In `www/`, run `pnpm test` | In `www/`, run `pnpm build`; it includes TypeScript and evidence-bundle checks |
| Repository skill | Run `quick_validate.py` from the installed `skill-creator` package for each changed skill | Run `uv run pytest tests/test_repository_skills.py -q` and smoke-test documented commands or unconditional paths |

Always finish with `git diff --check`. For documentation-only changes, verify
links, paths, and shown CLI flags against current source or `--help`.

External credentials, hosted evidence, or model calls are not implied by this
matrix. When a required exact-example or integration check needs unavailable
access, could incur cost, or exceeds the user's authorization, run all safe
local checks and report the blocked gate instead of silently substituting a
weaker check.
