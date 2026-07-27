# Processors

Processors transform and analyze data, computing metrics and derived values that are stored as artifacts.

## Overview

Processors are responsible for:
- Reading from `normalized_data` on the ProcessDataObject
- Computing metrics, aggregations, and transformations
- Storing results in `artifacts` for downstream use
- Mutating the data object **in place** (no return value)

## Creating a Processor

### Basic Structure

```python
from mi.core.processors import BaseProcessor, BaseProcessorConfig
from my_project.objects import MyProcessObject

class MyProcessorConfig(BaseProcessorConfig):
    # Add configuration fields
    threshold: float = 0.5

class MyProcessor(BaseProcessor[MyProcessObject]):
    def __init__(self, config: MyProcessorConfig | None = None) -> None:
        super().__init__(config)
        self.threshold = config.threshold if config else 0.5

    def process(self, data_object: MyProcessObject, *, metadata=None) -> None:
        """Process the data object in place.

        Args:
            data_object: The ProcessDataObject to transform
            metadata: Optional pipeline metadata
        """
        # Read data
        records = data_object.normalized_data["records"]

        # Compute metrics
        total = len(records)
        above_threshold = sum(1 for r in records if r["value"] > self.threshold)

        # Store as artifacts
        data_object.set_artifact("metrics.total", total)
        data_object.set_artifact("metrics.above_threshold", above_threshold)

        self.logger.info(f"Processed {total} records, {above_threshold} above threshold")
```

### Key Points

1. **In-place mutation** - `process()` returns `None`; modify `data_object` directly
2. **Generic typing** - `BaseProcessor[MyProcessObject]` provides type safety
3. **Artifacts** - Use `set_artifact()` to store computed values
4. **Logging** - Use `self.logger` for observability

## Working with Data

### Reading from normalized_data

```python
def process(self, data_object, *, metadata=None):
    # Access datasets
    customers = data_object.normalized_data["customers"]
    orders = data_object.normalized_data.get("orders", [])

    # If using a typed ProcessDataObject with properties
    customers = data_object.customers  # Using @property
```

### Writing to artifacts

```python
def process(self, data_object, *, metadata=None):
    # Single values
    data_object.set_artifact("total_count", 100)
    data_object.set_artifact("average_value", 45.5)

    # Nested structures
    data_object.set_artifact("metrics.summary", {
        "total": 100,
        "average": 45.5,
        "max": 99.0
    })

    # Lists
    data_object.set_artifact("top_customers", ["A", "B", "C"])
```

### Using typed data objects

```python
class CustomerMetricsProcessor(BaseProcessor[CustomerProcessObject]):
    def process(self, data_object: CustomerProcessObject, *, metadata=None) -> None:
        # Use typed property accessors
        customers = data_object.customers  # Returns list[dict]

        # Compute
        active_count = sum(1 for c in customers if c.get("active"))

        # Use typed setter
        data_object.active_count = active_count  # Uses @property setter
```

## Using Pipeline Metadata

Access metadata for context-aware processing:

```python
def process(self, data_object, *, metadata=None):
    if metadata:
        unit = metadata.unit  # e.g., tenant_id, device_id
        self.logger.info(f"Processing for unit: {unit}")

        # Filter or contextualize processing
        data_object.set_artifact("processed_unit", unit)
```

## Validation Hooks

Processors can implement validation methods:

```python
class ValidatingProcessor(BaseProcessor[MyProcessObject]):
    def validate_prerequisites(self, data_object):
        """Called BEFORE process(). Raise if prerequisites not met."""
        if "required_dataset" not in data_object.normalized_data:
            raise ValueError("Missing required dataset")

    def process(self, data_object, *, metadata=None):
        # Main processing logic
        pass

    def validate_output(self, data_object):
        """Called AFTER process(). Validate results."""
        if data_object.get_artifact("required_metric") is None:
            raise ValueError("Processing did not produce required metric")
```

## Multiple Processors

Pipelines can chain multiple processors:

```python
pipeline = (
    PipelineBuilder()
    # ... retrievers and hydrators ...
    .add_processor(DataCleaningProcessor())
    .add_processor(MetricsProcessor())
    .add_processor(AnomalyDetectionProcessor())
    # ...
)
```

Processors run in order, each receiving the same `ProcessDataObject` with accumulated artifacts.

## Examples

### Aggregation Processor

```python
class SalesAggregationProcessor(BaseProcessor[SalesProcessObject]):
    def process(self, data_object, *, metadata=None):
        sales = data_object.normalized_data["sales"]

        # Compute aggregations
        total_revenue = sum(s["amount"] for s in sales)
        avg_order_value = total_revenue / len(sales) if sales else 0
        by_region = {}
        for sale in sales:
            region = sale.get("region", "unknown")
            by_region[region] = by_region.get(region, 0) + sale["amount"]

        # Store artifacts
        data_object.set_artifact("revenue.total", total_revenue)
        data_object.set_artifact("revenue.average_order", avg_order_value)
        data_object.set_artifact("revenue.by_region", by_region)
```

### Filtering Processor

```python
class ActiveCustomerProcessor(BaseProcessor[CustomerProcessObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.days_threshold = 30

    def process(self, data_object, *, metadata=None):
        customers = data_object.normalized_data["customers"]

        # Filter to active customers
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=self.days_threshold)

        active = [c for c in customers if c.get("last_active") > cutoff]
        inactive = [c for c in customers if c.get("last_active") <= cutoff]

        # Store filtered lists
        data_object.normalized_data["active_customers"] = active
        data_object.set_artifact("inactive_count", len(inactive))
```

### ML Scoring Processor

```python
class ScoringProcessor(BaseProcessor[LeadProcessObject]):
    def __init__(self, config=None):
        super().__init__(config)
        self.model = load_model("lead_scoring_model.pkl")

    def process(self, data_object, *, metadata=None):
        leads = data_object.normalized_data["leads"]

        # Score each lead
        for lead in leads:
            features = extract_features(lead)
            lead["score"] = self.model.predict_proba(features)[0][1]

        # Categorize
        high_value = [l for l in leads if l["score"] > 0.8]

        data_object.set_artifact("high_value_leads", high_value)
        data_object.set_artifact("lead_count", len(leads))
```

## Best Practices

1. **Single responsibility** - Each processor should do one thing well
2. **Use artifacts** - Store computed values for downstream components
3. **Type your data objects** - Use generics for type safety
4. **Log important steps** - Help with debugging and monitoring
5. **Validate inputs** - Use `validate_prerequisites()` for defensive coding
6. **Keep processors pure** - No side effects; save those for Actions

---

## See Also

- [Hydrators](hydrators.md) — how processor output is converted to action data objects
- [Data Objects](data-objects.md) — the `ProcessDataObject` that processors operate on
- [AI Integration](../ai.md) — AI-powered processors using LLM workflows and agents
