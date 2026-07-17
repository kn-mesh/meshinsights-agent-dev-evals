# Mesh Insights Documentation

Comprehensive documentation for the Mesh Insights data pipeline framework.

## Accessing Documentation Programmatically

```python
from importlib.resources import files

# Get the docs package
docs = files("mi.docs")

# Read any guide
architecture = (docs / "architecture.md").read_text()

# Access component guides
components = files("mi.docs.components")
retrievers = (components / "retrievers.md").read_text()
```

## Documentation Index

### Getting Started
- [getting-started.md](getting-started.md) - Quick start tutorial
- [architecture.md](architecture.md) - Pipeline execution model and concepts

### Components
- [components/data-objects.md](components/data-objects.md) - Type-safe data containers
- [components/retrievers.md](components/retrievers.md) - Fetching data from sources
- [components/processors.md](components/processors.md) - Transforming and analyzing data
- [components/hydrators.md](components/hydrators.md) - Converting data between stages
- [components/actions.md](components/actions.md) - Executing side effects

### Pipeline Assembly
- [pipeline-builder.md](pipeline-builder.md) - Fluent API for constructing pipelines
- [yaml-configuration.md](yaml-configuration.md) - Declarative pipeline definitions
- [orchestrator.md](orchestrator.md) - Running pipelines at scale
- [registry.md](registry.md) - Component discovery and schema generation

### Utilities
- [utilities.md](utilities.md) - Caching, thread-safe execution, and helpers

### AI Integration
- [ai.md](ai.md) - AI workflow and agent processors (Anthropic, Azure OpenAI, Azure Foundry, OpenRouter)

### CLI
- [cli.md](cli.md) - Installation, usage, and when to use the CLI
