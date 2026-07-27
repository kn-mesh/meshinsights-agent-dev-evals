"""Resolve complete content-addressed agent versions from pipeline source."""

from __future__ import annotations

import ast
from collections.abc import Mapping
import copy
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any

from evaluation import canonical_sha256, is_sensitive_path
from mi.core.registry import (
    PipelineSchemaBuilder,
    RegistryScanner,
    build_registry_index,
    get_record,
    load_pipeline_settings,
)
from mi.core.registry.utils import import_symbol
from mi.core.versioning import declared_version_assets, declared_version_contracts
from pydantic import BaseModel
import yaml

from model_catalog import load_model_catalog, resolve_model_definition
from src.agent_versions.models import (
    AgentVersionManifest,
    AgentVersionPolicy,
    DirtyPolicy,
    ResolvedAgentVersion,
)
from src.evals.run_specs import repository_root


_DEFAULT_NON_EXECUTION_EXCLUSIONS = (
    "src/agent_versions/**",
    "src/benchmarks/**",
    "src/eval_lifecycle/**",
    "src/evals/**",
    "src/model_configuration.py",
    "src/pipelines/**",
    "src/project_bootstrap/**",
)
_COMPONENT_LAYOUT = (
    ("metadata_types", ("metadata_class",), None),
    ("process_data_objects", ("objects", "process"), None),
    ("action_data_objects", ("objects", "action"), None),
    ("retrieve_hydrators", ("retrieve", "hydrator"), None),
    ("retrievers", ("retrieve", "retrievers"), "retriever"),
    ("process_hydrators", ("process", "hydrator"), None),
    ("processors", ("process", "processors"), "processor"),
    ("action_hydrators", ("action", "hydrator"), None),
    ("actions", ("action", "actions"), "action"),
)


def default_policy_path(pipeline_path: Path, *, root: Path | None = None) -> Path:
    """Return the conventional project-owned policy path for a pipeline."""
    project_root = (root or repository_root(pipeline_path.parent)).resolve()
    return project_root / "agent_version_configs" / f"{pipeline_path.stem}.agent.yaml"


def load_agent_version_policy(path: Path) -> AgentVersionPolicy:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Agent-version policy must be a mapping: {path}")
    return AgentVersionPolicy.model_validate(payload)


def validate_runtime_overrides(
    policy: AgentVersionPolicy,
    *,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
) -> tuple[str, str | None]:
    """Resolve defaults and reject overrides outside the frozen policy."""
    requested_model = ai_model or policy.model_policy.default_model
    allowed_models = policy.model_policy.permitted_overrides.models
    if ai_model is not None and (
        not allowed_models or requested_model not in allowed_models
    ):
        raise ValueError(
            f"Model override {requested_model!r} is not permitted by the agent version."
        )
    requested_reasoning = (
        policy.model_policy.default_reasoning_effort
        if ai_reasoning_effort in {None, "default"}
        else ai_reasoning_effort
    )
    allowed_reasoning = policy.model_policy.permitted_overrides.reasoning_efforts
    if ai_reasoning_effort not in {None, "default"} and (
        not allowed_reasoning or requested_reasoning not in allowed_reasoning
    ):
        raise ValueError(
            f"Reasoning override {requested_reasoning!r} is not permitted by "
            "the agent version."
        )
    return requested_model, requested_reasoning


