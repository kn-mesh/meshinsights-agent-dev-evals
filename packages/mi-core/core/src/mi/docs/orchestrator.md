# Pipeline Orchestrator

The `PipelineOrchestrator` runs pipelines at scale, processing multiple items in parallel using threads or processes.

## Overview

```python
from mi.core import PipelineOrchestrator, OrchestratorConfig, PipelineConfig

orchestrator = PipelineOrchestrator(
    builder=pipeline_builder,
    adapter=lambda item: PipelineConfig(name=f"pipeline_{item}"),
    config=OrchestratorConfig(
        runtime="threaded",
        max_workers=4,
    ),
)

# Run for multiple items
receipts = orchestrator.run(["item1", "item2", "item3"])
```

## Configuration

### OrchestratorConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | "pipeline_orchestrator" | Orchestrator identifier |
| `runtime` | str | "serial" | Execution mode: "serial", "threaded", "process" |
| `error_action` | str | "stop" | "stop" or "continue" on errors |
| `max_workers` | int | 1 | Number of parallel workers |

### Runtime Modes

#### Serial

Runs items one at a time. Best for debugging.

```python
config = OrchestratorConfig(
    runtime="serial",
)
```

#### Threaded

Uses `ThreadPoolExecutor`. Best for I/O-bound workloads.

```python
config = OrchestratorConfig(
    runtime="threaded",
    max_workers=4,
)
```

#### Process

Uses `ProcessPoolExecutor`. Best for CPU-bound workloads.

```python
config = OrchestratorConfig(
    runtime="process",
    max_workers=4,
)
```

**Note:** Process mode requires all components to be picklable.

## Creating an Orchestrator

### Components

1. **Builder** - A `PipelineBuilder` configured with all components
2. **Adapter** - A function that converts each item to a `PipelineConfig`
3. **Config** - An `OrchestratorConfig` for execution settings

```python
from mi.core import PipelineBuilder, PipelineOrchestrator, OrchestratorConfig, PipelineConfig

# Create the builder (reused for all items)
builder = (
    PipelineBuilder()
    .add_retriever(MyRetriever(config))
    .with_retrieve_hydrator(MyRetrieveHydrator())
    .add_processor(MyProcessor())
    .with_process_hydrator(MyProcessHydrator())
    .add_action(MyAction())
    .with_action_hydrator(MyActionHydrator())
)

# Adapter converts each item to a PipelineConfig
def adapter(item):
    return PipelineConfig(
        name=f"pipeline_{item}",
        # Can customize config per item
    )

# Create orchestrator
orchestrator = PipelineOrchestrator(
    builder=builder,
    adapter=adapter,
    config=OrchestratorConfig(
        runtime="threaded",
        max_workers=4,
    ),
)
```

## Running the Orchestrator

### Basic Usage

```python
items = ["tenant_1", "tenant_2", "tenant_3"]
receipts = orchestrator.run(items)

for item, receipt in receipts.items():
    status = "OK" if receipt.success else "FAILED"
    print(f"{item}: {status}")
```

### With Different Item Types

Items can be any type—the adapter converts them:

```python
# Items as dictionaries
items = [
    {"tenant_id": "t1", "date": "2024-01-01"},
    {"tenant_id": "t2", "date": "2024-01-01"},
]

def adapter(item):
    return PipelineConfig(
        name=f"pipeline_{item['tenant_id']}_{item['date']}",
    )
```

### With PipelineMetadata

The adapter can also create metadata that flows through the pipeline:

```python
from mi.core import PipelineMetadata

# Create orchestrator with metadata support
orchestrator = PipelineOrchestrator(
    builder=builder,
    adapter=lambda item: PipelineConfig(name=f"pipeline_{item}"),
    config=config,
)

# Each item becomes metadata.unit by default
receipts = orchestrator.run(items)
```

## Error Handling

### Stop on Error

Default behavior—stops processing on first failure:

```python
config = OrchestratorConfig(
    runtime="threaded",
    max_workers=4,
    error_action="stop",
)
```

### Continue on Error

Process all items, collecting failures:

