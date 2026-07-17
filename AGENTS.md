# Project Overview
## Background
- The purpose of this project is to build a pipeline for a particular use case built on top of the mi_core library. The typical pattern is to retrieve data, process data, and then solve the use case with compute processors and, when useful, AI processors.
- The first thing a developer should do is populate the relevant files in `/docs/use_case/` with the durable details of the use case.
- Do not update the markdown files in `/docs/use_case/` unless the user explicitly asks for it. They are not running implementation logs and must not be overwritten with notes about how the current pipeline or intermediate experiments work.

## Where to find development guidance
- The README.md file contains setup, entry points, and a map of the available Codex skills.
- Use `$project-guide` for developer questions about repository architecture, customization, lifecycle, ownership boundaries, or which specialized skill to use.
- Use the available **agent skills** (`.agents/skills/`) as the primary development guidance. They should support both implementation work and questions from developers using Codex.
- When a skill is insufficient or may be stale, inspect the current code, tests, pipeline configs, and the repository-local `mi-core/` source. The codebase is the source of truth for current behavior.

## How to interpret repo skills
- The skills in `.agents/skills/` are recommended development guidance for AI coding agents working in `mi-core` style repos.
- The skills do not need to match the current repo exactly.
- Existing repo code is the source of truth for current local behavior.
- If the repo already uses a different but coherent approach, preserve that approach unless the user explicitly asks to migrate toward the skill pattern.
- Concrete repo references inside skills such as file paths, entrypoints, and startup docs should still be accurate.

## Runtime And Package Inspection
- This repo is `uv`-managed and the project environment lives in `.venv`.
- Do not spend time probing system `python`, `pip`, or site-packages on `PATH` before using the repo environment.
- Always use `uv run ...` for repo commands, imports, version checks, and installed-package inspection.
- `mi-core` and `mi.ai` are editable repository-local source under `mi-core/core/src/mi/`; inspect them directly or through `uv run python ...`, not through assumptions about a static installed package or globally installed Python.
- Assume `.venv` is the correct environment unless the user explicitly tells you to use something else.
- Useful examples:
  - `uv run python -c "import importlib.metadata; print(importlib.metadata.version('mi-core'))"`
  - `uv run python -c "import inspect; from mi.core.pipeline_orchestrator import PipelineOrchestrator; print(inspect.getsourcefile(PipelineOrchestrator))"`
  - `uv run python -m pytest`

## src/experimental_core folder
- This contains code that is not yet part of the mi_core library, but contains useful common code that can be used to build a pipeline.
- Do not modify the experimental_core folder without asking the user for permission (unless they explicitly ask you to).
- Modify `mi-core/` directly when requested behavior belongs in the framework. Keep unrelated framework refactors out of scope and run the relevant `mi-core` tests after changes.
