# Hydrators

Hydrators convert data between pipeline stages, transforming one data object type into another.

## Overview

Every pipeline requires three hydrators:

| Hydrator | Conversion | Purpose |
|----------|------------|---------|
| Retrieve Hydrator | `RetrieverDataObject` → `ProcessDataObject` | Extract raw data into normalized format |
| Process Hydrator | `ProcessDataObject` → `ActionDataObject` | Convert artifacts into decisions |
| Action Hydrator | `ActionDataObject` → `None` | Final cleanup and logging |

## Creating Hydrators

### Retrieve Hydrator

Converts raw retriever output into a structured ProcessDataObject.

```python
from mi.core.hydrators import BaseHydrator
from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt
from my_project.objects import MyProcessObject

class RetrieveToProcessHydrator(BaseHydrator[RetrieverDataObject, MyProcessObject]):
    def hydrate(
        self,
        source: RetrieverDataObject,
        receipt: PipelineReceipt,
    ) -> MyProcessObject:
        """Convert RetrieverDataObject to ProcessDataObject.

        Args:
            source: The retriever output containing raw data
            receipt: Pipeline receipt for metadata tracking

        Returns:
            A new ProcessDataObject with normalized data
        """
        target = MyProcessObject()

        # Access retriever data using attribute syntax
        # source.{name}["{scope}"] where name/scope come from retriever config
        customers_df = source.csv["default"]

        # Normalize into the process object
        target.normalized_data["customers"] = customers_df.to_dict("records")

        # Track metadata in receipt
        if receipt.retrieve_receipt:
            receipt.retrieve_receipt.set_metadata("record_count", len(customers_df))

        self.logger.debug(f"Hydrated {len(customers_df)} customer records")
        return target
```

### Accessing Retriever Data

Data in `RetrieverDataObject` is keyed by the retriever's `config.name` and `config.scope`:

```python
# If retriever had config.name = "csv" and config.scope = "customers"
df = source.csv["customers"]

# If retriever had config.name = "api" and config.scope = "orders"
orders = source.api["orders"]

# Dictionary syntax also works
df = source["csv"]["customers"]
```

### Process Hydrator

Converts ProcessDataObject (with artifacts) into ActionDataObject (with decisions).

```python
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from my_project.objects import MyProcessObject, MyActionObject

class ProcessToActionHydrator(BaseHydrator[MyProcessObject, MyActionObject]):
    def hydrate(
        self,
        source: MyProcessObject,
        receipt: PipelineReceipt,
    ) -> MyActionObject:
        """Convert ProcessDataObject to ActionDataObject.

        Args:
            source: The processed data with artifacts
            receipt: Pipeline receipt for metadata tracking

        Returns:
            A new ActionDataObject with decisions
        """
        target = MyActionObject()

        # Read artifacts from processor
        total = source.get_artifact("metrics.total", 0)
        active = source.get_artifact("metrics.active", 0)

        # Create decisions for actions
        target.set_decision("summary", {
            "total_customers": total,
            "active_customers": active,
            "activity_rate": active / total if total > 0 else 0
        })

        # Decide what actions should do
        if active / total < 0.5 if total > 0 else False:
            target.set_decision("alert", {
                "type": "low_activity",
                "message": f"Only {active}/{total} customers active"
            })

        return target
```

### Action Hydrator

Performs final cleanup after actions complete. Returns `None`.

```python
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from my_project.objects import MyActionObject

class FinalizeActionHydrator(BaseHydrator[MyActionObject, None]):
    def hydrate(
        self,
        source: MyActionObject,
        receipt: PipelineReceipt,
    ) -> None:
        """Finalize the pipeline after actions complete.

        Args:
            source: The action data object with decisions
            receipt: Pipeline receipt for final metadata
        """
        # Log final summary
        summary = source.get_decision("summary")
        self.logger.info(f"Pipeline complete: {summary}")

        # Record final metadata
        if receipt.act_receipt:
            receipt.act_receipt.set_metadata("finalized", True)
            receipt.act_receipt.set_metadata("summary", summary)

        # No return value for action hydrator
```

## Working with Receipts

Hydrators receive the pipeline receipt and can add metadata:

```python
def hydrate(self, source, receipt):
    # Add metadata to the appropriate stage receipt
    if receipt.retrieve_receipt:
        receipt.retrieve_receipt.set_metadata("key", "value")

    if receipt.process_receipt:
        receipt.process_receipt.set_metadata("artifacts_count", 5)

    if receipt.act_receipt:
        receipt.act_receipt.set_metadata("actions_executed", 3)
```

## Combining Multiple Retrievers

When a pipeline has multiple retrievers, combine their data in the retrieve hydrator:

```python
class MultiSourceHydrator(BaseHydrator[RetrieverDataObject, MyProcessObject]):
    def hydrate(self, source, receipt):
        target = MyProcessObject()

        # Combine data from different retrievers
        customers = source.csv["customers"]
        orders = source.api["orders"]
        inventory = source.database["inventory"]

        # Join or merge as needed
        customer_orders = merge_customer_orders(customers, orders)

        target.normalized_data["customers"] = customers.to_dict("records")
        target.normalized_data["orders"] = orders
        target.normalized_data["customer_orders"] = customer_orders

        return target
```

## Error Handling

Handle missing or malformed data gracefully:

```python
class SafeHydrator(BaseHydrator[RetrieverDataObject, MyProcessObject]):
    def hydrate(self, source, receipt):
        target = MyProcessObject()

        # Check for required data
        try:
            customers = source.csv["customers"]
        except KeyError:
            self.logger.error("Missing customers data from CSV retriever")
            raise ValueError("Required data 'csv.customers' not found")

        # Handle optional data
        try:
            metadata = source.api["metadata"]
        except KeyError:
            self.logger.warning("No metadata available, using defaults")
            metadata = {}

        target.normalized_data["customers"] = customers.to_dict("records")
        target.normalized_data["metadata"] = metadata

        return target
```

## Type Safety with Generics

The `BaseHydrator[Source, Target]` generic provides type checking:

```python
# Type-safe hydrator definition
class MyHydrator(BaseHydrator[MyProcessObject, MyActionObject]):
    def hydrate(
        self,
        source: MyProcessObject,    # Typed source
        receipt: PipelineReceipt,
    ) -> MyActionObject:            # Typed return
        target = MyActionObject()
        # IDE knows source has MyProcessObject methods
        # IDE knows target needs MyActionObject methods
        return target
```

## Best Practices

1. **Single responsibility** - Each hydrator handles one conversion
2. **Validate data** - Check for required fields before converting
3. **Use logging** - Track what data is being transformed
4. **Add metadata** - Record useful info in the pipeline receipt
5. **Handle errors** - Gracefully handle missing or malformed data
6. **Type your generics** - Use proper type hints for IDE support

---

## See Also

- [Data Objects](data-objects.md) — the typed containers that hydrators convert between
- [Retrievers](retrievers.md) — the source data that retrieve hydrators consume
- [Processors](processors.md) — the processors that run between retrieve and process hydrators
- [Actions](actions.md) — the actions that consume action data objects from process hydrators
