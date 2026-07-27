# Data Objects

Data objects are type-safe containers that hold data as it flows through the pipeline stages.

## Overview

The framework provides three data object types, each serving a specific purpose:

| Object | Stage | Purpose |
|--------|-------|---------|
| `RetrieverDataObject` | Retrieve | Holds raw data from retrievers |
| `ProcessDataObject` | Process | Holds normalized data + computed artifacts |
| `ActionDataObject` | Act | Holds decisions for actions |

## RetrieverDataObject

Created automatically by the retrieve stage. Holds raw data keyed by retriever name and scope.

### Structure

```python
RetrieverDataObject:
    {retriever_name}:           # e.g., "csv", "api", "database"
        {scope}:                # e.g., "default", "customers", "orders"
            <data>              # DataFrame, dict, list, etc.
```

### Accessing Data

```python
# In a hydrator, access retriever data:
def hydrate(self, source: RetrieverDataObject, receipt):
    # Attribute access (preferred)
    df = source.csv["default"]

    # Dictionary access (alternative)
    df = source["csv"]["default"]
```

### How Data Is Structured

When a retriever returns data, the framework automatically structures it:

```python
class MyRetriever(BaseRetriever):
    def __init__(self, config):
        config.name = "csv"       # → source.csv
        config.scope = "default"  # → source.csv["default"]
        super().__init__(config)

    def retrieve(self):
        return pd.read_csv(...)   # Automatically stored at source.csv["default"]
```

## ProcessDataObject

Holds normalized datasets and computed artifacts. This is where processors do their work.

### Structure

```python
ProcessDataObject:
    correlation_id: str         # Unique ID for this pipeline run
    object_id: str              # Unique ID for this object instance
    normalized_data: dict       # Cleaned, structured datasets
    artifacts: dict             # Computed metrics and derived values
```

### Creating a Custom ProcessDataObject

```python
from mi.core.objects import ProcessDataObject

class CustomerProcessObject(ProcessDataObject):
    # Constants for type safety
    _DATASET_CUSTOMERS = "customers"
    _ARTIFACT_ACTIVE_COUNT = "active_count"

    @property
    def customers(self) -> list[dict]:
        """Access the customers dataset."""
        return self.normalized_data.get(self._DATASET_CUSTOMERS, [])

    @property
    def active_count(self) -> int:
        """Get the computed active customer count."""
        return self.get_artifact(self._ARTIFACT_ACTIVE_COUNT, 0)

    @active_count.setter
    def active_count(self, value: int) -> None:
        """Set the active customer count."""
        self.set_artifact(self._ARTIFACT_ACTIVE_COUNT, value)
```

### Working with normalized_data

```python
# In a hydrator (setting data)
target = CustomerProcessObject()
target.normalized_data["customers"] = df.to_dict("records")

# In a processor (reading data)
customers = data_object.normalized_data["customers"]
```

### Working with artifacts

```python
# Setting artifacts
data_object.set_artifact("metrics.total", 100)
data_object.set_artifact("metrics.active", 75)

# Getting artifacts
total = data_object.get_artifact("metrics.total")
active = data_object.get_artifact("metrics.active", default=0)

# Direct access
all_artifacts = data_object.artifacts
```

## ActionDataObject

Holds structured decisions that actions use to execute side effects.

### Structure

```python
ActionDataObject:
    correlation_id: str         # Inherited from pipeline run
    object_id: str              # Unique ID for this object
    decisions: dict             # Key-value decisions for actions
```

### Creating a Custom ActionDataObject

```python
from mi.core.objects import ActionDataObject

class CustomerActionObject(ActionDataObject):
    _DECISION_SUMMARY = "summary"
    _DECISION_ALERTS = "alerts"

    @property
    def summary(self) -> dict:
        """Get the summary decision."""
        return self.get_decision(self._DECISION_SUMMARY)

    @summary.setter
    def summary(self, value: dict) -> None:
        """Set the summary decision."""
        self.set_decision(self._DECISION_SUMMARY, value)

    @property
    def alerts(self) -> list:
        """Get the alerts to send."""
        return self.get_decision(self._DECISION_ALERTS)

    @alerts.setter
    def alerts(self, value: list) -> None:
        self.set_decision(self._DECISION_ALERTS, value)
```

### Working with decisions

```python
# Setting decisions (in a hydrator)
target = CustomerActionObject()
target.set_decision("summary", {"total": 100, "active": 75})
target.set_decision("alerts", [{"type": "low_activity", "count": 25}])

# Getting decisions (in an action)
summary = data_object.get_decision("summary")
alerts = data_object.get_decision("alerts")

# List all decisions
all_decisions = data_object.list_decisions()
```

## BaseDataObject

All data objects inherit from `BaseDataObject`, which provides:

```python
class BaseDataObject:
    correlation_id: str   # Shared across all objects in a pipeline run
    object_id: str        # Unique to this specific object instance
```

These IDs are automatically generated and are useful for logging and tracing.

## Best Practices

### 1. Use Constants for Keys

```python
class MyProcessObject(ProcessDataObject):
    _DATASET_USERS = "users"
    _ARTIFACT_COUNT = "user_count"

    # This prevents typos and enables IDE autocomplete
```

### 2. Create Property Accessors

```python
@property
def user_count(self) -> int:
    return self.get_artifact(self._ARTIFACT_COUNT, 0)

@user_count.setter
def user_count(self, value: int) -> None:
    self.set_artifact(self._ARTIFACT_COUNT, value)
```

### 3. Validate in Hydrators

```python
def hydrate(self, source, receipt):
    target = MyProcessObject()

    # Validate required data exists
    if "users" not in source.csv:
        raise ValueError("Missing users data from CSV retriever")

    target.normalized_data["users"] = source.csv["users"]
    return target
```

### 4. Use Type Hints

```python
from typing import Final

class MyProcessObject(ProcessDataObject):
    _ARTIFACT_COUNT: Final[str] = "count"

    @property
    def count(self) -> int:  # Explicit return type
        return self.get_artifact(self._ARTIFACT_COUNT, 0)
```

---

## See Also

- [Retrievers](retrievers.md) — how retrievers populate `RetrieverDataObject`
- [Processors](processors.md) — how processors read and write to `ProcessDataObject`
- [Hydrators](hydrators.md) — the conversions between data object types
