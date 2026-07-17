# YAML Configuration

Pipelines can be defined declaratively using YAML files, making them easier to version, share, and modify without code changes.

## File Format

Pipeline definitions use the `.ppln` extension by convention:

```yaml
# pipelines/my_pipeline.ppln
name: my_pipeline
version: 1.0.0

retrieve:
  hydrator: RetrieveToProcessHydrator
  retrievers:
    - retriever: CsvRetriever
      file_path: data/input.csv
      scope: default

process:
  hydrator: ProcessToActionHydrator
  processors:
    - processor: MetricsProcessor

action:
  hydrator: FinalizeHydrator
  actions:
    - action: SaveAction
```

## Structure

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Pipeline identifier |
| `version` | No | Pipeline version string |
| `retrieve` | Yes | Retrieve stage configuration |
| `process` | Yes | Process stage configuration |
| `action` | Yes | Action stage configuration |

### Retrieve Section

```yaml
retrieve:
  hydrator: RetrieveToProcessHydrator  # Class name
  retrievers:
    - retriever: CsvRetriever          # Class name
      file_path: data/customers.csv    # Config field
      scope: customers                 # Config field
      columns:                         # Nested config
        - name: id
          type: str
        - name: amount
          type: float
```

**Fields:**
- `hydrator` - Class name of the retrieve hydrator
- `retrievers` - List of retriever configurations
  - `retriever` - Class name of the retriever
  - Additional fields are passed to the retriever's config

### Process Section

```yaml
process:
  hydrator: ProcessToActionHydrator
  processors:
    - processor: DataCleaningProcessor
      strict: true
    - processor: MetricsProcessor
    - processor: AnomalyProcessor
      threshold: 0.95
```

**Fields:**
- `hydrator` - Class name of the process hydrator
- `processors` - List of processor configurations (run in order)
  - `processor` - Class name of the processor
  - Additional fields are passed to the processor's config

### Action Section

```yaml
action:
  hydrator: FinalizeHydrator
  actions:
    - action: DatabaseSaveAction
      connection_string: postgresql://localhost/db
    - action: EmailNotificationAction
      recipients:
        - admin@example.com
        - team@example.com
```

**Fields:**
- `hydrator` - Class name of the action hydrator
- `actions` - List of action configurations (run in order)
  - `action` - Class name of the action
  - Additional fields are passed to the action's config

## Loading YAML Pipelines

### From File

```python
from mi.core import PipelineBuilder

builder = PipelineBuilder.from_yaml("pipelines/my_pipeline.ppln")
pipeline = builder.build()
receipt = pipeline.run()
```

### From String

```python
yaml_content = """
name: inline_pipeline
retrieve:
  hydrator: RetrieveHydrator
  retrievers:
    - retriever: CsvRetriever
      file_path: data/input.csv
process:
  hydrator: ProcessHydrator
  processors:
    - processor: MyProcessor
action:
  hydrator: ActionHydrator
  actions:
    - action: MyAction
"""

builder = PipelineBuilder.from_yaml_string(yaml_content)
pipeline = builder.build()
```

### Using the CLI

```bash
mi run pipelines/my_pipeline.ppln
```

## Component Registry

YAML files reference components by class name. The registry discovers these classes automatically from your project.

### How Discovery Works

1. The registry scans Python files in your project
2. It finds classes inheriting from base components
3. Class names become available for YAML reference

### Registry Requirements

Components must:
1. Inherit from a base class (`BaseRetriever`, `BaseProcessor`, etc.)
2. Be importable from your project
3. Have a unique class name within their type

### Example Project Structure

```
my_project/
├── src/
│   ├── retrievers/
│   │   └── customer_retriever.py    # CustomerRetriever class
│   ├── processors/
│   │   └── metrics_processor.py     # MetricsProcessor class
│   └── ...
└── pipelines/
    └── customer_pipeline.ppln       # References CustomerRetriever, MetricsProcessor
```

```yaml
# customer_pipeline.ppln
retrieve:
  retrievers:
    - retriever: CustomerRetriever   # Matches class name exactly
process:
  processors:
    - processor: MetricsProcessor    # Matches class name exactly
```

## Configuration Mapping

YAML fields map directly to Pydantic config fields:

### Python Config

```python
class CsvRetrieverConfig(BaseRetrieverConfig):
    file_path: str
    delimiter: str = ","
    encoding: str = "utf-8"
    columns: list[ColumnSchema] = []
```

### YAML Equivalent

```yaml
- retriever: CsvRetriever
  file_path: data/input.csv
  delimiter: ","
  encoding: utf-8
  columns:
    - name: id
      type: str
    - name: value
      type: float
```

## Complete Example

### Python Components

```python
# retrievers/order_retriever.py
class OrderRetrieverConfig(BaseRetrieverConfig):
    api_url: str
    api_key: str
    date_range: int = 30

class OrderRetriever(BaseRetriever):
    def __init__(self, config: OrderRetrieverConfig):
        config.name = "api"
        config.scope = "orders"
        super().__init__(config)
        # ...

# processors/revenue_processor.py
class RevenueProcessorConfig(BaseProcessorConfig):
    include_refunds: bool = True

class RevenueProcessor(BaseProcessor):
    # ...

# actions/report_action.py
class ReportActionConfig(BaseActionConfig):
    output_path: str
    format: str = "pdf"

class ReportAction(BaseAction):
    # ...
```

### YAML Pipeline

```yaml
# pipelines/revenue_report.ppln
name: revenue_report
version: 2.0.0

retrieve:
  hydrator: OrderRetrieveHydrator
  retrievers:
    - retriever: OrderRetriever
      api_url: https://api.example.com/orders
      api_key: ${API_KEY}  # Environment variable
      date_range: 90

process:
  hydrator: RevenueProcessHydrator
  processors:
    - processor: RevenueProcessor
      include_refunds: false

action:
  hydrator: ReportFinalizeHydrator
  actions:
    - action: ReportAction
      output_path: reports/
      format: pdf
```

### Running

```python
from mi.core import PipelineBuilder

pipeline = PipelineBuilder.from_yaml("pipelines/revenue_report.ppln").build()
receipt = pipeline.run()
```

Or via CLI:

```bash
mi run pipelines/revenue_report.ppln
```

## Environment Variables

Reference environment variables using `${VAR_NAME}` syntax:

```yaml
retrieve:
  retrievers:
    - retriever: DatabaseRetriever
      connection_string: ${DATABASE_URL}
      username: ${DB_USER}
      password: ${DB_PASSWORD}
```

## Best Practices

1. **Use `.ppln` extension** - Distinguishes pipeline files
2. **Store in `pipelines/` directory** - Keep organized
3. **Version your pipelines** - Track changes over time
4. **Use environment variables** - For secrets and environment-specific config
5. **Match class names exactly** - YAML references must match Python class names
6. **Document configurations** - Add comments explaining non-obvious settings

---

## See Also

- [Component Registry](registry.md) — how component discovery and schema generation work
- [Pipeline Builder](pipeline-builder.md) — programmatic alternative to YAML definitions
- [CLI](cli.md) — running YAML pipelines from the command line
- [Data Objects](components/data-objects.md) — the typed containers referenced in YAML `objects` section
