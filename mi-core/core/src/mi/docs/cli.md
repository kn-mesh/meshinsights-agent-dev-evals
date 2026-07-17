# CLI Reference

The `mi` command-line interface provides tools for creating, managing, and running Mesh Insights pipelines.

## Installation

```bash
# Using uv (recommended) from Git repository
uv tool install --from "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli" meshinsights-cli
```

Verify installation:
```bash
mi --help
mi --version
```

## When to Use the CLI

| Task | Use CLI | Use Python API |
|------|---------|----------------|
| Create a new project | `mi init` | - |
| Run a YAML-defined pipeline | `mi run` | `PipelineBuilder.from_yaml()` |
| Rebuild component registry | `mi registry build` | - |
| Inspect available components | `mi registry list` | - |
| Custom pipeline logic | - | `PipelineBuilder` |
| Programmatic execution | - | `pipeline.run()` |
| Integration with other code | - | Python API |

**Use the CLI when:**
- Creating new pipeline projects from templates
- Running pipelines defined in YAML files
- Managing the component registry
- Quick pipeline execution without writing Python

**Use the Python API when:**
- Building pipelines programmatically
- Integrating pipelines into larger applications
- Custom execution logic or error handling
- Running pipelines from within other Python code

## Commands

### `mi init` - Create a New Project

Scaffolds a new pipeline project from a template.

```bash
mi init my_project
mi init my_project --template standard
mi init my_project --template hotseat
```

**Options:**
| Option | Description |
|--------|-------------|
| `--template, -t` | Template key to use (for example `standard`, `hotseat`, `spirax`) |
| `--skip-uv-sync` | Skip running `uv sync` after creation |
| `--no-git-init` | Don't initialize a git repository |
| `--force, -f` | Overwrite existing files |

The concrete template implementations live in the companion templates
repository, which `mi init` clones during scaffolding.

**What it creates (varies by template):**
```
my_project/
├── src/
│   ├── objects/
│   ├── retrievers/
│   ├── processors/
│   ├── hydrators/
│   └── actions/
├── pipelines/
├── data/
└── pyproject.toml
```

### `mi run` - Execute a Pipeline

Runs a pipeline from a YAML configuration file.

```bash
mi run pipelines/my_pipeline.ppln
mi run path/to/pipeline.yaml
```

**What it does:**
1. Loads pipeline configuration from YAML
2. Discovers project components via the registry
3. Builds and executes the pipeline
4. Reports success/failure and execution time

**Example output:**
```
Loading pipeline from: pipelines/customer_insights.ppln
Building pipeline...
Running pipeline...
Pipeline execution completed successfully
Total execution time: 2.34 seconds
```

### `mi registry build` - Rebuild Component Registry

Scans your project and rebuilds the component registry.

```bash
mi registry build
mi registry build --force
mi registry build --config path/to/pyproject.toml
```

**Options:**
| Option | Description |
|--------|-------------|
| `--force, -f` | Force rebuild even if registry is up to date |
| `--config, -c` | Path to pyproject.toml with meshinsights config |

**When to use:**
- After adding new components (retrievers, processors, etc.)
- After renaming or moving component files
- When YAML pipeline can't find a component
- After pulling changes that add components

### `mi registry list` - List Components

Displays all registered components.

```bash
mi registry list
mi registry list --section retrievers
mi registry list --section processors
```

**Options:**
| Option | Description |
|--------|-------------|
| `--section, -s` | Filter by section (`retrievers`, `processors`, `actions`, etc.) |
| `--config, -c` | Path to pyproject.toml |

**Example output:**
```
[retrievers]
  CsvRetriever (mi.core.retrievers.csv_retriever)
  JsonRetriever (mi.core.retrievers.json_retriever)
  CustomerCsvRetriever (my_project.retrievers.customer_csv_retriever)

[processors]
  MetricsProcessor (my_project.processors.metrics_processor)
```

### `mi update` - Update CLI

Updates the meshinsights CLI to the latest version.

```bash
mi update
mi update --ref develop
mi update --pre
```

**Options:**
| Option | Description |
|--------|-------------|
| `--ref, -r` | Git ref to install from (`main`, `develop`) |
| `--pre` | Allow pre-release versions |

## Configuration

The CLI reads configuration from `pyproject.toml`:

```toml
[tool.meshinsights-pipeline]
scan_paths = ["src"]
exclude_paths = ["tests", "scripts"]
auto_scan = true
registry_dir = ".insights"
```

## Typical Workflow

1. **Create a project:**
   ```bash
   mi init my_pipeline --template standard
   cd my_pipeline
   ```

2. **Implement components** (retrievers, processors, actions)

3. **Rebuild the registry:**
   ```bash
   mi registry build
   ```

4. **Verify components are registered:**
   ```bash
   mi registry list
   ```

5. **Create a pipeline YAML** in `pipelines/`

6. **Run the pipeline:**
   ```bash
   mi run pipelines/my_pipeline.ppln
   ```

## Troubleshooting

### "Component not found" error

```bash
# Rebuild the registry
mi registry build --force

# Verify component is registered
mi registry list --section retrievers
```

### Pipeline YAML not loading

```bash
# Check the file path is correct
mi run ./pipelines/my_pipeline.ppln

# Ensure you're in the project root
pwd
```

### CLI not found after installation

```bash
# Check if it's in PATH
which mi

# Try reinstalling
uv tool install meshinsights-cli --force
```

---

## See Also

- [YAML Configuration](yaml-configuration.md) — the `.ppln` file format used by `mi run`
- [Component Registry](registry.md) — how `mi registry build` discovers components
- [Getting Started](getting-started.md) — full project setup workflow including CLI usage
