"""Tests for repeatable, safe Agent Workbench project initialization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, cast

import pytest
import yaml

from workbench.project_bootstrap import cli
from workbench.project_bootstrap.models import (
    BootstrapSpec,
    TemplateOwnershipManifest,
)
from workbench.project_bootstrap.ownership import resolve_ownership, unowned_paths
from workbench.project_bootstrap.service import initialize_project, validate_project


ROOT = Path(__file__).resolve().parents[2]


def _spec_payload() -> dict[str, object]:
    """Return one complete valid bootstrap input."""
    return {
        "schema_version": 1,
        "project": {
            "key": "acme-pumps",
            "name": "Acme Pump Reliability",
            "distribution_name": "acme-pump-agent",
            "use_case_key": "pump-failure",
            "description": "Agent Workbench for Acme pump reliability",
        },
        "benchmark_studio": {
            "project_key": "acme-pumps",
            "access_mode": "direct_read_only",
            "postgres_host": "acme-benchmarks.postgres.database.azure.com",
            "postgres_database": "benchmark_studio",
            "storage_account_url": "https://acmebenchmarks.blob.core.windows.net",
            "storage_container": "source-snapshots",
        },
        "benchmarks": {
            "default": {"key": "pump-failures", "version": "3"},
            "published": [
                {
                    "key": "pump-failures",
                    "version": "3",
                    "published_contract_schema_version": 2,
                    "label_fields": ["classification", "root_cause"],
                    "evidence_recipe_id": "pump-evidence-v2",
                    "source_snapshot_contract": "azure-blob-sha256-v1",
                }
            ],
        },
        "model_catalog": {
            "default_model": "azure:gpt-test",
            "models": [
                {
                    "id": "azure:gpt-test",
                    "api": "openai_responses",
                    "pricing_key": "azure:gpt-test-standard",
                },
                {"id": "google:gemini-test", "api": "google_generate_content"},
            ],
        },
    }


def _write_spec(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    """Write a bootstrap spec fixture and return its path."""
    path = tmp_path / "bootstrap.json"
    path.write_text(json.dumps(payload or _spec_payload()), encoding="utf-8")
    return path


def _write_template(root: Path) -> None:
    """Create a minimal standard-template-shaped source tree."""
    root.mkdir()
    (root / "pyproject.toml").write_text(
        """[project]
