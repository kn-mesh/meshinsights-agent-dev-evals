# mesh.insights.core

A flexible, type-safe framework for building multi-stage data pipelines with pluggable components for retrieval, processing, hydration, and actions.

## Installing the `mi` CLI

Mesh Insights ships a thin CLI (`mi`) via the privately hosted `meshinsights-cli`
package. Install it directly from the Git repo (replace the SSH URL with the one
your org provides):

```bash
uv tool install --from "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli" meshinsights-cli
# or
pip install "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli"
```

When developing from this repo locally, install the workspace build instead so
you pick up changes instantly:

```bash
uv tool install --from ./cli meshinsights-cli --editable
# or
pip install -e cli
```

Verify the tool is on your PATH:

```bash
mi --help
```

## Quick Start

### Prerequisites

- Python 3.13.5
- [UV](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd meshinsights-data-pipeline
   ```

2. Install dependencies (workspace-aware):
   ```bash
   pip install uv
   uv sync
   ```

   This will set up the virtual environment and install all required dependencies from `pyproject.toml`.

### Repository Layout

This repository is now a monorepo that builds two Python packages:

- `core/` – the reusable runtime exported as the `mi-core` wheel (sources live under `core/src/mi`)
- `cli/` – the thin CLI wrapper published as `meshinsights-cli` and depending on the core package (`cli/src/cli`)

Running `uv sync` from the repo root installs both packages in editable mode along with the shared dev tooling declared in the workspace `pyproject.toml`.

Concrete starter implementations now live in the companion templates repository:

- `https://github.com/Mesh-Systems-Eng/mesh.insights.templates`

Use this repo for framework development and reference docs. Use `mi init` or the
templates repo when you want a runnable project skeleton.

## Developing This Repo

### Workspace Interpreter

Because the repo is managed as a UV workspace, dependencies (including the
editable `mi-core` package) are only injected when commands are executed through
UV. Always run Python entry points via `uv run …` so imports such as `pandas`
and `mi` resolve correctly:

```bash
uv run python -m basedpyright
uv run python -m pytest
uv run ipython
```

If you prefer to use another toolchain, install the packages manually (for
example `pip install -e core -e cli` plus whichever shared dependencies your
workflow needs from the root `pyproject.toml`).

## Consumer Projects

To scaffold a concrete project, use the CLI:

```bash
mi init my-project
mi init my-project --template standard
```

Available templates are defined by the CLI and currently include concrete
starter projects such as `standard`, `hotseat`, and `spirax`.

For end-to-end examples, template structure, and runnable starter
implementations, use the templates repository rather than this framework repo.

## Architecture

The framework is built around four main stages:

1. **Retrieval** - Fetch data from various sources (CSV, databases, APIs, etc.)
2. **Processing** - Transform and analyze the retrieved data
3. **Hydration** - Convert data between pipeline stages using type-safe hydrators
4. **Actions** - Execute final operations (save to database, send notifications, etc.)

### Core Components

- **Retrievers** (`core/retrievers/`) - Abstract data retrieval from various sources
- **Processors** (`core/processors/`) - Transform and process data objects
- **Hydrators** (`core/hydrators/`) - Convert data objects between pipeline stages
- **Actions** (`core/actions/`) - Execute final operations on processed data
- **Data Objects** (`core/objects/`) - Type-safe data containers for each stage

## How To

This section walks through creating custom components for your pipeline. We'll build a simple example that processes user activity data.

### 1. Create Custom Data Objects

Data objects are type-safe containers that hold data as it flows through the pipeline. You need two types: a `ProcessDataObject` and an `ActionDataObject`.

#### ProcessDataObject

```python
from typing import Final
from mi.core.objects import ProcessDataObject
import pandas as pd

class UserActivityProcessObject(ProcessDataObject):
    _DATASET_DEFAULT: Final[str] = "default"
    _ARTIFACT_ACTIVE_USERS: Final[str] = "active_users"
    _ARTIFACT_TOTAL_EVENTS: Final[str] = "total_events"

    @property
    def activity_data(self) -> pd.DataFrame:
        return self.get_dataset(self._DATASET_DEFAULT)

    @property
    def active_users(self) -> int:
        return self.get_artifact(self._ARTIFACT_ACTIVE_USERS)

    @active_users.setter
    def active_users(self, value: int) -> None:
        self.set_artifact(self._ARTIFACT_ACTIVE_USERS, value)

    @property
    def total_events(self) -> int:
        return self.get_artifact(self._ARTIFACT_TOTAL_EVENTS)

    @total_events.setter
    def total_events(self, value: int) -> None:
        self.set_artifact(self._ARTIFACT_TOTAL_EVENTS, value)
```

#### ActionDataObject

```python
from typing import Final
from mi.core.objects import ActionDataObject

class UserActivityActionObject(ActionDataObject):
    _DECISION_ACTIVE_USERS: Final[str] = "active_users"
    _DECISION_TOTAL_EVENTS: Final[str] = "total_events"

    @property
    def active_users(self) -> int:
        return self.get_decision(self._DECISION_ACTIVE_USERS)

    @active_users.setter
    def active_users(self, value: int) -> None:
        self.set_decision(self._DECISION_ACTIVE_USERS, value)

    @property
    def total_events(self) -> int:
        return self.get_decision(self._DECISION_TOTAL_EVENTS)

    @total_events.setter
    def total_events(self, value: int) -> None:
        self.set_decision(self._DECISION_TOTAL_EVENTS, value)
```

### 2. Create a Custom Retriever

Retrievers fetch data from your source. They must inherit from `BaseRetriever` and implement the `retrieve()` method.

```python
from pathlib import Path
import pandas as pd
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig

class UserActivityRetrieverConfig(BaseRetrieverConfig):
    file_path: str
    dataset_name: str = "default"

class UserActivityRetriever(BaseRetriever):
    def __init__(self, config: UserActivityRetrieverConfig | None = None) -> None:
        if config is None:
            raise ValueError("UserActivityRetriever requires a config")
        
        config.name = "user_activity"
        config.scope = "default"
        super().__init__(config)
        
        self.file_path = Path(config.file_path)
        self.dataset_name = config.dataset_name

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def retrieve(self) -> pd.DataFrame:
        self.logger.info(f"Reading file: {self.file_path}")
        df = pd.read_csv(self.file_path)
        self.logger.debug(f"Loaded {len(df)} rows")
        return df
```

### 3. Create Custom Hydrators

Hydrators convert data between pipeline stages. You need three types:

#### Retrieval Hydrator (RetrieverDataObject → ProcessDataObject)

```python
from mi.core.hydrators import BaseHydrator
from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt
from your_project.objects import UserActivityProcessObject

class UserActivityRetrievalHydrator(BaseHydrator[RetrieverDataObject, UserActivityProcessObject]):
    def hydrate(
        self,
        source: RetrieverDataObject,
        receipt: PipelineReceipt,
    ) -> UserActivityProcessObject:
        self.logger.debug("Hydrating ProcessDataObject from RetrieverDataObject")
        
        target = UserActivityProcessObject()
        df = source.csv["default"]
        target.normalized_data["default"] = df
        
        if receipt.retrieve_receipt:
            receipt.retrieve_receipt.set_metadata("hydrated_to_process", True)
        
        return target
```

#### Process Hydrator (ProcessDataObject → ActionDataObject)

```python
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from your_project.objects import UserActivityProcessObject, UserActivityActionObject

class UserActivityProcessHydrator(BaseHydrator[UserActivityProcessObject, UserActivityActionObject]):
    def hydrate(
        self,
        source: UserActivityProcessObject,
        receipt: PipelineReceipt,
    ) -> UserActivityActionObject:
        self.logger.debug("Hydrating ActionDataObject from ProcessDataObject")
        
        target = UserActivityActionObject()
        target.active_users = source.active_users
        target.total_events = source.total_events
        
        if receipt.process_receipt:
            receipt.process_receipt.set_metadata("hydrated_to_action", True)
        
        return target
```

#### Action Hydrator (ActionDataObject → None)

```python
from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from your_project.objects import UserActivityActionObject

class UserActivityActionHydrator(BaseHydrator[UserActivityActionObject, None]):
    def hydrate(
        self,
        source: UserActivityActionObject,
        receipt: PipelineReceipt,
    ) -> None:
        self.logger.debug("Finalizing ActionDataObject")
        
        # Perform any final cleanup or logging
        self.logger.info(
            f"Activity summary - Active users: {source.active_users}, "
            f"Total events: {source.total_events}"
        )
        
        if receipt.act_receipt:
            receipt.act_receipt.set_metadata("finalized", True)
```

### 4. Create a Custom Processor

Processors transform and analyze data. They operate on `ProcessDataObject` instances.

```python
from mi.core.processors import BaseProcessor
from your_project.objects import UserActivityProcessObject
import pandas as pd

class UserActivityProcessor(BaseProcessor[UserActivityProcessObject]):
    def process(self, data_object: UserActivityProcessObject) -> None:
        self.logger.debug("Processing user activity data")
        
        activity_data = data_object.activity_data
        
        # Calculate metrics
        active_users = activity_data["user_id"].nunique()
        total_events = len(activity_data)
        
        # Store results in the data object
        data_object.active_users = active_users
        data_object.total_events = total_events
        
        self.logger.debug(
            f"Processed activity - Active users: {active_users}, "
            f"Total events: {total_events}"
        )
```

### 5. Create a Custom Action

Actions execute final operations on processed data. They operate on `ActionDataObject` instances.

```python
from mi.core.actions import BaseAction
from your_project.objects import UserActivityActionObject

class UserActivityAction(BaseAction[UserActivityActionObject]):
    def act(self, data_object: UserActivityActionObject) -> None:
        self.logger.debug("Executing user activity action")
        
        active_users = data_object.active_users
        total_events = data_object.total_events
        
        # Perform your action (e.g., send notification, save to database, etc.)
        print(f"📊 Activity Report:")
        print(f"   Active Users: {active_users}")
        print(f"   Total Events: {total_events}")
        
        self.logger.info(f"Action completed for {active_users} active users")
        
        # Actions must return None - any return value is discarded
```

### 6. Assemble and Run Your Pipeline

Now combine all components using the `PipelineBuilder`. There are two ways to specify type parameters:

**Option 1: Using generics on PipelineBuilder (recommended)**

```python
from pathlib import Path
from mi.core import PipelineBuilder
from your_project.retrievers import UserActivityRetriever, UserActivityRetrieverConfig
from your_project.hydrators import (
    UserActivityRetrievalHydrator,
    UserActivityProcessHydrator,
    UserActivityActionHydrator
)
from your_project.processors import UserActivityProcessor
from your_project.actions import UserActivityAction
from your_project.objects import UserActivityProcessObject, UserActivityActionObject

# Configure retriever
csv_path = Path("data/activity.csv")
retriever_config = UserActivityRetrieverConfig(
    file_path=str(csv_path),
    dataset_name="default"
)
retriever = UserActivityRetriever(retriever_config)

# Build and run pipeline with generics
pipeline = (
    PipelineBuilder[UserActivityProcessObject, UserActivityActionObject]()
    .add_retriever(retriever)
    .with_retrieve_hydrator(UserActivityRetrievalHydrator())
    .add_processor(UserActivityProcessor())
    .with_process_hydrator(UserActivityProcessHydrator())
    .add_action(UserActivityAction())
    .with_action_hydrator(UserActivityActionHydrator())
    .build()
)

receipt = pipeline.run()
print(f"\nPipeline execution complete!")
print(f"Success: {receipt.success}")
print(f"Total execution time: {receipt.total_execution_time_seconds:.2f}s")
```

**Option 2: Using `with_objects()` for typing**

The `with_objects()` method is purely for type inference - it doesn't actually use the objects you pass. It's an alternative way to specify types:

```python
pipeline = (
    PipelineBuilder()
    .with_objects(UserActivityProcessObject(), UserActivityActionObject())  # For typing only
    .add_retriever(retriever)
    .with_retrieve_hydrator(UserActivityRetrievalHydrator())
    .add_processor(UserActivityProcessor())
    .with_process_hydrator(UserActivityProcessHydrator())
    .add_action(UserActivityAction())
    .with_action_hydrator(UserActivityActionHydrator())
    .build()
)
```

**Note:** `with_config()` is optional - if not provided, the pipeline will use default `PipelineConfig()` settings.

## Project File Structure

For a typical consuming project, organize your pipeline code as follows:

```
your-project/
├── objects/
│   ├── __init__.py
│   ├── your_process_obj.py      # Your ProcessDataObject subclass
│   └── your_action_obj.py        # Your ActionDataObject subclass
├── retrievers/
│   ├── __init__.py
│   ├── your_retriever.py         # Your BaseRetriever subclass
│   └── your_retriever_config.py   # Optional: separate config class
├── hydrators/
│   ├── __init__.py
│   ├── your_retrieval_hydrator.py  # RetrieverDataObject → ProcessDataObject
│   ├── your_process_hydrator.py     # ProcessDataObject → ActionDataObject
│   └── your_action_hydrator.py     # ActionDataObject → None
├── processors/
│   ├── __init__.py
│   └── your_processor.py           # Your BaseProcessor subclass
├── actions/
│   ├── __init__.py
│   └── your_action.py              # Your BaseAction subclass
├── data/                            # Input data files
│   └── your_data.csv
└── your_pipeline.py                 # Main pipeline script
```

### Key Points:

- **Separate directories** for each component type (objects, retrievers, hydrators, processors, actions)
- **Include `__init__.py`** files to make directories Python packages
- **Group related components** in the same directory structure
- **Keep data files** in a dedicated `data/` directory
- **Main pipeline script** at the project root for easy execution

This structure keeps your code organized, makes imports clear, and matches the
layout expected by the framework and its starter templates.

## Versioning

This monorepo uses **unified versioning** — both `mi-core` and `meshinsights-cli` always share the same version number. Versions are bumped automatically when a PR is merged to `main`.

### How it works

1. Write your changelog entries under the `## [Unreleased]` section in `CHANGELOG.md` as part of your PR
2. Add exactly one version label to your PR to control the bump type:
   - `major` — breaking changes (e.g., `0.5.0` → `1.0.0`)
   - `minor` — new features (e.g., `0.5.0` → `0.6.0`)
   - `patch` — fixes or small changes (e.g., `0.5.0` → `0.5.1`)
3. Merge the PR to `main`
4. The **Version Bump** GitHub Action automatically:
   - Runs only when the merged PR has a `major`, `minor`, or `patch` label
   - Reads the bump type from that label
   - Runs `scripts/bump_versions.py bump` which updates:
     - `core/pyproject.toml` — package version
     - `cli/pyproject.toml` — package version and `mi-core` dependency pin
     - `core/src/mi/core/utils/telemetry.py` — `SERVICE_VERSION` for OpenTelemetry
     - `CHANGELOG.md` via `scripts/changelog.py update` — renames `[Unreleased]` to the new version with today's date, adds a fresh `[Unreleased]` section, and updates comparison links
   - Commits the changes to `main`
   - Creates a git tag (`vX.Y.Z`) and pushes the commit and tag
   - Extracts the changelog entry with `scripts/changelog.py extract` and creates a GitHub Release with the changelog content as the release notes

> The **Release** workflow (`.github/workflows/release.yml`) can also be triggered independently by pushing a `v*` tag manually.

### Running locally

You can run the bump script manually for testing (changes are real — remember to revert if needed):

```bash
python scripts/bump_versions.py bump patch   # 0.5.0 → 0.5.1
python scripts/bump_versions.py bump minor   # 0.5.0 → 0.6.0
python scripts/bump_versions.py bump major   # 0.5.0 → 1.0.0
```

To extract a changelog entry for a specific version:

```bash
python scripts/changelog.py extract 0.4.2
```

To stamp the current `## [Unreleased]` section as a release manually:

```bash
python scripts/changelog.py update 0.5.1 0.5.0
```

## Documentation

For framework API documentation, see the docs under `core/src/mi/docs/`.
For concrete starter implementations, see:

- `https://github.com/Mesh-Systems-Eng/mesh.insights.templates`
