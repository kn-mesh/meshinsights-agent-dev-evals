# Component Registry

The registry automatically discovers pipeline components in your project and generates JSON schemas for YAML pipeline definitions. It powers IDE autocomplete for `.ppln` files and enables the framework to instantiate components by name at runtime.

## Overview

When you define custom retrievers, processors, actions, hydrators, or data objects, the registry scans your source files using AST analysis to find classes that extend the framework's base types. It builds an index of all discovered components, then generates a JSON schema that maps component names to their configuration types.

The registry is stored at `.insights/registry.json` in your project root. The generated schema lives at `.insights/schemas/pipeline_schema.json` and is automatically wired into VS Code for `.ppln` file autocomplete.

## How Discovery Works

The `RegistryScanner` parses Python files without importing them, using AST analysis to identify classes by their base class:

| Base Class | Registry Section |
|------------|-----------------|
| `BaseRetriever` | `retrievers` |
| `BaseProcessor` | `processors` |
| `BaseAction` | `actions` |
| `BaseHydrator[Source, Target]` | `retrieve_hydrators`, `process_hydrators`, or `action_hydrators` (inferred from type args) |
| `ProcessDataObject` | `process_data_objects` |
| `ActionDataObject` | `action_data_objects` |
| `PipelineMetadata` | `metadata_types` |

### Hydrator Categorization

Hydrators are classified by their generic type arguments:

```
BaseHydrator[RetrieverDataObject, ProcessDataObject]  → retrieve_hydrators
BaseHydrator[ProcessDataObject, ActionDataObject]     → process_hydrators
BaseHydrator[ActionDataObject, None]                  → action_hydrators
```

### Name Collisions

If two components share the same class name, the scanner appends an `@` suffix to disambiguate:

```
MyProcessor       → "MyProcessor"
MyProcessor (2nd) → "MyProcessor@1"
```

### Installed Package Scanning

The scanner also checks the `mi` package installed in your venv's `site-packages`, so built-in components (like `CsvRetriever`, `JsonRetriever`, `ProcessDataObject`, `ActionDataObject`) appear in the registry alongside your custom ones.

## Configuration

Registry settings live in your `pyproject.toml` under `[tool.meshinsights-pipeline]`:

```toml
[tool.meshinsights-pipeline]
scan_paths = ["core/**", "examples/**"]    # Glob patterns for source discovery
exclude_paths = [                           # Patterns to skip
    "**/__pycache__/**",
    "**/tests/**",
    "**/*.pyc",
]
auto_scan = true                            # Rebuild automatically when stale
registry_dir = ".insights"                  # Where to store registry and schemas
```

### Default Behavior

| Setting | Default | Description |
|---------|---------|-------------|
| `scan_paths` | `["core/**", "examples/**"]` | Glob patterns to search for components |
| `exclude_paths` | `["**/__pycache__/**", "**/tests/**", "**/*.pyc"]` | Patterns to exclude |
| `auto_scan` | `true` | Auto-rebuild when the registry is stale |
| `registry_dir` | `".insights"` | Directory for registry and schema files |

## Registry Commands

Use the CLI to manage the registry directly:

```bash
# Build or rebuild the registry and schema
mi registry build

# Force rebuild even if the registry appears current
mi registry build --force

# List all discovered components by category
mi registry list
```

## Schema Generation

The `PipelineSchemaBuilder` reads the registry and dynamically generates a JSON schema for `.ppln` files. For each component, it:

1. Imports the component class
2. Inspects the `__init__` signature for a Pydantic config type
3. Generates a schema entry with the component name as a literal and its config fields inlined

The resulting schema is written to `.insights/schemas/pipeline_schema.json` and automatically registered in `.vscode/settings.json` so the YAML extension provides autocomplete and validation for `*.ppln` files.

### VS Code Integration

After a registry build, your `.vscode/settings.json` is updated with:

```json
{
    "yaml.schemas": {
        ".insights/schemas/pipeline_schema.json": ["*.ppln"]
    },
    "files.associations": {
        "*.ppln": "yaml"
    }
}
```

This gives you autocomplete for component names, config fields, and validation errors directly in your editor.

## Staleness and Rebuilds

The registry uses multiple signals to detect when a rebuild is needed:

1. **File modification timestamps** — any scanned Python file newer than the last scan triggers a rebuild
2. **Component hash mismatches** — SHA256 hashes based on class name, file path, and line number detect moved or renamed classes
3. **Config file changes** — modifications to `pyproject.toml` trigger a rebuild
4. **Version changes** — a registry version bump forces a rebuild
5. **Missing registry** — first run always scans

When `auto_scan = true` (the default), the rebuild happens automatically before pipeline execution. With `auto_scan = false`, you must run `mi registry build` manually.

## Best Practices

1. **Keep `auto_scan` enabled during development** — the overhead is minimal and prevents stale registry issues
2. **Run `mi registry build --force` after renaming or moving components** — hash-based detection catches most changes, but a force rebuild ensures consistency
3. **Add `.insights/` to `.gitignore`** — the registry and schema are generated artifacts
4. **Check `mi registry list` when debugging YAML pipelines** — confirms the framework sees your components
5. **Use descriptive class names** — they appear directly in YAML files and IDE autocomplete

---

## See Also

- [YAML Configuration](yaml-configuration.md) — how the registry powers `.ppln` file validation
- [CLI](cli.md) — `mi registry build` and `mi registry list` command reference
- [Getting Started](getting-started.md) — project setup including registry configuration