name = "mesh.insights.template"
version = "0.1.0"
description = "Template project"
readme = "README.md"

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
""",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Workbench Template\n", encoding="utf-8")
    (root / "model-pricing.yaml").write_text(
        "schema_version: 1\n"
        "rates:\n"
        "  azure:gpt-test-standard:\n"
        "    version: fixture-v1\n"
        "    currency: USD\n"
        "    input_per_million_tokens: 1.25\n"
        "    output_per_million_tokens: 5.0\n",
        encoding="utf-8",
    )
    (root / "workbench.template.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ownership": [
                    {
                        "path": "packages/mi-core",
                        "owner": "reusable_library",
                        "description": "Reusable pipeline library",
                    },
                    {
                        "path": ".agents/skills",
                        "owner": "root_infrastructure",
                        "description": "Root skills",
                    },
                    {
                        "path": "use_case",
                        "owner": "reference_use_case",
                        "description": "Replaceable use-case implementation",
                    },
                ],
                "reference_reset": {
                    "clear_directories": ["use_case"],
                    "remove_directories": [],
                    "remove_files": [],
                    "leak_scan_paths": ["README.md", "use_case"],
                    "forbidden_terms": ["spirax", "steam trap"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "workbench").mkdir()
    (root / "workbench/__init__.py").touch()
    (root / "workbench/agent_versions").mkdir()
    (root / "workbench/agent_versions/__init__.py").write_text(
        "REUSABLE = True\n", encoding="utf-8"
    )
    (root / "packages/mi-core").mkdir(parents=True)
    (root / "packages/mi-core/keep.py").write_text("REUSABLE = True\n", encoding="utf-8")
    (root / "apps/eval_explorer/web/src").mkdir(parents=True)
    (root / "apps/eval_explorer/server.py").write_text(
        "def main():\n    return None\n", encoding="utf-8"
    )
    (root / "apps/eval_explorer/web/src/main.tsx").write_text(
        "export {};\n", encoding="utf-8"
    )
    (root / ".agents/skills/project-guide").mkdir(parents=True)
    (root / ".agents/skills/project-guide/SKILL.md").write_text(
        "---\nname: project-guide\ndescription: Test guide.\n---\n",
        encoding="utf-8",
    )
    (root / "use_case/docs").mkdir(parents=True)
    (root / "use_case/docs/reference.md").write_text(
        "Spirax steam trap reference\n", encoding="utf-8"
    )
    (root / "use_case/tests").mkdir(parents=True)
    (root / "use_case/tests/test_reference.py").write_text(
        "def test_reference_only():\n    assert False\n",
        encoding="utf-8",
    )
    (root / "tests/workbench").mkdir(parents=True)
    (root / "tests/workbench/test_reusable.py").write_text(
        "def test_reusable_contract():\n    assert True\n",
        encoding="utf-8",
    )
    (root / "tests/architecture").mkdir()
    (root / "tests/architecture/test_repository_skills.py").write_text(
        "from pathlib import Path\n\n"
        "def test_preserved_repository_skill():\n"
        "    root = Path(__file__).resolve().parents[2]\n"
        "    assert (root / '.agents/skills/project-guide/SKILL.md').is_file()\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("REAL_SECRET=do-not-copy\n", encoding="utf-8")
    (root / ".env.local").write_text("OTHER_SECRET=do-not-copy\n", encoding="utf-8")
    (root / "credentials.json").write_text("{}\n", encoding="utf-8")
    (root / "api_key.json").write_text("{}\n", encoding="utf-8")
    (root / "client-secret.pem").write_text("private-key\n", encoding="utf-8")
    (root / "id_rsa").write_text("private-key\n", encoding="utf-8")
    (root / ".netrc").write_text("machine example.test password secret\n")
    (root / ".DS_Store").write_text("generated\n")
    (root / ".ssh").mkdir()
    (root / ".ssh/id_custom").write_text("private-key\n", encoding="utf-8")
    (root / ".env.example").write_text("OLD=<placeholder>\n", encoding="utf-8")
    (root / ".workbench/evals").mkdir(parents=True)
    (root / ".workbench/evals/result.json").write_text("{}\n", encoding="utf-8")
    (root / "apps/eval_explorer/web/node_modules/pkg").mkdir(parents=True)
    (root / "apps/eval_explorer/web/node_modules/pkg/index.js").write_text(
        "generated\n"
    )
    (root / "apps/eval_explorer/web/dist").mkdir()
    (root / "apps/eval_explorer/web/dist/index.html").write_text(
        "generated\n"
    )
    (root / "workbench/example.egg-info").mkdir()
    (root / "workbench/example.egg-info/PKG-INFO").write_text("generated\n")


def _git_template(root: Path) -> str:
    """Commit a template fixture and return its exact revision."""
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "template"], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_bootstrap_spec_rejects_unknown_fields_and_missing_defaults() -> None:
    payload = _spec_payload()
    payload["credential"] = "should-never-be-accepted"
    with pytest.raises(ValueError, match="credential"):
        BootstrapSpec.model_validate(payload)

    payload = _spec_payload()
    payload["model_catalog"]["default_model"] = "azure:not-present"  # type: ignore[index]
    with pytest.raises(ValueError, match="Default model"):
        BootstrapSpec.model_validate(payload)

    payload = _spec_payload()
    payload["model_catalog"]["models"][0]["pricing"] = {  # type: ignore[index]
        "version": "legacy-v1",
        "currency": "USD",
    }
    with pytest.raises(ValueError, match="pricing"):
        BootstrapSpec.model_validate(payload)


def test_non_git_bootstrap_requires_explicit_revision(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    spec = _write_spec(tmp_path)

    with pytest.raises(ValueError, match="requires --template-revision"):
        initialize_project(
            tmp_path / "project",
            spec_path=spec,
            template_source=str(template),
            initialize_git=False,
        )


def test_non_git_bootstrap_renders_and_validates_safe_project(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    spec = _write_spec(tmp_path)
    destination = tmp_path / "project"

    result = initialize_project(
        destination,
        spec_path=spec,
        template_source=str(template),
        template_revision="fixture-v1",
        initialize_git=False,
    )

    assert result["status"] == "initialized"
    assert result["validation"]["project_root"] == str(destination)
    assert not (destination / ".env").exists()
    assert not (destination / ".env.local").exists()
    assert not (destination / "credentials.json").exists()
    assert not (destination / "api_key.json").exists()
    assert not (destination / "client-secret.pem").exists()
    assert not (destination / "id_rsa").exists()
    assert not (destination / ".netrc").exists()
    assert not (destination / ".DS_Store").exists()
    assert not (destination / ".ssh").exists()
    assert not (destination / ".workbench/evals/result.json").exists()
    assert not (destination / "apps/eval_explorer/web/node_modules").exists()
    assert not (destination / "apps/eval_explorer/web/dist").exists()
    assert not (destination / "workbench/example.egg-info").exists()
    assert (destination / ".workbench/evals/.gitkeep").exists()
    assert (destination / "packages/mi-core/keep.py").is_file()
    assert (destination / "workbench/agent_versions/__init__.py").is_file()
    assert (destination / ".agents/skills/project-guide/SKILL.md").is_file()
    assert not (destination / "use_case/docs/reference.md").exists()
    assert (destination / "workbench.template.json").is_file()
    assert (destination / "EVAL_RUNBOOK.md").is_file()
    generated_runbook = (destination / "EVAL_RUNBOOK.md").read_text()
    assert "agent-workbench-eval-runbook-status: bootstrap-placeholder" in (
        generated_runbook
    )
    assert "Do not run an eval from this file" in generated_runbook
    assert "$agent-eval-builder" in generated_runbook
    assert (destination / "use_case/explorer/adapter.tsx").is_file()
    assert "unconfiguredUseCaseAdapter" in (
        destination / "use_case/explorer/adapter.tsx"
    ).read_text()
    assert (destination / "use_case/tests/__init__.py").is_file()
    assert not (destination / "use_case/tests/test_reference.py").exists()
    assert (destination / "tests/workbench/test_reusable.py").is_file()
    assert (
        destination / "tests/architecture/test_repository_skills.py"
    ).is_file()
    reusable_test = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/workbench/test_reusable.py",
            "tests/architecture/test_repository_skills.py",
        ],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert reusable_test.returncode == 0, reusable_test.stdout + reusable_test.stderr
    assert "APP_PROJECT_KEY=acme-pumps" in (destination / ".env.example").read_text()
    generated_readme = (destination / "README.md").read_text()
    normalized_readme = " ".join(generated_readme.split())
    assert generated_readme.startswith("# Acme Pump Reliability\n")
    assert "Use `uv run` for Python commands" in generated_readme
    assert "package manager declared by each non-Python workspace" in normalized_readme
    assert "Run repository commands through `uv run`" not in generated_readme
    assert 'name = "acme-pump-agent"' in (destination / "pyproject.toml").read_text()
    assert (
        yaml.safe_load((destination / "models.yaml").read_text())["default_model"]
        == "azure:gpt-test"
    )
    assert (destination / "model-pricing.yaml").read_text() == (
        template / "model-pricing.yaml"
    ).read_text()
    assert validate_project(destination)["status"] == "valid"


def test_real_template_bootstrap_preserves_runnable_skill_contract(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template"
    shutil.copytree(
        ROOT,
        template,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".coverage",
            "*.egg-info",
            ".workbench",
            "build",
            "dist",
        ),
    )
    destination = tmp_path / "generated"
    spec = _spec_payload()
    model_catalog = cast(dict[str, Any], spec["model_catalog"])
    models = cast(list[dict[str, Any]], model_catalog["models"])
    models[0].pop("pricing_key")

    initialize_project(
        destination,
        spec_path=_write_spec(tmp_path, spec),
        template_source=str(template),
        template_revision="working-tree-test",
        initialize_git=False,
    )

    preserved_test = destination / "tests/architecture/test_repository_skills.py"
    assert preserved_test.is_file()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
                "-q",
                str(preserved_test),
                "tests/architecture/test_architecture_boundaries.py",
                "tests/architecture/test_project_layout.py",
                "packages/eval-core/tests",
                "tests/workbench",
            ],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    imports = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from evaluation import build_default_grader_registry; "
                "from workbench.apps.eval_explorer import build_app; "
                "from use_case.evidence import create_project_evidence_adapter; "
                "assert build_default_grader_registry().resolve('core.exact', 1)"
            ),
        ],
        cwd=destination,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(destination)},
    )
    assert imports.returncode == 0, imports.stdout + imports.stderr

    for module in (
        "workbench.project_bootstrap.cli",
        "workbench.eval_lifecycle.cli",
        "workbench.evals.eval_orchestration",
        "workbench.pipelines.pipeline_run_from_yaml",
        "apps.eval_explorer.server",
    ):
        help_result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=destination,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(destination)},
        )
        assert help_result.returncode == 0, help_result.stdout + help_result.stderr

    unconfigured_commands = (
        [sys.executable, "-m", "workbench.evals.eval_orchestration"],
        [
            sys.executable,
            "-m",
            "workbench.pipelines.pipeline_run_from_yaml",
            "--benchmark-key",
            "unconfigured",
            "--example-id",
            "unconfigured",
        ],
    )
    for command in unconfigured_commands:
        result = subprocess.run(
            command,
            cwd=destination,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(destination)},
        )
        assert result.returncode == 2
        assert "Use case not configured" in result.stderr
        assert not (destination / ".workbench/evals/working").exists()

    os.symlink(
        ROOT / "apps/eval_explorer/web/node_modules",
        destination / "apps/eval_explorer/web/node_modules",
        target_is_directory=True,
    )
    os.symlink(
        ROOT / "apps/eval_explorer/web/node_modules",
        destination / "node_modules",
        target_is_directory=True,
    )
    frontend_bin = ROOT / "apps/eval_explorer/web/node_modules/.bin"
    frontend_commands = (
        [str(frontend_bin / "vitest"), "run"],
        [str(frontend_bin / "tsc"), "--noEmit"],
        [str(frontend_bin / "vite"), "build"],
        ["node", "scripts/check-evidence-bundle.mjs"],
    )
    for command in frontend_commands:
        frontend = subprocess.run(
            command,
            cwd=destination / "apps/eval_explorer/web",
            check=False,
            capture_output=True,
            text=True,
        )
        assert frontend.returncode == 0, frontend.stdout + frontend.stderr


def test_git_url_and_ref_record_exact_commit_and_create_new_repo(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template"
    _write_template(template)
    revision = _git_template(template)
    spec = _write_spec(tmp_path)
    destination = tmp_path / "project"

    result = initialize_project(
        destination,
        spec_path=spec,
        template_source=template.as_uri(),
        template_ref="main",
    )

    contract = json.loads((destination / "workbench.project.json").read_text())
    assert result["template_revision"] == revision
    assert contract["template"] == {"source": template.as_uri(), "revision": revision}
    assert (destination / ".git").is_dir()
    assert (
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=destination,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "true"
    )


def test_non_empty_destination_is_unchanged(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    destination = tmp_path / "project"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        initialize_project(
            destination,
            spec_path=_write_spec(tmp_path),
            template_source=str(template),
            template_revision="fixture-v1",
            initialize_git=False,
        )
    assert marker.read_text() == "keep me"


def test_validation_rejects_project_identity_drift(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    destination = tmp_path / "project"
    initialize_project(
        destination,
        spec_path=_write_spec(tmp_path),
        template_source=str(template),
        template_revision="fixture-v1",
        initialize_git=False,
    )
    pyproject = destination / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace("acme-pump-agent", "wrong-project"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match"):
        validate_project(destination)


def test_validation_accepts_local_root_environment_file(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    destination = tmp_path / "project"
    initialize_project(
        destination,
        spec_path=_write_spec(tmp_path),
        template_source=str(template),
        template_revision="fixture-v1",
        initialize_git=False,
    )
    (destination / ".env").write_text("LOCAL_SECRET=developer-only\n", encoding="utf-8")

    assert validate_project(destination)["status"] == "valid"


def test_validation_rejects_reference_identity_leak(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    destination = tmp_path / "project"
    initialize_project(
        destination,
        spec_path=_write_spec(tmp_path),
        template_source=str(template),
        template_revision="fixture-v1",
        initialize_git=False,
    )
    (destination / "use_case/docs/leak.md").write_text(
        "Copied from Spirax.", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="retains reference identifiers"):
        validate_project(destination)


def test_template_manifest_rejects_unsafe_reset_path(tmp_path: Path) -> None:
    template = tmp_path / "template"
    _write_template(template)
    manifest_path = template / "workbench.template.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["reference_reset"]["clear_directories"] = ["../outside"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="normalized and relative"):
        initialize_project(
            tmp_path / "project",
            spec_path=_write_spec(tmp_path),
            template_source=str(template),
            template_revision="fixture-v1",
            initialize_git=False,
        )


def test_template_manifest_covers_reusable_mvp_workbench_surfaces() -> None:
    manifest = json.loads(
        (ROOT / "workbench.template.json").read_text(encoding="utf-8")
    )
    ownership = {item["path"]: item["owner"] for item in manifest["ownership"]}

    assert ownership["examples"] == "root_infrastructure"
    assert ownership["workbench"] == "reusable_workbench"
    assert ownership["apps"] == "root_infrastructure"
    assert ownership["packages/mi-core"] == "reusable_library"
    assert ownership["tests"] == "reusable_workbench"
    assert ownership["use_case"] == "reference_use_case"


def test_template_ownership_uses_the_longest_matching_prefix() -> None:
    manifest = TemplateOwnershipManifest.model_validate_json(
        (ROOT / "workbench.template.json").read_text(encoding="utf-8")
    )

    reusable = resolve_ownership("workbench/evals/run_store.py", manifest.ownership)
    reference = resolve_ownership(
        "use_case/evidence/spirax.py",
        manifest.ownership,
    )
    reference_test = resolve_ownership(
        "use_case/tests/test_v1_3_workflow.py",
        manifest.ownership,
    )

    assert reusable is not None and reusable.path == "workbench"
    assert reference is not None and reference.path == "use_case"
    assert reference_test is not None and reference_test.path == "use_case"


def test_template_manifest_covers_every_repository_file() -> None:
    manifest = TemplateOwnershipManifest.model_validate_json(
        (ROOT / "workbench.template.json").read_text(encoding="utf-8")
    )
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    files = tuple(
        path
        for path in completed.stdout.splitlines()
        if path and (ROOT / path).is_file()
    )

    assert unowned_paths(files, manifest) == ()


def test_cli_emits_machine_readable_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    template = tmp_path / "template"
    _write_template(template)
    destination = tmp_path / "project"

    exit_code = cli.main(
        [
            "--json",
            "init",
            str(destination),
            "--spec",
            str(_write_spec(tmp_path)),
            "--template-source",
            str(template),
            "--template-revision",
            "fixture-v1",
            "--no-git",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "initialized"
