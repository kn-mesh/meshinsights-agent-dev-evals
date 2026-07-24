"""Safely materialize, render, and validate Agent Workbench projects."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import tomllib
from typing import Any

import yaml
from evaluation import is_sensitive_path
from model_catalog import load_model_catalog

from src.project_bootstrap.models import (
    BootstrapSpec,
    ProjectContract,
    ProjectPaths,
    TemplateOwnershipManifest,
    TemplateProvenance,
)


DEFAULT_TEMPLATE_SOURCE = (
    "https://github.com/Mesh-Systems-Eng/mesh.insights.templates.git"
)
PROJECT_CONTRACT_FILE = "workbench.project.json"
TEMPLATE_MANIFEST_FILE = "workbench.template.json"

_EXCLUDED_PARTS = frozenset(
    {
        ".docker",
        ".ds_store",
        ".git",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".logfire",
        ".insights",
        ".coverage",
        "__pycache__",
        "build",
        "dist",
        "eval_results",
        "htmlcov",
        "node_modules",
    }
)
_REQUIRED_DIRECTORIES = (
    "docs/use_case",
    "pipeline_configs",
    "evaluation_configs",
    "agent_version_configs",
    "eval_results",
    "src/actions",
    "src/evidence",
    "src/hydrators",
    "src/objects",
    "src/processors",
    "src/retrievers",
    "src/pipelines",
    "src/evals",
    "www/src/use_case",
    "tests",
    "tests/use_case",
)


def load_bootstrap_spec(path: Path) -> BootstrapSpec:
    """Load and strictly validate a versioned bootstrap specification."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read bootstrap spec {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Bootstrap spec is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError("Bootstrap spec must be a JSON object.")
    return BootstrapSpec.model_validate(payload)


