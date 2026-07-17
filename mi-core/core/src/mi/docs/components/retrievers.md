# Retrievers

Retrievers fetch data from external sources and are the entry point for data into the pipeline.

## Overview

Retrievers are responsible for:
- Connecting to data sources (files, databases, APIs)
- Fetching raw data
- Returning data in a consistent format

## Built-in Retrievers

### CsvRetriever

Reads CSV files with optional schema validation and type conversion.

```python
from mi.core.retrievers import CsvRetriever, CsvRetrieverConfig, ColumnSchema

config = CsvRetrieverConfig(
    file_path="data/customers.csv",
    scope="default",
    filter_column="tenant_id",
    columns=[
        ColumnSchema(name="customer_id", type="str"),
        ColumnSchema(name="created_at", type="datetime", datetime_format="%Y-%m-%d"),
        ColumnSchema(name="amount", type="float"),
    ],
    delimiter=",",
    encoding="utf-8",
    strict=False,  # Log warnings instead of raising errors
)

retriever = CsvRetriever(config)
```

### JsonRetriever

Reads JSON files with schema validation.

```python
from mi.core.retrievers import JsonRetriever, JsonRetrieverConfig, FieldSchema

config = JsonRetrieverConfig(
    file_path="data/devices.json",
    root_key="devices",  # Extract from {"devices": [...]}
    filter_field="device_id",
    fields=[
        FieldSchema(name="device_id", type="str"),
        FieldSchema(name="status", type="str"),
    ],
)

retriever = JsonRetriever(config)
```

## Creating Custom Retrievers

### Basic Structure

```python
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig

class MyRetrieverConfig(BaseRetrieverConfig):
    # Add your configuration fields
    connection_string: str
    table_name: str

class MyRetriever(BaseRetriever):
    def __init__(self, config: MyRetrieverConfig) -> None:
        # CRITICAL: Set name and scope BEFORE super().__init__()
        config.name = "database"      # Retriever type identifier
        config.scope = config.table_name  # Dataset key
        super().__init__(config)

        self.connection_string = config.connection_string
        self.table_name = config.table_name

    def retrieve(self, *, metadata=None):
        """Fetch data from the source.

        Returns:
            Data in any format (DataFrame, dict, list, etc.)
            The framework wraps it as {name: {scope: data}}
        """
        # Your data fetching logic
        self.logger.info(f"Fetching from {self.table_name}")
        data = fetch_from_database(self.connection_string, self.table_name)
        return data
```

### Important: name and scope

The `config.name` and `config.scope` values determine how data is structured in `RetrieverDataObject`:

```python
config.name = "csv"
config.scope = "customers"
# Result: source.csv["customers"] contains the data

config.name = "api"
config.scope = "users"
# Result: source.api["users"] contains the data
```

**Always set these BEFORE calling `super().__init__(config)`.**

### Using Pipeline Metadata

Retrievers can access pipeline metadata for filtering or parameterization:

```python
def retrieve(self, *, metadata=None):
    if metadata:
        tenant_id = metadata.unit
        self.logger.info(f"Filtering for tenant: {tenant_id}")
        return self.fetch_for_tenant(tenant_id)
    return self.fetch_all()
```

### With Caching

Use the cache decorator to avoid repeated I/O:

```python
from mi.utilities import cache

class CachedRetriever(BaseRetriever):
    def retrieve(self, *, metadata=None):
        return self._load_data()

    @cache(log_misses=True)
    def _load_data(self):
        # This result is cached across calls
        return pd.read_csv(self.file_path)
```

## Configuration

### BaseRetrieverConfig Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Retriever type identifier (e.g., "csv", "api") |
| `scope` | str | Dataset key within the retriever type |

### Custom Configuration

Extend `BaseRetrieverConfig` with your own fields:

```python
from pydantic import Field

class ApiRetrieverConfig(BaseRetrieverConfig):
    base_url: str = Field(description="API base URL")
    api_key: str = Field(description="API authentication key")
    endpoint: str = Field(default="/data", description="API endpoint")
    timeout: int = Field(default=30, description="Request timeout in seconds")
```

## Examples

### API Retriever

```python
import requests
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig

class ApiRetrieverConfig(BaseRetrieverConfig):
    base_url: str
    api_key: str
    endpoint: str = "/data"

class ApiRetriever(BaseRetriever):
    def __init__(self, config: ApiRetrieverConfig) -> None:
        config.name = "api"
        config.scope = "default"
        super().__init__(config)
        self.base_url = config.base_url
        self.api_key = config.api_key
        self.endpoint = config.endpoint

    def retrieve(self, *, metadata=None):
        url = f"{self.base_url}{self.endpoint}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        self.logger.info(f"Fetching from {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()
```

### Database Retriever

```python
import pandas as pd
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig

class DatabaseRetrieverConfig(BaseRetrieverConfig):
    connection_string: str
    query: str

class DatabaseRetriever(BaseRetriever):
    def __init__(self, config: DatabaseRetrieverConfig) -> None:
        config.name = "database"
        config.scope = "query_result"
        super().__init__(config)
        self.connection_string = config.connection_string
        self.query = config.query

    def retrieve(self, *, metadata=None):
        self.logger.info("Executing query")
        # Using pandas read_sql or your preferred database library
        df = pd.read_sql(self.query, self.connection_string)
        return df
```

### Multiple Retrievers

A pipeline can have multiple retrievers:

```python
pipeline = (
    PipelineBuilder()
    .add_retriever(CsvRetriever(CsvRetrieverConfig(
        file_path="customers.csv",
        name="csv",
        scope="customers"
    )))
    .add_retriever(ApiRetriever(ApiRetrieverConfig(
        base_url="https://api.example.com",
        name="api",
        scope="orders"
    )))
    .with_retrieve_hydrator(MyHydrator())
    # ...
)

# In hydrator:
def hydrate(self, source, receipt):
    customers = source.csv["customers"]
    orders = source.api["orders"]
    # Combine data...
```

## Best Practices

1. **Set name/scope early** - Always before `super().__init__()`
2. **Use logging** - `self.logger` is available for debugging
3. **Handle errors gracefully** - Validate inputs, catch exceptions
4. **Cache when appropriate** - Use `@cache` for repeated I/O
5. **Support metadata filtering** - Enable per-unit data retrieval

---

## See Also

- [Hydrators](hydrators.md) — how retriever output is converted to process data objects
- [Data Objects](data-objects.md) — the `RetrieverDataObject` structure retrievers populate
- [Utilities](../utilities.md) — `@cache` decorator for caching retriever results
