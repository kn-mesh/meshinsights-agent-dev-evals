# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added backend-neutral AI capabilities, instruction-bearing reusable toolsets, and Agent Skills-compatible `SKILL.md` loading with progressive disclosure through pydantic-ai.

### Changed
- Upgraded the `mi.ai` backend to pydantic-ai 2.11.0, including the v2 retry and usage APIs while preserving the previous early agent-completion behavior.
- Split AI transport, tool, and output-validation retry budgets and added opt-in request, token, and tool-call usage limits with unlimited token/tool defaults.

### Removed
- Removed the legacy combined `retries` processor setting and obsolete internal compatibility helpers; configurations must use the explicit transport, tool, and output retry budgets.

## [0.5.2] - 2026-04-13
### Changed
- **Architecture and onboarding docs** — refocused the architecture documentation on the framework and CLI shipped by this repo, added a "typical consuming project" view, and updated README/getting-started guidance to point concrete starter implementations at `mesh.insights.templates` instead of missing in-repo examples.

## [0.5.1] - 2026-03-18
### Added**
- **GPT 5.4 mini and nano** as valid model paths for Azure

### Changed
- **`mi init` deploy animation** — the truck/rocket animation now loops continuously until project scaffolding completes, instead of playing once and leaving the terminal static during long network operations.

### Fixed
- **Versioning/release automation** — version bumps now only run for merged PRs explicitly labeled `major`, `minor`, or `patch`, and changelog handling is split into a dedicated `scripts/changelog.py` utility shared by the bump and release workflows.
- **CLI packaging bug** — `monitor.css` was missing from the built wheel, causing `FileNotFoundError` on any CLI command (e.g., `mi auth`). Added `[tool.setuptools.package-data]` to `cli/pyproject.toml` to include the file.

### Changed
- Updated `mi.ai` reasoning configuration to use pydantic-ai's unified `thinking` levels directly, including support for `minimal` and `xhigh`
- Simplified `ReasoningSpec` so model mappings now resolve straight to unified reasoning effort values instead of bespoke mode handling

### Removed
- `ReasoningMode` from the public `mi.ai` model config API in favor of the `ReasoningEffort` shim enum

## [0.5.0] - 2026-03-17
### Added
- **`mi auth` command** — interactive wizard for configuring credentials
- **CLI UI system** (`cli/src/cli/ui`) — rich terminal components including themed display, picker, ASCII art, conveyor animation, and pipeline runner visuals
- **Google Gemini provider support** — direct Gemini model access with model registration and tests
- **GitHub CI workflow** — parallel Ruff, Basedpyright, and Pytest checks on pull requests
- **PR template and CODEOWNERS** for standardized pull request workflow

### Changed
- Refactored CLI component TUI system with new `ui/` module structure
- `mi init` project scaffolding refactored and expanded
- CLI version display and self-update improvements
- Pydantic AI backend updated with extended model mapping and error handling
- Telemetry bootstrap updated for broader compatibility
- Package dependency bumps across core and CLI

### Fixed
- AI agent and workflow test reliability improvements
- Registry scanner and validation cleanups
- Code properly passes CI checks

## [0.4.2] - 2026-02-19
### Added
- **Image and DataFrame input support** for AI workflows (`mi.ai.dataframe`, expanded `mi.ai.message`)
- `DataFrameContent` content block type for passing structured tabular data to AI models
- `ImageContent` now supports inline base64 and URL-based image inputs
- Fast-fail error handling for unsupported message content types in the pydantic-ai backend
- Test suite for image and DataFrame input handling

## [0.4.1] - 2026-02-19
### Added
- **Backend abstraction layer** (`mi.ai.backends`) for AI execution, with pluggable backend resolution and registration via `BackendSpec`
- **New AI primitives** decoupled from pydantic-ai internals:
  - `mi.ai.message` — `UserMessageBuilder`, multimodal `ContentBlock` types (`TextContent`, `ImageContent`, `MediaContent`)
  - `mi.ai.tools` — `ToolContext`, `ToolSet`, `ToolSetBuilder`, `@ai_tool` decorator
  - `mi.ai.model_config` — `ModelRef` parser, `ReasoningSpec`/`ReasoningMode`, provider and model registration (`register_provider`, `register_model`, `register_reasoning_spec`)
