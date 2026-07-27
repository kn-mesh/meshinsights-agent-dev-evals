# mesh.insights.core – Getting Started

This guide walks through a minimal, opinionated project layout for wiring up a
Mesh Insights pipeline. Copy the structure below into your own package (under
`my_project/`) and replace the component logic with your domain-specific
behavior. For concrete starter implementations, use `mi init` or the companion
templates repository:

- `https://github.com/Mesh-Systems-Eng/mesh.insights.templates`

## Environment Setup

1. Install dependencies once from the repo root:
   ```bash
   uv sync
   ```
2. Run Python entry points through UV so the editable `mi-core` package and
   workspace dependencies are on `PYTHONPATH`:
   ```bash
   uv run basedpyright
   uv run pytest
   ```
3. (Optional) Install the `mi` CLI so that `mi run …` commands are available.
   When working on a checkout, point UV/pip at the local subpackage:
   ```bash
   uv tool install --from ./cli mi
   # or: pip install -e cli
   ```
   To mirror production in a clean environment, install from the private Git
   repository instead (swap in your org’s HTTPS URL):
   ```bash
   uv tool install --from "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli" meshinsights-cli
   # or: pip install "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli"
   ```
   Use `mi --help` to confirm the command is available.

```
my_project/
├── src/
│   ├── actions/
│   │   ├── __init__.py
│   │   └── publish_summary_action.py
│   ├── hydrators/
│   │   ├── __init__.py
│   │   ├── finalize_action_hydrator.py
│   │   ├── process_to_action_hydrator.py
│   │   └── retrieve_to_process_hydrator.py
│   ├── objects/
│   │   ├── __init__.py
│   │   ├── action_object.py
│   │   └── process_object.py
│   ├── processors/
│   │   ├── __init__.py
│   │   └── customer_metrics_processor.py
│   ├── retrievers/
│   │   ├── __init__.py
│   │   └── customer_csv_retriever.py
│   ├── example_pipeline.py
│   └── run_from_yaml.py
├── pipelines/
│   └── customer_insights.ppln
├── data/
│   └── customers.csv
└── pyproject.toml
```

**Note:** The `src/` directory pattern is the standard Python project layout. Each subdirectory includes an `__init__.py` file to make them proper Python packages, enabling clean imports.

## 1. Project Configuration

Before creating components, set up your project structure. Create a `pyproject.toml` at the project root:

```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.13.5"
dependencies = [
    "mi-core",
    "pandas>=2.3.3",  # or other dependencies
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.basedpyright]
include = ["src"]
typeCheckingMode = "standard"
pythonVersion = "3.13"
```

Install dependencies using `uv`:
```bash
uv sync
```

## 2. Package Structure and __init__.py Files

Each subdirectory should include an `__init__.py` file to make them proper Python packages. This enables clean imports and re-exports:

```python
# src/objects/__init__.py
from .action_object import CustomerActionObject
from .process_object import CustomerProcessObject

__all__ = ["CustomerActionObject", "CustomerProcessObject"]
```

```python
# src/retrievers/__init__.py
from .customer_csv_retriever import CustomerCsvRetriever, CustomerCsvRetrieverConfig

__all__ = ["CustomerCsvRetriever", "CustomerCsvRetrieverConfig"]
```

Similar patterns apply to `actions/`, `hydrators/`, and `processors/` directories.

## 3. Data Objects

Retrievers populate `normalized_data` on the process object, processors add
derived facts to the `artifacts` map, and the action object collects structured
decisions that downstream actions can evaluate.

```python
# src/objects/process_object.py
from mi.core.objects import ProcessDataObject


class CustomerProcessObject(ProcessDataObject):
    def customers(self) -> list[dict[str, str]]:
        return self.normalized_data["customers"]

    def active_customer_count(self) -> int:
        return self.artifacts.get("metrics.active_customer_count", 0)
```