```python
config = OrchestratorConfig(
    runtime="threaded",
    max_workers=4,
    error_action="continue",
)

receipts = orchestrator.run(items)

# Check for failures
failed = {item: r for item, r in receipts.items() if not r.success}
if failed:
    print(f"{len(failed)} items failed")
    for item, receipt in failed.items():
        print(f"  {item}: {receipt.process_receipt.error}")
```

## Parallel Execution Details

### Thread Safety

Each worker receives a **deep copy** of the builder, ensuring:
- No shared mutable state between workers
- Thread-safe by construction
- Independent pipeline instances

### Process Isolation

In process mode:
- Each worker runs in a separate Python process
- All components must be picklable (serializable)
- True parallelism (bypasses GIL)

### Worker Count Guidelines

| Workload Type | Recommended Workers |
|---------------|---------------------|
| I/O bound (API calls, file reads) | 2-4x CPU cores |
| CPU bound (data processing) | CPU cores |
| Mixed | CPU cores + 1-2 |

## Using with Thread-Unsafe Libraries

Some libraries aren't thread-safe. Use the `RootExecutor` utility:

```python
from mi.utilities import root_executor, bound

# Initialize before running orchestrator
root_executor.initialize()

class MyProcessor(BaseProcessor):
    @bound  # Executes on main thread
    def unsafe_operation(self, data):
        return thread_unsafe_library.process(data)

    def process(self, data_object, *, metadata=None):
        result = self.unsafe_operation(data_object.data)
        data_object.set_artifact("result", result)

# Run orchestrator
receipts = orchestrator.run(items)

# Cleanup
root_executor.shutdown()
```

See [Utilities](utilities.md) for more on `RootExecutor`.

## Complete Example

```python
from mi.core import (
    PipelineBuilder,
    PipelineOrchestrator,
    OrchestratorConfig,
    PipelineConfig,
)
from my_project.components import (
    CustomerRetriever,
    CustomerRetrieverConfig,
    MetricsProcessor,
    SaveAction,
    RetrieveHydrator,
    ProcessHydrator,
    ActionHydrator,
)

# Build the pipeline template
builder = (
    PipelineBuilder()
    .add_retriever(CustomerRetriever(CustomerRetrieverConfig(
        file_path="data/customers.csv"
    )))
    .with_retrieve_hydrator(RetrieveHydrator())
    .add_processor(MetricsProcessor())
    .with_process_hydrator(ProcessHydrator())
    .add_action(SaveAction())
    .with_action_hydrator(ActionHydrator())
)

# Create orchestrator
orchestrator = PipelineOrchestrator(
    builder=builder,
    adapter=lambda tenant: PipelineConfig(name=f"customer_pipeline_{tenant}"),
    config=OrchestratorConfig(
        name="customer_orchestrator",
        runtime="threaded",
        max_workers=4,
        error_action="continue",
    ),
)

# Process all tenants
tenants = ["acme", "globex", "initech", "umbrella"]
receipts = orchestrator.run(tenants)

# Summarize results
successful = sum(1 for r in receipts.values() if r.success)
failed = len(receipts) - successful

print(f"Processed {len(receipts)} tenants: {successful} OK, {failed} failed")

# Log failures
for tenant, receipt in receipts.items():
    if not receipt.success:
        error = receipt.process_receipt.error if receipt.process_receipt else "Unknown"
        print(f"  {tenant}: {error}")
```

## Best Practices

1. **Choose the right runtime** - Threaded for I/O, process for CPU
2. **Handle errors** - Use "continue" mode for batch processing
3. **Monitor results** - Check all receipts for failures
4. **Tune workers** - Start with CPU count, adjust based on workload
5. **Use RootExecutor** - For thread-unsafe libraries
6. **Keep builders stateless** - Builders are copied per worker

---

## See Also

- [Pipeline Builder](pipeline-builder.md) — building the pipeline that the orchestrator runs
- [Utilities](utilities.md) — RootExecutor and caching for thread-safe parallel execution
- [Architecture](architecture.md) — pipeline execution model and stage lifecycle
