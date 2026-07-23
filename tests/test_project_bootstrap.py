"""Tests for repeatable, safe Agent Workbench project initialization."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
import yaml

from src.project_bootstrap import cli
from src.project_bootstrap.models import BootstrapSpec
from src.project_bootstrap.service import initialize_project, validate_project


ROOT = Path(__file__).resolve().parents[1]


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
    (root / "model_pricing.yaml").write_text(
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
                        "path": "mi-core",
                        "owner": "reusable_library",
                        "description": "Reusable pipeline library",
                    },
                    {
                        "path": ".agents/skills",
                        "owner": "root_infrastructure",
                        "description": "Root skills",
                    },
                    {
                        "path": "docs/use_case",
                        "owner": "reference_use_case",
                        "description": "Replaceable reference context",
                    },
                ],
                "reference_reset": {
                    "clear_directories": ["docs/use_case"],
                    "remove_directories": [],
                    "remove_files": [],
                    "root_skills_with_project_defaults": [],
                    "leak_scan_paths": ["README.md", "docs/use_case"],
                    "forbidden_terms": ["spirax", "steam trap"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "src").mkdir()
    (root / "src/__init__.py").touch()
    (root / "mi-core").mkdir()
    (root / "mi-core/keep.py").write_text("REUSABLE = True\n", encoding="utf-8")
    (root / ".agents/skills/project-guide").mkdir(parents=True)
    (root / ".agents/skills/project-guide/SKILL.md").write_text(
        "---\nname: project-guide\ndescription: Test guide.\n---\n",
        encoding="utf-8",
    )
    (root / "docs/use_case").mkdir(parents=True)
    (root / "docs/use_case/reference.md").write_text(
        "Spirax steam trap reference\n", encoding="utf-8"
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
    (root / "eval_results").mkdir()
    (root / "eval_results/result.json").write_text("{}\n", encoding="utf-8")
    (root / "www/node_modules/pkg").mkdir(parents=True)
    (root / "www/node_modules/pkg/index.js").write_text("generated\n")
    (root / "www/dist").mkdir()
    (root / "www/dist/index.html").write_text("generated\n")
    (root / "src/example.egg-info").mkdir()
    (root / "src/example.egg-info/PKG-INFO").write_text("generated\n")


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
    assert not (destination / "eval_results/result.json").exists()
    assert not (destination / "www/node_modules").exists()
    assert not (destination / "www/dist").exists()
    assert not (destination / "src/example.egg-info").exists()
    assert (destination / "eval_results/.gitkeep").exists()
    assert (destination / "mi-core/keep.py").is_file()
    assert (destination / ".agents/skills/project-guide/SKILL.md").is_file()
    assert not (destination / "docs/use_case/reference.md").exists()
    assert (destination / "workbench.template.json").is_file()
    assert (destination / "EvalRunbook.md").is_file()
    assert (destination / "www/src/use_case/.gitkeep").is_file()
    assert (destination / "tests/.gitkeep").is_file()
    assert "APP_PROJECT_KEY=acme-pumps" in (destination / ".env.example").read_text()
    assert (
        (destination / "README.md").read_text().startswith("# Acme Pump Reliability\n")
    )
    assert 'name = "acme-pump-agent"' in (destination / "pyproject.toml").read_text()
    assert (
        yaml.safe_load((destination / "models.yaml").read_text())["default_model"]
        == "azure:gpt-test"
    )
    assert validate_project(destination)["status"] == "valid"


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
    (destination / ".env").write_text(
        "LOCAL_SECRET=developer-only\n", encoding="utf-8"
    )

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
    (destination / "docs/use_case/leak.md").write_text(
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
    ownership = {
        item["path"]: item["owner"] for item in manifest["ownership"]
    }

    assert ownership["bootstrap_configs"] == "root_infrastructure"
    assert ownership["model_catalog.py"] == "reusable_workbench"
    assert ownership["src/model_configuration.py"] == "reusable_workbench"
    assert ownership["src/eval_lifecycle"] == "reusable_workbench"


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