```python
# src/objects/action_object.py
from mi.core.objects import ActionDataObject


class CustomerActionObject(ActionDataObject):
    @property
    def summary(self) -> dict[str, int]:
        return self.get_decision("summary")
```

**Important:** `get_decision()` takes only one argument (the decision key). If the decision doesn't exist, it will raise a `KeyError`. Always ensure decisions are set before accessing them.

## 4. Retriever

Retrievers (and their paired retrieve hydrators) are the only components that
should normalize raw data into `CustomerProcessObject.normalized_data`.

**Critical:** You must set `config.name` and `config.scope` **before** calling `super().__init__(config)`. The framework uses these values to structure the returned data:

- `config.name` represents the **retriever type identifier** (e.g., "csv", "api", "database") - this becomes an attribute on `RetrieverDataObject`
- `config.scope` represents the **dataset key** within that retriever type (e.g., "default", "customers", "orders")

The framework automatically structures the return value from `retrieve()` as `{name: {scope: data}}` based on these config values.

```python
# src/retrievers/customer_csv_retriever.py
from pathlib import Path
import pandas as pd
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig


class CustomerCsvRetrieverConfig(BaseRetrieverConfig):
    file_path: str
    dataset_name: str = "default"


class CustomerCsvRetriever(BaseRetriever):
    def __init__(self, config: CustomerCsvRetrieverConfig) -> None:
        # Set name and scope BEFORE calling super().__init__()
        config.name = "csv"  # Retriever type identifier
        config.scope = "default"  # Dataset key within the csv type
        super().__init__(config)
        self.csv_path = Path(config.file_path)
        self.dataset_name = config.dataset_name

    def retrieve(self) -> pd.DataFrame:
        # Can return DataFrame directly - framework structures it automatically
        df = pd.read_csv(self.csv_path)
        # Framework automatically structures as: {name: {scope: data}}
        # In this case: {"csv": {"default": df}}
        return df
```

**Note:** The `retrieve()` method can return data directly (DataFrame, list, dict, etc.). The framework handles structuring it based on `config.name` and `config.scope`. You don't need to manually wrap the return value in a nested dictionary.

## 5. Hydrators

Hydrators convert data between pipeline stages. When accessing data from `RetrieverDataObject`, use **attribute access** (`source.{name}[{scope}]`) or **dictionary access** (`source["{name}"]["{scope}"]`).

**Access Pattern:** If a retriever sets `config.name = "csv"` and `config.scope = "default"`, access the data using:
- Attribute syntax: `source.csv["default"]`
- Dictionary syntax: `source["csv"]["default"]`

Both patterns are equivalent. The framework structures the data as `{name: {scope: data}}` automatically.

```python
# src/hydrators/retrieve_to_process_hydrator.py
from mi.core.hydrators import BaseHydrator
from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt
from objects.process_object import CustomerProcessObject  # Relative import from src/


class RetrieveToProcessHydrator(BaseHydrator[RetrieverDataObject, CustomerProcessObject]):
    def hydrate(self, source: RetrieverDataObject, receipt: PipelineReceipt) -> CustomerProcessObject:
        target = CustomerProcessObject()
        
        # Access using attribute syntax (preferred)
        try:
            df = source.csv["default"]  # If retriever set config.name="csv" and config.scope="default"
            target.normalized_data["customers"] = df
        except KeyError:
            # Or use dictionary access syntax
            df = source["csv"]["default"]
            target.normalized_data["customers"] = df
        
        if receipt.retrieve_receipt:
            receipt.retrieve_receipt.set_metadata("datasets", ["customers"])
        return target
```

**Import Patterns:** When files are in `src/`, you can use relative imports:
```python
from objects.process_object import CustomerProcessObject
from hydrators.retrieve_to_process_hydrator import RetrieveToProcessHydrator
```