def resolve_agent_version(
    pipeline_path: Path,
    *,
    policy_path: Path | None = None,
    root: Path | None = None,
    dirty_policy: DirtyPolicy = "capture",
) -> ResolvedAgentVersion:
    """Resolve one immutable candidate without executing pipeline components."""
    source_path = pipeline_path.resolve()
    project_root = (root or repository_root(source_path.parent)).resolve()
    policy_source = (
        policy_path or default_policy_path(source_path, root=project_root)
    ).resolve()
    _require_within(project_root, source_path)
    _require_within(project_root, policy_source)
    policy = load_agent_version_policy(policy_source)
    configured_pipeline = (policy_source.parent / policy.source_pipeline).resolve()
    if configured_pipeline != source_path:
        raise ValueError(
            f"Agent policy references {configured_pipeline}, not {source_path}."
        )
    catalog = load_model_catalog(project_root / "models.yaml")
    default_definition = resolve_model_definition(
        policy.model_policy.default_model, catalog
    )
    for allowed_model in policy.model_policy.permitted_overrides.models:
        resolve_model_definition(allowed_model, catalog)

    raw_pipeline = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_pipeline, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    settings, _ = load_pipeline_settings(start=source_path.parent)
    registry = RegistryScanner(project_root, settings).scan()
    schema_builder = PipelineSchemaBuilder(registry, project_root)
    validation_pipeline = copy.deepcopy(raw_pipeline)
    # The benchmark-aware runner converts this source-only shorthand into the
    # regular runtime ``metadata`` entry before invoking PipelineBuilder.
    validation_pipeline.pop("metadata_class", None)
    # Compatibility metadata is hashed as part of the source pipeline but is
    # consumed by the benchmark-aware preflight rather than PipelineBuilder.
    validation_pipeline.pop("benchmark_contract", None)
    schema_builder.model.model_validate(validation_pipeline)
    registry_index = build_registry_index(registry)

    file_roles: dict[Path, list[dict[str, Any]]] = {}
    component_graph: list[dict[str, Any]] = []
    contracts: dict[str, list[dict[str, Any]]] = {}
    _add_file_role(
        file_roles, source_path, role="source_pipeline", logical_name=source_path.stem
    )
    _add_file_role(
        file_roles, policy_source, role="model_policy", logical_name=policy_source.stem
    )

    for stage_index, (section, locator, list_key) in enumerate(_COMPONENT_LAYOUT):
        values = _at_path(raw_pipeline, locator)
        entries: list[tuple[str, dict[str, Any]]]
        if list_key is None:
            if values is None:
                continue
            entries = [(str(values), {})]
        else:
            if not isinstance(values, list):
                raise ValueError(
                    f"Pipeline section {'.'.join(locator)} must be a list."
                )
            entries = []
            for raw_entry in values:
                if not isinstance(raw_entry, dict) or not raw_entry.get(list_key):
                    raise ValueError(f"Invalid component entry in {'.'.join(locator)}.")
                entries.append(
                    (
                        str(raw_entry[list_key]),
                        {
                            key: value
                            for key, value in raw_entry.items()
                            if key != list_key
                        },
                    )
                )
        for order, (component_name, raw_config) in enumerate(entries):
            record = get_record(section, component_name, registry_index)
            component_type = import_symbol(record.import_path, project_root)
            config_type = schema_builder.component_config_type(section, record.name)
            effective_config = (
                {"runtime_injected": True}
                if section == "metadata_types"
                else _effective_config(config_type, raw_config)
            )
            component_source = _record_path(record.file_path, project_root)
            _add_file_role(
                file_roles,
                component_source,
                role="component_source",
                logical_name=record.import_path,
            )
            declarations: list[dict[str, Any]] = []
            for declaration in declared_version_assets(
                component_type, effective_config
            ):
                payload = declaration.model_dump(mode="json")
                if declaration.path is not None:
                    asset_path = (component_source.parent / declaration.path).resolve()
                    _require_within(project_root, asset_path)
                    _add_file_role(
                        file_roles,
                        asset_path,
                        role=declaration.role.value,
                        logical_name=declaration.logical_name,
                        media_type=declaration.media_type,
                        symbol=declaration.symbol,
                    )
                    payload["resolved_path"] = asset_path.relative_to(
                        project_root
                    ).as_posix()
                declarations.append(payload)
            component_contracts = declared_version_contracts(
                component_type, effective_config
            )
            for declaration in component_contracts:
                payload = declaration.model_dump(mode="json")
                contracts.setdefault(declaration.role.value, []).append(payload)
            if section == "actions" and not any(
                declaration.role.value == "action_policy"
                for declaration in component_contracts
            ):
                raise ValueError(
                    f"Terminal action {record.import_path} must declare an action policy."
                )
            schema_type = getattr(component_type, "output_schema", None)
            if isinstance(schema_type, type) and issubclass(schema_type, BaseModel):
                normalized_schema = schema_type.model_json_schema()
                contracts.setdefault("normalized_output_schema", []).append(
                    {
                        "role": "output_schema",
                        "logical_name": (
                            f"{schema_type.__module__}.{schema_type.__qualname__}"
                        ),
                        "value": normalized_schema,
                        "content_sha256": canonical_sha256(normalized_schema),
                    }
                )
            if section == "metadata_types" and issubclass(component_type, BaseModel):
                normalized_schema = component_type.model_json_schema()
                contracts.setdefault("normalized_input_schema", []).append(
                    {
                        "role": "input_schema",
                        "logical_name": record.import_path,
                        "value": normalized_schema,
                        "content_sha256": canonical_sha256(normalized_schema),
                    }
                )
            component_graph.append(
                {
                    "stage_index": stage_index,
                    "section": section,
                    "order": order,
                    "name": component_name,
                    "import_path": record.import_path,
                    "registry_locator_hash": record.hash,
                    "source_path": component_source.relative_to(
                        project_root
                    ).as_posix(),
                    "effective_config": effective_config,
                    "declarations": declarations,
                }
            )

    for asset in policy.additional_assets:
        asset_path = (policy_source.parent / asset.path).resolve()
        _require_within(project_root, asset_path)
        _add_file_role(
            file_roles,
            asset_path,
            role=asset.role,
            logical_name=asset.logical_name,
            media_type=asset.media_type,
        )

    dependency_paths = (
        project_root / "pyproject.toml",
        project_root / "uv.lock",
        project_root / "models.yaml",
        project_root / "model_pricing.yaml",
        project_root / "model_catalog.py",
        project_root / "mi-core/core/pyproject.toml",
        project_root / "agent-dev-eval-core/pyproject.toml",
    )
    for path in dependency_paths:
        if path.is_file():
            _add_file_role(file_roles, path, role="dependency", logical_name=path.name)

    git_identity = _git_identity(project_root)
    deleted_surface_paths: list[str] = []
    if git_identity["git_revision"] is not None:
        dirty_runtime_paths = _dirty_runtime_paths(project_root)
        resolved_runtime_paths = _resolved_local_python_dependencies(
            project_root,
            file_roles,
            known_runtime_paths={relative for relative, _ in dirty_runtime_paths},
        )
        exclusions = (
            *_DEFAULT_NON_EXECUTION_EXCLUSIONS,
            *policy.non_execution_exclusions,
        )
        for relative, exists in dirty_runtime_paths:
            path = (project_root / relative).resolve()
            _reject_sensitive_path(path, project_root)
            if path in file_roles:
                continue
            if any(fnmatch.fnmatch(relative, pattern) for pattern in exclusions):
                continue
            if exists and relative in resolved_runtime_paths:
                _add_file_role(
                    file_roles,
                    path,
                    role="version_surface_guard",
                    logical_name=relative,
                )
            elif not exists and relative in resolved_runtime_paths:
                deleted_surface_paths.append(relative)
            else:
                raise ValueError(
                    "Dirty runtime path is not reachable from the resolved agent "
                    f"graph and is not an approved non-execution exclusion: {relative}"
                )
    blobs: dict[str, bytes] = {}
    asset_entries: list[dict[str, Any]] = []
    overlay_entries: list[dict[str, Any]] = []
    for path in sorted(file_roles):
        if not path.is_file():
            raise ValueError(f"Version asset does not exist: {path}")
        _reject_sensitive_path(path, project_root)
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        relative = path.relative_to(project_root).as_posix()
        base_content = _git_file_bytes(
            project_root, git_identity["git_revision"], relative
        )
        changed = base_content != content
        if changed and dirty_policy == "reject":
            raise ValueError(f"Dirty version-surface path is not allowed: {relative}")
        origin = "git"
        if changed or git_identity["git_revision"] is None:
            origin = "overlay" if git_identity["git_revision"] else "cas"
            blobs[digest] = content
            overlay_entries.append(
                {
                    "operation": "add" if base_content is None else "modify",
                    "path": relative,
                    "base_sha256": (
                        hashlib.sha256(base_content).hexdigest()
                        if base_content is not None
                        else None
                    ),
                    "content_sha256": digest,
                    "byte_size": len(content),
                    "file_mode": path.stat().st_mode & 0o777,
                }
            )
        asset_entries.append(
            {
                "path": relative,
                "origin": origin,
                "content_sha256": digest,
                "byte_size": len(content),
                "file_mode": path.stat().st_mode & 0o777,
                "roles": sorted(
                    file_roles[path], key=lambda item: canonical_sha256(item)
                ),
            }
        )
    for relative in sorted(deleted_surface_paths):
        base_content = _git_file_bytes(
            project_root, git_identity["git_revision"], relative
        )
        if base_content is None:
            continue
        if dirty_policy == "reject":
            raise ValueError(f"Dirty version-surface path is not allowed: {relative}")
        overlay_entries.append(
            {
                "operation": "delete",
                "path": relative,
                "base_sha256": hashlib.sha256(base_content).hexdigest(),
                "content_sha256": None,
                "byte_size": 0,
                "file_mode": None,
            }
        )

    tree_state = (
        "unavailable"
        if git_identity["git_revision"] is None
        else "dirty"
        if overlay_entries
        else "clean"
    )
    resolved_graph_sha256 = canonical_sha256(component_graph)
    model_policy = {
        **policy.model_policy.model_dump(mode="json"),
        "default_provider": default_definition.id.partition(":")[0],
        "default_api": default_definition.api,
    }
    model_policy["policy_sha256"] = canonical_sha256(model_policy)
    evidence_contract = {
        "component_declarations": contracts.get("evidence_recipe", []),
        "project": policy.contracts.get("evidence_recipe", {}),
    }
    if (
        not evidence_contract["component_declarations"]
        or not evidence_contract["project"]
    ):
        raise ValueError(
            "Agent versions require component and project evidence-recipe declarations."
        )
    evidence_recipe_sha256 = canonical_sha256(evidence_contract)
    contract_document = {
        "structured_input": policy.contracts.get("structured_input", {}),
        "structured_output": policy.contracts.get("structured_output", {}),
        "action_policy": {
            "component_declarations": contracts.get("action_policy", []),
            "project": policy.contracts.get("action_policy", {}),
        },
        "evidence_recipe": evidence_contract,
        "evidence_recipe_sha256": evidence_recipe_sha256,
        "component_contracts": contracts,
        "normalized_input_schemas": contracts.get("normalized_input_schema", []),
        "normalized_output_schemas": contracts.get("normalized_output_schema", []),
    }
    pipeline_document = {
        "path": source_path.relative_to(project_root).as_posix(),
        "name": raw_pipeline.get("name"),
        "display_version": raw_pipeline.get("version"),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "canonical_config_sha256": canonical_sha256(raw_pipeline),
        "resolved_graph_sha256": resolved_graph_sha256,
    }
    overlay_document = {"entries": overlay_entries}
    overlay_sha256 = canonical_sha256(overlay_document) if overlay_entries else None
    identity = {
        "source": {
            "repository_id": project_root.name,
            **git_identity,
            "tree_policy": (
                "captured_dirty_surface" if overlay_entries else "clean_version_surface"
            ),
            "tree_state": tree_state,
            "dirty_overlay_sha256": overlay_sha256,
            "dirty_overlay": overlay_document if overlay_entries else None,
        },
        "source_pipeline": pipeline_document,
        "components": component_graph,
        "assets": asset_entries,
        "contracts": contract_document,
        "dependencies": _dependency_identity(project_root),
        "model_policy": model_policy,
        "runtime_contract": {
            "agent_version_contract_version": 1,
            "pipeline_execution_contract_version": 1,
            "compatible_result_schema_versions": [2],
            "registry_schema_version": registry.version,
        },
    }
    manifest = AgentVersionManifest.build(identity)
    return ResolvedAgentVersion(
        manifest=manifest,
        blobs=blobs,
        policy=policy,
        pipeline_path=source_path.relative_to(project_root).as_posix(),
    )


