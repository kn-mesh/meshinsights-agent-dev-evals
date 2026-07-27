# mi-core

A flexible, type-safe framework for building multi-stage data pipelines.

## Installation

```bash
# Using uv (recommended)
uv add mi-core

# With AI support (optional)
uv add 'mi-core[ai]'
```

## Quick Start

```python
from mi.core import PipelineBuilder, PipelineConfig

pipeline = (
    PipelineBuilder()
    .with_config(PipelineConfig(name="my_pipeline"))
    .add_retriever(MyRetriever(config))
    .with_retrieve_hydrator(MyRetrieveHydrator())
    .add_processor(MyProcessor())
    .with_process_hydrator(MyProcessHydrator())
    .add_action(MyAction())
    .with_action_hydrator(MyActionHydrator())
    .build()
)

receipt = pipeline.run()
```

## Documentation

Full documentation ships with the package:

```python
from importlib.resources import files

docs = files("mi.docs")
readme = (docs / "README.md").read_text()
```

## Package Structure

```
mi/
├── core/        # Pipeline framework
├── utilities/   # Caching, thread-safe execution
├── ai/          # AI workflow and agent processors (optional)
└── docs/        # Comprehensive documentation
```

## Requirements

- Python 3.13.5
- pydantic >= 2.12.3
- pyyaml >= 6.0.0
- cachetools >= 5.3.3

## Optional AI Dependencies

```bash
uv add 'mi-core[ai]'  # AI support (pydantic-ai, logfire)
```

This enables all supported providers: Anthropic (direct), Azure OpenAI, Azure Foundry (Claude via Azure), and OpenRouter.