- **`bootstrap_telemetry()` utility** for automatic telemetry initialization (Logfire-first with `if-token-present`, OTel SDK fallback), exported from `mi.core`
- `PipelineConfig.bootstrap_otel` flag to opt out of automatic telemetry initialization
- Comprehensive test suites for AI model mapping, processor config, and telemetry bootstrap

### Changed
- **Refactored AI mixins** — `AIWorkflowMixin` and `AIAgentMixin` now delegate execution through the backend interface instead of calling pydantic-ai inline
- **Expanded `AIProcessorConfig`** with `backend`, `retries`, `timeout`, `output_retries`, `tool_timeout`, `provider_options`, `backend_options`, and `attach_response` fields
- **Updated supported AI providers** — documentation and model config now target Anthropic (direct), Azure OpenAI, Azure Foundry (Claude via Azure), and OpenRouter; direct OpenAI API access removed
- CLI `run_pipeline` and process-mode orchestrator now auto-bootstrap telemetry before execution
- `mi.ai` public exports reorganized around the new message, tools, and model-config modules
- `import mi` no longer hard-fails when AI optional dependencies are missing

### Removed
- **Legacy AI modules** — entire `mi.ai.legacy` package (agent adapters, workflow adapters, credentials, convert helpers)
- `mi.ai.types` module — replaced by `mi.ai.message`, `mi.ai.tools`, and `mi.ai.model_config`

### Fixed
- Azure Foundry Anthropic model initialization now uses standard `ANTHROPIC_FOUNDRY_*` environment-based credential resolution instead of explicit `provider_options`
- Reasoning settings precedence ensures `azure:claude-*` resolves to Anthropic budget-based thinking before the generic `azure:*` effort-based pattern

## [0.4.0] - 2025-02-04
### Added
- **RootExecutor utility** (`mi.utilities.root_executor`) for executing functions on the main thread from worker threads/processes - essential for thread-unsafe libraries
- `@bound` decorator for automatic routing of function calls through RootExecutor
- Comprehensive documentation suite (12 markdown files) in `core/docs/`:
  - Architecture overview and getting started guide
  - Component guides (data objects, retrievers, processors, hydrators, actions)
  - Pipeline builder and orchestrator documentation
  - Utilities reference and YAML configuration guide

### Changed
- **BREAKING**: Package namespace restructured from `mi_core`/`mi_utilities` to `mi.core`/`mi.utilities`
  - `from mi_core import ...` → `from mi.core import ...`
  - `from mi_utilities import ...` → `from mi.utilities import ...`
- Moved `cache_adapter` from `mi_core.utils` to `mi.utilities`
- Documentation now ships with the package under `src/docs/`

## [0.3.1] - 2025-12-16
### Changed
- Bumped pydantic revision for AI module compat

### Fixed
- Registry scanner now correctly ACTUALLY handles files outside project root
- Registry logs will now print to typer when running from the cli
- base objects will now populate the registry as intended

## [0.3.0] - 2025-12-15
### Added
- CSV and JSON retrievers (`CsvRetriever`, `JsonRetriever`) with schema validation and type conversion
- Shared typing utilities in `mi_core.utils.typing` for schema validation and type coercion
- Automatic discovery of `mi_core` components from venv packages during registry scanning
- Pipeline metadata support for filtering and unit-based data selection
- Pipeline orchestrator for running pipelines across multiple items with concurrency support

### Changed
- Registry scanner now automatically scans installed `mi_core` packages from virtual environment site-packages
- Retrievers module uses lazy imports for pandas to support optional dependency installation
- Improved module path extraction for components installed in venv site-packages

### Fixed
- Registry scanner now correctly handles files outside project root (e.g., from site-packages)

## [0.2.0] - 2025-12-01
### Added
- CLI now can update to a given branch

### Changed
- Updated CLI to work with virtual environments
- Base classes can be targeted in the .ppln yaml definition

### Fixed
- CLI breaks on Windows
- Fixed some poorly defined docstrings

## [0.1.0] - 2025-11-20
### Added
- Initial release
- Core pipeline framework
- CLI tooling
- Example implementations

[Unreleased]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.5.2...HEAD
[0.5.2]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.4.1...v0.5.0
[0.4.2]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Mesh-Systems-Eng/mesh.insights.core/releases/tag/v0.1.0