def _at_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _effective_config(
    config_type: type[Any] | None, raw: dict[str, Any]
) -> dict[str, Any]:
    if config_type is None:
        return json.loads(json.dumps(raw, default=str))
    value = config_type(**raw)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return json.loads(json.dumps(value, default=str))


def _record_path(raw: str, root: Path) -> Path:
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    _require_within(root, resolved)
    return resolved


def _add_file_role(
    target: dict[Path, list[dict[str, Any]]],
    path: Path,
    *,
    role: str,
    logical_name: str,
    media_type: str | None = None,
    symbol: str | None = None,
) -> None:
    target.setdefault(path.resolve(), []).append(
        {
            "role": role,
            "logical_name": logical_name,
            "media_type": media_type,
            "symbol": symbol,
        }
    )


def _require_within(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"Version path is outside the repository: {path}") from error


def _reject_sensitive_path(path: Path, root: Path) -> None:
    relative = path.relative_to(root)
    if is_sensitive_path(relative):
        raise ValueError(f"Sensitive path cannot be an agent-version asset: {relative}")


def _resolved_local_python_dependencies(
    root: Path,
    source_paths: Mapping[Path, Any],
    *,
    known_runtime_paths: set[str] | None = None,
) -> set[str]:
    """Resolve local Python imports that can affect the selected agent graph."""
    project_root = root.resolve()
    import_roots = tuple(
        path.resolve()
        for path in (
            project_root / "mi-core/core/src",
            project_root / "agent-dev-eval-core",
            project_root,
        )
        if path.is_dir()
    )
    known_paths = known_runtime_paths or set()
    resolved_paths: set[str] = set()
    queued: list[Path] = [
        path.resolve()
        for path in source_paths
        if path.suffix == ".py" and path.is_file()
    ]
    visited: set[Path] = set()

    while queued:
        source = queued.pop()
        if source in visited:
            continue
        visited.add(source)
        try:
            relative = source.relative_to(project_root).as_posix()
        except ValueError:
            continue
        resolved_paths.add(relative)
        if not source.is_file():
            continue
        package_parts = _package_parts(source, import_roots)
        if package_parts is None:
            continue
        try:
            syntax = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, SyntaxError, UnicodeError) as error:
            raise ValueError(
                f"Could not inspect version-surface imports in {relative}."
            ) from error

        imported_modules: set[tuple[str, ...]] = set()
        for node in ast.walk(syntax):
            if isinstance(node, ast.Import):
                imported_modules.update(
                    tuple(alias.name.split(".")) for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                base = _import_from_parts(node, package_parts)
                if base:
                    imported_modules.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        imported_modules.add((*base, *alias.name.split(".")))
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.fullmatch(
                    r"(?:src|mi|evaluation)(?:\.[A-Za-z_]\w*)+",
                    node.value,
                )
            ):
                # Capture local modules named in lazy-import catalogs.
                imported_modules.add(tuple(node.value.split(".")))

        for imported in imported_modules:
            for dependency in _resolve_local_module(
                imported,
                import_roots=import_roots,
                project_root=project_root,
                known_paths=known_paths,
            ):
                dependency_relative = dependency.relative_to(project_root).as_posix()
                resolved_paths.add(dependency_relative)
                if dependency.is_file() and dependency not in visited:
                    queued.append(dependency)

    return resolved_paths