def initialize_project(
    destination: Path,
    *,
    spec_path: Path,
    template_source: str = DEFAULT_TEMPLATE_SOURCE,
    template_ref: str | None = None,
    template_revision: str | None = None,
    initialize_git: bool = True,
) -> dict[str, Any]:
    """Create and validate a new project without overlaying existing content."""
    spec = load_bootstrap_spec(spec_path)
    destination = destination.expanduser().resolve()
    _validate_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.bootstrap-", dir=destination.parent
        )
    )
    try:
        with _template_checkout(
            template_source,
            template_ref=template_ref,
            explicit_revision=template_revision,
        ) as (template_root, provenance, tracked_only):
            _copy_template(template_root, staging, tracked_only=tracked_only)
        manifest = _load_template_manifest(staging)
        _reset_reference_use_case(staging, manifest)
        contract = _render_project(staging, spec=spec, provenance=provenance)
        if initialize_git:
            _run_git(["init", "--initial-branch=main"], cwd=staging)
        validation = validate_project(staging)
        if destination.exists():
            destination.rmdir()
        os.replace(staging, destination)
        validation["project_root"] = str(destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return {
        "status": "initialized",
        "destination": str(destination),
        "project_key": contract.project.key,
        "template_revision": contract.template.revision,
        "git_initialized": initialize_git,
        "validation": validation,
    }


def validate_project(project_root: Path) -> dict[str, Any]:
    """Validate one generated project using only its committed local contract."""
    root = project_root.expanduser().resolve()
    contract_path = root / PROJECT_CONTRACT_FILE
    try:
        contract = ProjectContract.model_validate_json(
            contract_path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise ValueError(f"Cannot read generated project contract: {error}") from error

    missing = [
        relative
        for relative in (
            "pyproject.toml",
            "README.md",
            "models.yaml",
            "model_pricing.yaml",
            ".env.example",
            "docs/use_case/PROJECT_CONTEXT.md",
            *_REQUIRED_DIRECTORIES,
        )
        if not (root / relative).exists()
    ]
    if missing:
        raise ValueError("Generated project is missing: " + ", ".join(missing))
    manifest = _load_template_manifest(root)
    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    actual_name = pyproject.get("project", {}).get("name")
    if actual_name != contract.project.distribution_name:
        raise ValueError(
            "pyproject project name does not match workbench.project.json: "
            f"{actual_name!r} != {contract.project.distribution_name!r}"
        )

    catalog = yaml.safe_load((root / contract.paths.model_catalog).read_text())
    expected_catalog = contract.model_catalog.model_dump(mode="json", exclude_none=True)
    if catalog != expected_catalog:
        raise ValueError("models.yaml does not match the generated project contract.")
    load_model_catalog(
        root / contract.paths.model_catalog,
        root / "model_pricing.yaml",
    )

    default_identity = (
        contract.benchmarks.default.key,
        contract.benchmarks.default.version,
    )
    published = {
        (benchmark.key, benchmark.version)
        for benchmark in contract.benchmarks.published
    }
    if default_identity not in published:
        raise ValueError("Default benchmark is absent from the published catalog.")
    if not contract.template.revision.strip():
        raise ValueError("Template revision provenance is required.")
    _validate_reference_leaks(root, manifest)

    return {
        "status": "valid",
        "project_root": str(root),
        "project_key": contract.project.key,
        "distribution_name": contract.project.distribution_name,
        "default_benchmark": {
            "key": contract.benchmarks.default.key,
            "version": contract.benchmarks.default.version,
        },
        "default_model": contract.model_catalog.default_model,
        "template_revision": contract.template.revision,
        "template_manifest_schema_version": manifest.schema_version,
    }


def _validate_destination(destination: Path) -> None:
    """Reject any destination that could be overwritten by initialization."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Bootstrap destination is not a directory: {destination}")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Bootstrap destination must be empty: {destination}")


@contextmanager
def _template_checkout(
    source: str,
    *,
    template_ref: str | None,
    explicit_revision: str | None,
) -> Iterator[tuple[Path, TemplateProvenance, bool]]:
    """Yield an isolated template tree and exact provenance."""
    local_source = Path(source).expanduser()
    if local_source.exists() and not _is_git_repository(local_source):
        if template_ref is not None:
            raise ValueError("--template-ref requires a Git template source.")
        if not explicit_revision or not explicit_revision.strip():
            raise ValueError("A non-Git template source requires --template-revision.")
        yield (
            local_source.resolve(),
            TemplateProvenance(
                source=str(local_source.resolve()),
                revision=explicit_revision.strip(),
            ),
            False,
        )
        return

    if explicit_revision is not None:
        raise ValueError("--template-revision is only valid for non-Git sources.")
    with tempfile.TemporaryDirectory(prefix="workbench-template-") as directory:
        checkout = Path(directory) / "template"
        _run_git(["clone", "--no-checkout", "--", source, str(checkout)])
        _run_git(["checkout", "--detach", template_ref or "HEAD"], cwd=checkout)
        revision = _run_git(["rev-parse", "HEAD"], cwd=checkout).strip()
        yield (
            checkout,
            TemplateProvenance(source=source, revision=revision),
            True,
        )


def _is_git_repository(path: Path) -> bool:
    """Return whether a path is the root of a Git work tree."""
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return Path(result.stdout.strip()).resolve() == path.resolve()


def _copy_template(source: Path, destination: Path, *, tracked_only: bool) -> None:
    """Copy safe template files while rejecting symbolic links."""
    relative_files = _tracked_files(source) if tracked_only else _ordinary_files(source)
    for relative in relative_files:
        if _excluded(relative):
            continue
        source_path = source / relative
        if source_path.is_symlink():
            raise ValueError(f"Template symlinks are not supported: {relative}")
        if not source_path.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)


def _load_template_manifest(root: Path) -> TemplateOwnershipManifest:
    """Load the versioned ownership and reference-reset contract."""
    path = root / TEMPLATE_MANIFEST_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Standard template must contain {TEMPLATE_MANIFEST_FILE}.") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Template ownership manifest is invalid JSON: {error}") from error
    return TemplateOwnershipManifest.model_validate(payload)


def _reset_reference_use_case(
    root: Path, manifest: TemplateOwnershipManifest
) -> None:
    """Clear only manifest-declared reference content in a copied template."""
    reset = manifest.reference_reset
    for relative in reset.clear_directories:
        path = _template_target(root, relative)
        if path.is_symlink():
            raise ValueError(f"Reference reset refuses symlink: {relative}")
        if path.exists():
            if not path.is_dir():
                raise ValueError(f"Reference reset expected a directory: {relative}")
            shutil.rmtree(path)
        path.mkdir(parents=True)
    for relative in reset.remove_directories:
        path = _template_target(root, relative)
        if path.is_symlink():
            raise ValueError(f"Reference reset refuses symlink: {relative}")
        if path.exists():
            if not path.is_dir():
                raise ValueError(f"Reference reset expected a directory: {relative}")
            shutil.rmtree(path)
    for relative in reset.remove_files:
        path = _template_target(root, relative)
        if path.is_symlink():
            raise ValueError(f"Reference reset refuses symlink: {relative}")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"Reference reset expected a file: {relative}")
            path.unlink()


def _template_target(root: Path, relative: str) -> Path:
    """Resolve one manifest path without allowing project-root escape."""
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError(f"Template manifest path escapes the project root: {relative}")
    return target


def _tracked_files(source: Path) -> tuple[Path, ...]:
    """List files tracked at the checked-out template revision."""
    output = _run_git(["ls-files", "-z"], cwd=source)
    return tuple(Path(value) for value in output.split("\0") if value)


def _ordinary_files(source: Path) -> tuple[Path, ...]:
    """List regular files in a non-Git template without following symlinks."""
    return tuple(
        path.relative_to(source)
        for path in source.rglob("*")
        if path.is_file() or path.is_symlink()
    )


def _excluded(relative: Path) -> bool:
    """Return whether a template path is local state or potentially sensitive."""
    pure = PurePosixPath(relative.as_posix())
    if pure.parts and pure.parts[0].lower() == "agent_versions":
        return True
    if any(part.lower() in _EXCLUDED_PARTS for part in pure.parts):
        return True
    if any(part.lower().endswith(".egg-info") for part in pure.parts):
        return True
    if pure.name.lower() in {".env.example", ".env.template"}:
        return False
    return is_sensitive_path(pure)


def _render_project(
    root: Path,
    *,
    spec: BootstrapSpec,
    provenance: TemplateProvenance,
) -> ProjectContract:
    """Render generated identity, configuration, placeholders, and paths."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        raise ValueError("Standard template must contain pyproject.toml.")
    _rewrite_pyproject(pyproject_path, spec)
    _rewrite_readme(root / "README.md", spec)
    _write_eval_runbook(root / "EvalRunbook.md", spec)

    for relative in _REQUIRED_DIRECTORIES:
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        if relative in {
            "pipeline_configs",
            "evaluation_configs",
            "agent_version_configs",
            "eval_results",
            "www/src/use_case",
            "tests/use_case",
        } and not any(directory.iterdir()):
            (directory / ".gitkeep").touch()
    for directory in _REQUIRED_DIRECTORIES:
        if directory.startswith("src/"):
            (root / directory / "__init__.py").touch(exist_ok=True)
    _write_use_case_placeholders(root)

    contract = ProjectContract(
        schema_version=1,
        created_at_utc=datetime.now(timezone.utc),
        template=provenance,
        project=spec.project,
        benchmark_studio=spec.benchmark_studio,
        benchmarks=spec.benchmarks,
        model_catalog=spec.model_catalog,
        paths=ProjectPaths(),
    )
    (root / PROJECT_CONTRACT_FILE).write_text(
        json.dumps(contract.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "models.yaml").write_text(
        yaml.safe_dump(
            spec.model_catalog.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (root / ".env.example").write_text(_environment_template(spec), encoding="utf-8")
    context_path = root / "docs/use_case/PROJECT_CONTEXT.md"
    if not context_path.exists():
        context_path.write_text(_project_context(spec), encoding="utf-8")
    return contract


def _rewrite_pyproject(path: Path, spec: BootstrapSpec) -> None:
    """Replace project identity fields without reformatting unrelated TOML."""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_project = False
    found_name = False
    found_description = False
    for index, line in enumerate(lines):
        if line.startswith("["):
            in_project = line.strip() == "[project]"
        if not in_project:
            continue
        if re.match(r"^name\s*=", line):
            lines[index] = f"name = {json.dumps(spec.project.distribution_name)}"
            found_name = True
        elif re.match(r"^description\s*=", line):
            lines[index] = f"description = {json.dumps(spec.project.description)}"
            found_description = True
    if not found_name or not found_description:
        raise ValueError("Template [project] must declare name and description.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rewrite_readme(path: Path, spec: BootstrapSpec) -> None:
    """Replace reference README content with a project-owned on-ramp."""
    if not path.exists():
        raise ValueError("Standard template must contain README.md.")
    path.write_text(
        f"""# {spec.project.name}

{spec.project.description}

This repository is a Mesh Agent Workbench project initialized from an exact
template revision. Non-secret project, benchmark, evidence, and model identities
are recorded in `workbench.project.json`.

## Start Here

1. Document durable domain context in `docs/use_case/PROJECT_CONTEXT.md`.
2. Port the published-benchmark evidence pipeline into the replaceable use-case
   paths declared by `workbench.template.json`.
3. Add project pipeline, evaluation, and agent-version configurations.
4. Run one exact benchmark example before a broader evaluation.
5. Use `EvalRunbook.md` and the root skills under `.agents/skills/`.

Run repository commands through `uv run`. Reusable libraries are editable local
source, but coding agents must obtain user approval before modifying them.
""",
        encoding="utf-8",
    )


def _write_eval_runbook(path: Path, spec: BootstrapSpec) -> None:
    """Write a project-neutral runbook that points to configured identities."""
    path.write_text(
        f"""# {spec.project.name} Eval Runbook

<!-- agent-workbench-eval-runbook-status: bootstrap-placeholder -->

**Status:** Bootstrap placeholder. Do not run an eval from this file until the
first evaluable pipeline, agent policy, and evaluation profile have replaced
this marker with explicit validated commands.

The project default is benchmark `{spec.benchmarks.default.key}` version
`{spec.benchmarks.default.version}` with model
`{spec.model_catalog.default_model}`.

Before running an eval:

1. finish the use-case pipeline and evaluation profile;
2. validate `workbench.project.json` and `models.yaml`;
3. authenticate to the configured read-only Benchmark Studio data plane; and
4. use `$run-use-case-evals` to select the full benchmark, explicit units, or a
   named use-case section.

`$benchmark-pipeline-port` records the exact-example control-pipeline command.
`$agent-eval-builder` finalizes this runbook after the first evaluation profile
exists. Do not copy commands from the reference implementation.
""",
        encoding="utf-8",
    )


def _environment_template(spec: BootstrapSpec) -> str:
    """Render identity values and credential placeholders without secrets."""
    studio = spec.benchmark_studio
    lines = [
        "# Generated non-secret project and Benchmark Studio identity",
        f"APP_PROJECT_KEY={studio.project_key}",
        f"AZURE_POSTGRES_HOST={studio.postgres_host}",
        f"AZURE_POSTGRES_DATABASE={studio.postgres_database}",
        "AZURE_POSTGRES_USER=<entra-user-or-group-name>",
        f"AZURE_STORAGE_ACCOUNT_URL={studio.storage_account_url}",
        f"AZURE_STORAGE_CONTAINER={studio.storage_container}",
        "",
        "# DefaultAzureCredential supplies short-lived PostgreSQL and Blob tokens.",
        "# Use a published-data database reader and Storage Blob Data Reader.",
        "",
        "# Model-provider credentials; populate only those required by models.yaml.",
        "AZURE_OPENAI_ENDPOINT=<azure-openai-endpoint>",
        "AZURE_OPENAI_API_KEY=<azure-openai-api-key>",
        "OPENAI_API_VERSION=<azure-openai-api-version>",
        "ANTHROPIC_API_KEY=<anthropic-api-key>",
        "ANTHROPIC_FOUNDRY_API_KEY=<anthropic-foundry-api-key>",
        "ANTHROPIC_FOUNDRY_RESOURCE=<anthropic-foundry-resource>",
        "GOOGLE_API_KEY=<google-api-key>",
        "OPENROUTER_API_KEY=<openrouter-api-key>",
        "LOGFIRE_TOKEN=<optional-logfire-token>",
        "",
    ]
    return "\n".join(lines)


def _project_context(spec: BootstrapSpec) -> str:
    """Create prompts for durable use-case facts without inventing them."""
    return f"""# {spec.project.name} Use-Case Context

Project key: `{spec.project.key}`  
Use-case key: `{spec.project.use_case_key}`

Document durable, reviewed context here before porting or building pipelines:

- business outcome and decision being supported;
- unit identity and decision-timestamp semantics;
- source systems and evidence meaning;
- expected structured output and label semantics;
- domain terminology, operating constraints, and safety boundaries; and
- representative examples and known edge cases.

Do not use this file as an implementation log.
"""


def _write_use_case_placeholders(root: Path) -> None:
    """Write import-safe extension points for the not-yet-ported use case."""
    (root / "src/evidence/__init__.py").write_text(
        '''"""Project-owned evidence adapter extension point."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src.benchmarks.models import BenchmarkExample


class ProjectEvidenceAdapter(Protocol):
    def build_view(
        self,
        *,
        benchmark_key: str,
        benchmark_version_id: str,
        version_number: int,
        example: BenchmarkExample,
    ) -> dict[str, Any]: ...


def create_project_evidence_adapter(project_root: Path) -> ProjectEvidenceAdapter:
    raise RuntimeError(
        "Port the use-case evidence adapter before starting the eval explorer."
    )
''',
        encoding="utf-8",
    )


def _validate_reference_leaks(
    root: Path, manifest: TemplateOwnershipManifest
) -> None:
    """Reject reference identifiers in generated project-facing paths."""
    findings: list[str] = []
    suffixes = {".json", ".md", ".py", ".toml", ".ts", ".tsx", ".yaml", ".yml"}
    for relative in manifest.reference_reset.leak_scan_paths:
        path = _template_target(root, relative)
        if not path.exists():
            continue
        candidates = (path,) if path.is_file() else tuple(path.rglob("*"))
        for candidate in candidates:
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or candidate.suffix.lower() not in suffixes
            ):
                continue
            try:
                content = candidate.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue
            matched = [
                term
                for term in manifest.reference_reset.forbidden_terms
                if term in content
            ]
            if matched:
                findings.append(
                    f"{candidate.relative_to(root)} ({', '.join(sorted(matched))})"
                )
    if findings:
        raise ValueError(
            "Generated project retains reference identifiers: "
            + "; ".join(sorted(findings))
        )


def _run_git(
    arguments: list[str],
    *,
    cwd: Path | None = None,
) -> str:
    """Run Git non-interactively and translate failures into operator errors."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = str(error.stderr).strip()
        suffix = f": {detail}" if detail else ""
        raise ValueError(
            f"Git command failed ({' '.join(arguments)}){suffix}"
        ) from error
    return result.stdout