Or use package imports if your project is installed:
```python
from my_project.objects.process_object import CustomerProcessObject
from my_project.hydrators.retrieve_to_process_hydrator import RetrieveToProcessHydrator
```

```python
# src/hydrators/process_to_action_hydrator.py
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from objects.process_object import CustomerProcessObject
from objects.action_object import CustomerActionObject


class ProcessToActionHydrator(BaseHydrator[CustomerProcessObject, CustomerActionObject]):
    def hydrate(self, source: CustomerProcessObject, receipt: PipelineReceipt) -> CustomerActionObject:
        target = CustomerActionObject()
        target.set_decision(
            "summary",
            {
                "active_customers": source.artifacts["metrics.active_customer_count"],
                "total_customers": len(source.customers()),
            },
        )
        return target
```

```python
# src/hydrators/finalize_action_hydrator.py
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from objects.action_object import CustomerActionObject


class FinalizeActionHydrator(BaseHydrator[CustomerActionObject, None]):
    def hydrate(self, source: CustomerActionObject, receipt: PipelineReceipt) -> None:
        if receipt.act_receipt:
            receipt.act_receipt.set_metadata("email_subject", source.summary["subject"])
```

## 6. Processor

Processors read from normalized datasets, compute metrics, and store them as
artifacts for later hydrators or actions.

```python
# src/processors/customer_metrics_processor.py
from mi.core.processors import BaseProcessor
from objects.process_object import CustomerProcessObject


class CustomerMetricsProcessor(BaseProcessor[CustomerProcessObject]):
    def process(self, data_object: CustomerProcessObject) -> None:
        customers = data_object.customers()
        active_count = sum(1 for row in customers if row.get("active"))
        data_object.set_artifact("metrics.active_customer_count", active_count)
```

## 7. Action

Actions consult the decisions populated on `CustomerActionObject` to trigger
side effects.

```python
# src/actions/publish_summary_action.py
from mi.core.actions import BaseAction, BaseActionConfig
from objects.action_object import CustomerActionObject


class PublishSummaryAction(BaseAction[CustomerActionObject]):
    def __init__(self) -> None:
        super().__init__(config=BaseActionConfig(name="summary", scope="analytics").model_dump())

    def act(self, data_object: CustomerActionObject) -> None:
        summary = data_object.summary
        self.logger.info(
            "Emailing KPI summary (active: %s / total: %s)",
            summary["active_customers"],
            summary["total_customers"],
        )
```

## 8. Wire Everything Together

```python
# src/example_pipeline.py
from pathlib import Path
from mi.core import PipelineConfig
from mi.core.pipeline_builder import PipelineBuilder
from objects.process_object import CustomerProcessObject
from objects.action_object import CustomerActionObject
from retrievers.customer_csv_retriever import (
    CustomerCsvRetriever,
    CustomerCsvRetrieverConfig,
)
from hydrators.retrieve_to_process_hydrator import RetrieveToProcessHydrator
from hydrators.process_to_action_hydrator import ProcessToActionHydrator
from hydrators.finalize_action_hydrator import FinalizeActionHydrator
from processors.customer_metrics_processor import CustomerMetricsProcessor
from actions.publish_summary_action import PublishSummaryAction

csv_file = Path("data/customers.csv").resolve()

pipeline = (
    PipelineBuilder()
    .with_config(PipelineConfig(name="customer_insights"))
    .with_objects(CustomerProcessObject, CustomerActionObject)
    .add_retriever(
        CustomerCsvRetriever(CustomerCsvRetrieverConfig(file_path=str(csv_file), dataset_name="default"))
    )
    .with_retrieve_hydrator(RetrieveToProcessHydrator())
    .add_processor(CustomerMetricsProcessor())
    .with_process_hydrator(ProcessToActionHydrator())
    .add_action(PublishSummaryAction())
    .with_action_hydrator(FinalizeActionHydrator())
    .build()
)

receipt = pipeline.run()
print(receipt.success)
print(receipt.process_receipt.metadata)
```