def _package_parts(
    path: Path,
    import_roots: tuple[Path, ...],
) -> tuple[str, ...] | None:
    for import_root in import_roots:
        try:
            relative = path.relative_to(import_root)
        except ValueError:
            continue
        parts = relative.with_suffix("").parts
        if not parts:
            return ()
        return tuple(parts[:-1])
    return None


def _import_from_parts(
    node: ast.ImportFrom,
    package_parts: tuple[str, ...],
) -> tuple[str, ...]:
    if node.level == 0:
        prefix: tuple[str, ...] = ()
    else:
        parents = node.level - 1
        prefix = package_parts[: max(len(package_parts) - parents, 0)]
    module = tuple(node.module.split(".")) if node.module else ()
    return (*prefix, *module)


def _resolve_local_module(
    module_parts: tuple[str, ...],
    *,
    import_roots: tuple[Path, ...],
    project_root: Path,
    known_paths: set[str],
) -> tuple[Path, ...]:
    if not module_parts:
        return ()
    resolved: list[Path] = []
    for import_root in import_roots:
        module_base = import_root.joinpath(*module_parts)
        candidates = (
            module_base.with_suffix(".py"),
            module_base / "__init__.py",
        )
        target = next(
            (
                candidate
                for candidate in candidates
                if candidate.is_file()
                or _known_project_path(candidate, project_root, known_paths)
            ),
            None,
        )
        if target is None:
            continue
        for parent in target.parents:
            if parent == import_root:
                break
            initializer = parent / "__init__.py"
            if initializer.is_file() or _known_project_path(
                initializer, project_root, known_paths
            ):
                resolved.append(initializer.resolve())
        resolved.append(target.resolve())
        break
    return tuple(dict.fromkeys(resolved))


