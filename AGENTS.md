# Project Overview
## Background
- The purpose of this project is to build a pipeline for a particular use case built on top of the mi_core library. The typical pattern is to retrieve data, process data, and then solve the use case with compute processors and, when useful, AI processors.
- The first thing a developer should do is populate the relevant files in `/docs/use_case/` with the durable details of the use case.
- Do not update the markdown files in `/docs/use_case/` unless the user explicitly asks for it. They are not running implementation logs and must not be overwritten with notes about how the current pipeline or intermediate experiments work.

## Where to find helpful documentation related to how to build a pipeline
- The README.md file contains instructions on how to setup and run the pipeline locally as well as high level descriptions of the mi-core pipeline.
- Use `docs/human_dev_guidance/` for human-oriented development guidance about template structure, customization, and lifecycle.
- Use the available **agent skills** (`.agents/skills/`) as the primary reference for coding-agent implementation guidance when building and evolving a pipeline. When the skills prove insufficient, refer to the mi_core library.

## How to interpret repo skills
- The skills in `.agents/skills/` are recommended implementation guidance for AI coding agents working in `mi-core` style repos.
- The skills do not need to match the current repo exactly.
- Existing repo code is the source of truth for current local behavior.
- If the repo already uses a different but coherent approach, preserve that approach unless the user explicitly asks to migrate toward the skill pattern.
- Concrete repo references inside skills such as file paths, entrypoints, and startup docs should still be accurate.

## Runtime And Package Inspection
- This repo is `uv`-managed and the project environment lives in `.venv`.
- Do not spend time probing system `python`, `pip`, or site-packages on `PATH` before using the repo environment.
- Always use `uv run ...` for repo commands, imports, version checks, and installed-package inspection.
- When you need installed library behavior for `mi-core`, `mi.ai`, or other dependencies, inspect the package through `uv run python ...`, not through assumptions about globally installed Python.
- Assume `.venv` is the correct environment unless the user explicitly tells you to use something else.
- Useful examples:
  - `uv run python -c "import importlib.metadata; print(importlib.metadata.version('mi-core'))"`
  - `uv run python -c "import inspect; from mi.core.pipeline_orchestrator import PipelineOrchestrator; print(inspect.getsourcefile(PipelineOrchestrator))"`
  - `uv run python -m pytest`

## src/experimental_core folder
- This contains code that is not yet part of the mi_core library, but contains useful common code that can be used to build a pipeline.
- Do not modify the experimental_core folder without asking the user for permissionb (unless they explicitly ask you to).
- The mi_core library is not modifiable during the development of this project, you may surface issues to the user for consideration. (e.g. there's a bug from mi_core that's blocking this project from progressing)