Run the pipeline:
```bash
uv run python src/example_pipeline.py
```

## 9. YAML-driven assembly

You can describe the exact same pipeline declaratively and load it with
`PipelineBuilder.from_yaml`. The YAML references component class names exactly
as they appear in your registry (no module prefixes). 

**Directory Structure:** Save YAML pipeline files in a `pipelines/` directory at the project root:

```
my_project/
├── pipelines/
│   └── customer_insights.ppln
```

Save the following as `pipelines/customer_insights.ppln`:

```yaml
name: customer_insights
version: 1.0.0

retrieve:
  hydrator: RetrieveToProcessHydrator
  retrievers:
    - retriever: CustomerCsvRetriever
      file_path: data/customers.csv
      dataset_name: default

process:
  hydrator: ProcessToActionHydrator
  processors:
    - processor: CustomerMetricsProcessor

action:
  hydrator: FinalizeActionHydrator
  actions:
    - action: PublishSummaryAction
```

**Important:** Class names in YAML must match registry entries exactly. The registry is built from your project's component classes.

Then bootstrap the pipeline with:

```python
# src/run_from_yaml.py
from mi.core.pipeline_builder import PipelineBuilder

builder = PipelineBuilder.from_yaml("pipelines/customer_insights.ppln")
pipeline = builder.build()
receipt = pipeline.run()
print(f"Pipeline success: {receipt.success}")
```

Run from YAML:
```bash
uv run python src/run_from_yaml.py
```

Or use the CLI:
```bash
mi run pipelines/customer_insights.ppln
```

## 10. Development Workflow

### Common Commands

```bash
# Install dependencies
uv sync

# Type check
uv run basedpyright

# Run pipeline script
uv run python src/example_pipeline.py

# Run from YAML
uv run python src/run_from_yaml.py

# Or use the CLI
mi run pipelines/customer_insights.ppln
```

### Project Setup Checklist

1. ✅ Create `pyproject.toml` with project metadata and dependencies
2. ✅ Set up `src/` directory structure with component subdirectories
3. ✅ Add `__init__.py` files to each subdirectory
4. ✅ Create `pipelines/` directory for YAML configuration files
5. ✅ Set `config.name` and `config.scope` in retriever `__init__` before `super().__init__()`
6. ✅ Use attribute or dictionary access for `RetrieverDataObject` in hydrators
7. ✅ Ensure `get_decision()` is called with only one argument (the key)

This setup mirrors the structure referenced in the docstrings and provides a
cohesive template to start building your own pipeline components. Adapt the file
paths, dataset names, and business logic to match your scenario (and update the
YAML to match your registry configuration).

## 11. Inspect receipts and logs

`Pipeline.run()` returns a `PipelineReceipt` that captures config snapshots,
stage timing, and any recorded errors or metadata. Use it to debug or surface
telemetry in your own tools.

```python
receipt = pipeline.run()
print(receipt.success)
print(receipt.get_config("name"))               # pipeline name

if receipt.retrieve_receipt:
    print(receipt.retrieve_receipt.execution_time_seconds)
    print(receipt.retrieve_receipt.metadata.get("retriever_name"))

if not receipt.success:
    # correlate with logs written to .insights/logs/<pipeline>.log
    print(receipt.get_stage_receipt("process") and receipt.process_receipt.error)
```

To run the same builder over many units in parallel, wire a `PipelineOrchestrator`
with a builder and an adapter that maps each item to `PipelineConfig`. Each run
returns its own `PipelineReceipt`, keyed by the original item.

---

## See Also

- [Architecture](architecture.md) — high-level design and data flow concepts
- [Pipeline Builder](pipeline-builder.md) — full API reference for the fluent builder
- [YAML Configuration](yaml-configuration.md) — declarative pipeline definitions in detail
- [CLI](cli.md) — command-line tools for running pipelines and managing the registry
