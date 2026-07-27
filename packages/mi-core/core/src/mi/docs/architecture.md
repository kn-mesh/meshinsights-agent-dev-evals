# Architecture Overview

`mesh.insights.core` is a framework repo, not a concrete pipeline project. It
ships the reusable runtime (`mi-core`) and the terminal CLI (`meshinsights-cli`)
that downstream projects use to define, validate, and run pipelines. Concrete
starter implementations now live in the companion templates repository:
`https://github.com/Mesh-Systems-Eng/mesh.insights.templates`.

## System Context

```mermaid
flowchart LR
    user["Pipeline developer / operator"]
    system["Mesh Insights Pipeline Toolkit
    (mi-core + mi CLI)"]

    project["Consumer pipeline project
    pyproject.toml, .ppln, custom components, .env"]
    data["Data sources and sinks
    built-in: CSV, JSON
    project-specific: APIs, DBs, files, services"]
    llm["Optional LLM providers
    Azure / Anthropic / Google / OpenRouter"]
    telemetry["Optional telemetry backend
    Logfire or OTLP collector"]
    auth["Auth/setup tools
    Azure CLI, browser-based credential flows"]
    templates["Templates repository
    scaffolded starter projects"]

    user -->|"runs mi commands, authors components"| system
    system <-->|"loads config, scans components, writes generated artifacts"| project
    system <-->|"retrieves from and acts on"| data
    system -->|"optional ai requests"| llm
    system -->|"optional traces/logging"| telemetry
    system -->|"project init scaffolding"| templates
    system -->|"credential bootstrap"| auth
```

## Containers And Subsystems

```mermaid
flowchart LR
    subgraph host["Developer machine / Python runtime"]
        subgraph cli["Container: meshinsights-cli"]
            commands["Typer CLI commands
            run | registry | auth | init | update"]
            ui["Terminal UI
            Rich/Textual-style prompts, wizards, banners"]
        end

        subgraph core["Container: mi-core"]
            registry["Registry and schema subsystem
            AST scan, dynamic import, JSON schema generation"]
            builder["PipelineBuilder
            fluent API + from_yaml()"]
            pipeline["Pipeline runtime
            retrieve -> process -> act"]
            orchestrator["PipelineOrchestrator
            serial | threaded | process"]
            ai["Optional mi.ai subsystem
            workflow + agent mixins"]
            utilities["Utilities
            shared TTL cache, RootExecutor"]
            bootstrap["Bootstrap
            .env loading + telemetry setup"]
        end

        project["Consumer project code and config
        custom components, pyproject, .ppln"]
        env[(".env / .env.template")]
        regstore[(".insights/registry.json")]
        schemastore[(".insights/schemas/pipeline_schema.json")]
        logstore[(".insights/logs/*.log")]
        vscode[(".vscode/settings.json")]
        sources[("Files / external systems")]
    end

    llm["LLM providers"]
    otel["Logfire / OTLP backend"]
    templates["Templates repo"]

    commands --> builder
    commands --> registry
    commands --> templates
    ui --- commands

    registry <--> project
    registry --> regstore
    registry --> schemastore
    registry --> vscode

    builder --> registry
    builder --> pipeline
    builder --> project

    pipeline --> bootstrap
    bootstrap --> env
    bootstrap --> otel

    pipeline <--> sources
    pipeline --> logstore
    pipeline --> ai
    ai --> llm

    orchestrator --> pipeline
    utilities -. shared infra .- pipeline
    utilities -. shared infra .- orchestrator
```

## Major Subsystems

- **`meshinsights-cli`**: the user-facing entry point. It runs pipelines,
  manages the registry, helps configure credentials, scaffolds new consumer
  projects from templates, and updates the installed CLI.
- **Registry and schema generation**: scans consumer-project Python modules for
  classes that inherit from framework base types, writes `.insights/registry.json`,
  generates `.ppln` JSON schema, and wires VS Code YAML settings.
- **PipelineBuilder and YAML loading**: converts declarative `.ppln` files into
  instantiated retrievers, hydrators, processors, actions, and typed data
  objects.
- **Pipeline runtime**: coordinates the retrieve, process, and act stages,
  manages receipts, logs, error behavior, and stage transitions through
  hydrators.
- **PipelineOrchestrator**: runs the same pipeline template across many items
  with serial, threaded, or subprocess execution models and propagates trace
  context into worker processes.
- **`mi.ai`**: optional AI extensions for processors. It supports one-shot
  structured workflows and tool-using agents through a lazily resolved backend
  built around `pydantic-ai`.
- **Utilities and observability**: shared TTL cache, root-thread execution
  helper for unsafe libraries, `.env` bootstrap, and telemetry bootstrap to
  Logfire or OTLP.

## Typical Consuming Project

Concrete examples belong in the templates repo, but a typical consuming project
that uses this framework looks like this:

```mermaid
flowchart LR
    dev["Developer"] -->|"mi init or manual setup"| proj["Consumer project repo"]

    subgraph proj["Consumer project repo"]
        ppln["pipelines/*.ppln"]
        code["custom retrievers/processors/actions/hydrators"]
        pyproject["pyproject.toml"]
        env[".env / .env.template"]
        artifacts["generated artifacts
        .insights/*"]
    end

    run["mi run pipelines/example.ppln"] --> scan["registry refresh + schema validation"]
    scan --> build["PipelineBuilder.from_yaml()"]
    build --> exec["Pipeline.run()"]
    exec --> source["source systems"]
    exec --> sink["actions / side effects"]
    exec --> artifacts

    dev --> run
    run --> proj
```

Typical project responsibilities:

- own the domain-specific components and data contracts
- own the `.ppln` pipeline definitions and `.env` configuration
- treat `.insights/` and `.vscode/settings.json` as generated support artifacts
- use this repo for the framework runtime, not as the source of example project
  behavior

## Notes

- This repo currently ships built-in file retrievers for CSV and JSON, but most
  real integrations are expected to come from consumer projects.
- The framework does not include a built-in scheduler or durable message broker.
  Pipelines are typically invoked by the CLI or by a host application.
- `RootExecutor` uses in-memory thread and process queues for coordination, but
  those are framework internals rather than an external queueing subsystem.

## See Also

- [Getting Started](getting-started.md) — how to structure a consuming project
- [Pipeline Builder](pipeline-builder.md) — fluent and YAML-driven assembly
- [Orchestrator](orchestrator.md) — parallel execution models
- [Registry](registry.md) — component discovery and schema generation