def _known_project_path(path: Path, root: Path, known_paths: set[str]) -> bool:
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    return relative in known_paths


def _git_identity(root: Path) -> dict[str, str | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return {"git_revision": None, "git_tree": None}
    return {"git_revision": revision or None, "git_tree": tree or None}


def _git_file_bytes(root: Path, revision: str | None, relative: str) -> bytes | None:
    if revision is None:
        return None
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"], cwd=root, capture_output=True
    )
    return result.stdout if result.returncode == 0 else None


def _dirty_runtime_paths(root: Path) -> tuple[tuple[str, bool], ...]:
    """Return changed runtime-surface paths and whether each currently exists."""
    pathspecs = (
        "src",
        "mi-core/core/src/mi",
    )
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "-z", "HEAD", "--", *pathspecs],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    names = {
        raw.decode("utf-8")
        for raw in (*tracked.split(b"\0"), *untracked.split(b"\0"))
        if raw
    }
    selected = []
    for relative in sorted(names):
        selected.append((relative, (root / relative).is_file()))
    return tuple(selected)


def _dependency_identity(root: Path) -> dict[str, Any]:
    def project(path: Path) -> dict[str, Any]:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)["project"]
        return {
            "name": payload["name"],
            "version": payload["version"],
            "source": path.relative_to(root).as_posix(),
        }

    lock = root / "uv.lock"
    return {
        "python": f"{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "lock_path": "uv.lock",
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "project": project(root / "pyproject.toml"),
        "eval_core": project(root / "agent-dev-eval-core/pyproject.toml"),
        "mi_core": project(root / "mi-core/core/pyproject.toml"),
    }
