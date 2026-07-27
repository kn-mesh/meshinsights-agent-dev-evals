# Pipeline Builder

The `PipelineBuilder` provides a fluent API for constructing pipelines with type safety and validation.

## Overview

```python
from mi.core import PipelineBuilder, PipelineConfig

pipeline = (
    PipelineBuilder()
    .with_config(PipelineConfig(name="my_pipeline"))
    .add_retriever(MyRetriever(config))
    .with_retrieve_hydrator(RetrieveHydrator())
    .add_processor(MyProcessor())
    .with_process_hydrator(ProcessHydrator())
    .add_action(MyAction())
    .with_action_hydrator(ActionHydrator())
    .build()
)

receipt = pipeline.run()
```

## Builder Methods

### Configuration

#### with_config()

Set the pipeline configuration:

```python
from mi.core import PipelineConfig

builder.with_config(PipelineConfig(
    name="customer_pipeline",
    version="1.0.0",
    log_level="INFO",
    error_action="stop",  # or "continue"
))
```

**PipelineConfig fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | "pipeline" | Pipeline identifier for logging |
| `version` | str | "1.0.0" | Pipeline version |
| `log_level` | str | "INFO" | Logging level |
| `error_action` | str | "stop" | "stop" or "continue" on errors |

#### with_objects()

Specify data object types for type inference (optional):

```python
from my_project.objects import MyProcessObject, MyActionObject

builder.with_objects(MyProcessObject, MyActionObject)
```

This is for IDE type inference only—the objects aren't actually used.

### Retrievers

#### add_retriever()

Add a retriever to the pipeline:

```python
builder.add_retriever(CsvRetriever(CsvRetrieverConfig(
    file_path="data/input.csv",
    name="csv",
    scope="default"
)))
```

Multiple retrievers can be added:

```python
builder
    .add_retriever(CsvRetriever(csv_config))
    .add_retriever(ApiRetriever(api_config))
    .add_retriever(DatabaseRetriever(db_config))
```

### Hydrators

#### with_retrieve_hydrator()

Set the hydrator that converts `RetrieverDataObject` → `ProcessDataObject`:

```python
builder.with_retrieve_hydrator(RetrieveToProcessHydrator())
```

#### with_process_hydrator()

Set the hydrator that converts `ProcessDataObject` → `ActionDataObject`:

```python
builder.with_process_hydrator(ProcessToActionHydrator())
```

#### with_action_hydrator()

Set the hydrator that finalizes after actions (returns `None`):

```python
builder.with_action_hydrator(FinalizeHydrator())
```

### Processors

#### add_processor()

Add a processor to the pipeline:

```python
builder.add_processor(MetricsProcessor())
```

Multiple processors run in sequence:

```python
builder
    .add_processor(DataCleaningProcessor())
    .add_processor(MetricsProcessor())
    .add_processor(AnomalyDetectionProcessor())
```

### Actions

#### add_action()

Add an action to the pipeline:

```python
builder.add_action(DatabaseSaveAction())
```

Multiple actions run in sequence:

```python
builder
    .add_action(DatabaseSaveAction())
    .add_action(NotificationAction())
    .add_action(WebhookAction())
```

### Building

#### build()

Compile the pipeline configuration and return a runnable `Pipeline`:

```python
pipeline = builder.build()
```

The builder validates that all required components are present.

## Type-Safe Building

### Using Generics

```python
from mi.core import PipelineBuilder
from my_project.objects import MyProcessObject, MyActionObject

# Specify types via generics
pipeline = (
    PipelineBuilder[MyProcessObject, MyActionObject]()
    .add_retriever(...)
    .with_retrieve_hydrator(...)
    # IDE knows the expected types for each method
    .build()
)
```

### Using with_objects()

```python
# Alternative: specify types via method
pipeline = (
    PipelineBuilder()
    .with_objects(MyProcessObject, MyActionObject)
    # Same effect as generics
    .build()
)
```

## Loading from YAML

### from_yaml()

Load a pipeline definition from a YAML file:

```python
builder = PipelineBuilder.from_yaml("pipelines/my_pipeline.ppln")
pipeline = builder.build()
```

See [YAML Configuration](yaml-configuration.md) for the YAML format.

### from_yaml_string()

Load from a YAML string:

```python
yaml_content = """
name: inline_pipeline
retrieve:
  hydrator: MyRetrieveHydrator
  retrievers:
    - retriever: CsvRetriever
      file_path: data/input.csv
"""

builder = PipelineBuilder.from_yaml_string(yaml_content)
```

## Running Pipelines

### Basic Execution

```python
pipeline = builder.build()
receipt = pipeline.run()

print(f"Success: {receipt.success}")
print(f"Duration: {receipt.total_execution_time_seconds:.2f}s")
```

### With Metadata

Pass metadata that flows through all stages:

```python
from mi.core import PipelineMetadata

metadata = PipelineMetadata(unit="tenant_123")
receipt = pipeline.run(metadata=metadata)
```

### Checking Results

```python
receipt = pipeline.run()

if receipt.success:
    print("Pipeline completed successfully")

    # Access stage receipts
    if receipt.retrieve_receipt:
        print(f"Retrieve time: {receipt.retrieve_receipt.execution_time_seconds}s")

    if receipt.process_receipt:
        artifacts = receipt.process_receipt.metadata
        print(f"Process metadata: {artifacts}")
else:
    # Check for errors
    if receipt.process_receipt and receipt.process_receipt.error:
        print(f"Process error: {receipt.process_receipt.error}")
```

## Complete Example

```python
from pathlib import Path
from mi.core import PipelineBuilder, PipelineConfig, PipelineMetadata

from my_project.retrievers import CustomerRetriever, CustomerRetrieverConfig
from my_project.processors import MetricsProcessor, AnomalyProcessor
from my_project.actions import SaveAction, AlertAction
from my_project.hydrators import (
    RetrieveHydrator,
    ProcessHydrator,
    ActionHydrator,
)
from my_project.objects import CustomerProcessObject, CustomerActionObject

# Configure
config = PipelineConfig(
    name="customer_analytics",
    version="2.0.0",
    error_action="continue",
)

retriever_config = CustomerRetrieverConfig(
    file_path="data/customers.csv",
    name="csv",
    scope="customers",
)

# Build
pipeline = (
    PipelineBuilder[CustomerProcessObject, CustomerActionObject]()
    .with_config(config)
    .add_retriever(CustomerRetriever(retriever_config))
    .with_retrieve_hydrator(RetrieveHydrator())
    .add_processor(MetricsProcessor())
    .add_processor(AnomalyProcessor())
    .with_process_hydrator(ProcessHydrator())
    .add_action(SaveAction())
    .add_action(AlertAction())
    .with_action_hydrator(ActionHydrator())
    .build()
)

# Run for multiple tenants
for tenant_id in ["tenant_1", "tenant_2", "tenant_3"]:
    metadata = PipelineMetadata(unit=tenant_id)
    receipt = pipeline.run(metadata=metadata)
    print(f"{tenant_id}: {'OK' if receipt.success else 'FAILED'}")
```

## Best Practices

1. **Use type parameters** - Either generics or `with_objects()` for type safety
2. **Set meaningful names** - Pipeline names appear in logs
3. **Order matters** - Processors and actions run in the order added
4. **Validate early** - `build()` validates the configuration
5. **Handle receipts** - Always check `receipt.success` after running

---

## See Also

- [YAML Configuration](yaml-configuration.md) — declarative alternative to the programmatic builder
- [Orchestrator](orchestrator.md) — running a builder across multiple items in parallel
- [Architecture](architecture.md) — how the pipeline stages connect
