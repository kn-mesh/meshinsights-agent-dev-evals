"""Reusable hosted data-plane identity and Entra-only storage contracts."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest

from workbench.benchmarks.runtime_identity import resolve_hosted_data_plane_identity
from workbench.pipelines import pipeline_run_from_yaml
from workbench.pipelines.pipeline_run_from_yaml import _argument_parser
from workbench.project_bootstrap.models import ProjectContract
from workbench.storage.azure_blob import AzureBlobEvidenceStore


def _project_contract() -> ProjectContract:
    return ProjectContract.model_validate(
        {
            "schema_version": 1,
            "created_at_utc": "2026-07-24T00:00:00Z",
            "template": {"source": "fixture", "revision": "abc123"},
            "project": {
                "key": "pump-workbench",
                "name": "Pump Workbench",
                "distribution_name": "pump-agent",
                "use_case_key": "pump-failure",
                "description": "Pump failure fixture",
            },
            "benchmark_studio": {
                "project_key": "acme-pumps",
                "access_mode": "direct_read_only",
                "postgres_host": "benchmarks.postgres.database.azure.com",
                "postgres_database": "benchmark_studio",
                "storage_account_url": "https://evidence.blob.core.windows.net",
                "storage_container": "source-snapshots",
            },
            "benchmarks": {
                "default": {"key": "pump-failures", "version": "3"},
                "published": [
                    {
                        "key": "pump-failures",
                        "version": "3",
                        "published_contract_schema_version": 2,
                        "label_fields": ["classification"],
                        "evidence_recipe_id": "pump-evidence@v3",
                        "source_snapshot_contract": "arrow-sha256-v1",
                    }
                ],
            },
            "model_catalog": {
                "default_model": "azure:test",
                "models": [{"id": "azure:test", "api": "openai_responses"}],
            },
            "paths": {},
        }
    )


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "APP_PROJECT_KEY": "acme-pumps",
        "AZURE_POSTGRES_HOST": "benchmarks.postgres.database.azure.com",
        "AZURE_POSTGRES_DATABASE": "benchmark_studio",
        "AZURE_POSTGRES_USER": "operator@example.com",
        "AZURE_STORAGE_ACCOUNT_URL": "https://evidence.blob.core.windows.net/",
        "AZURE_STORAGE_CONTAINER": "source-snapshots",
    }
    values.update(overrides)
    return values


def test_hosted_identity_normalizes_and_matches_project_contract() -> None:
    identity = resolve_hosted_data_plane_identity(
        _project_contract(),
        environ=_environment(
            AZURE_POSTGRES_HOST="BENCHMARKS.POSTGRES.DATABASE.AZURE.COM",
            AZURE_STORAGE_ACCOUNT_URL="HTTPS://EVIDENCE.BLOB.CORE.WINDOWS.NET/",
        ),
    )

    assert identity.project_key == "acme-pumps"
    assert identity.postgres_user == "operator@example.com"
    assert (
        identity.storage_account_url
        == "https://evidence.blob.core.windows.net"
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_PROJECT_KEY", "other-project"),
        ("AZURE_POSTGRES_HOST", "other.postgres.database.azure.com"),
        ("AZURE_POSTGRES_DATABASE", "other_database"),
        ("AZURE_STORAGE_ACCOUNT_URL", "https://other.blob.core.windows.net"),
        ("AZURE_STORAGE_CONTAINER", "other-snapshots"),
    ],
)
def test_hosted_identity_rejects_every_project_contract_mismatch(
    name: str,
    value: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="does not match workbench.project.json",
    ):
        resolve_hosted_data_plane_identity(
            _project_contract(),
            environ=_environment(**{name: value}),
        )


def test_hosted_identity_does_not_accept_database_url_or_storage_key_fallbacks() -> None:
    environment = _environment()
    environment.pop("AZURE_POSTGRES_HOST")
    environment.pop("AZURE_STORAGE_ACCOUNT_URL")
    environment["DATABASE_URL"] = "postgresql://local.invalid/test"
    environment["AZURE_STORAGE_CONNECTION_STRING"] = "not-a-real-secret"

    with pytest.raises(ValueError, match="AZURE_POSTGRES_HOST"):
        resolve_hosted_data_plane_identity(
            _project_contract(),
            environ=environment,
        )


def test_blob_store_ignores_ambient_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER", "source-snapshots")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "not-a-real-secret")

    with pytest.raises(
        ValueError,
        match="AZURE_STORAGE_ACCOUNT_URL is required",
    ):
        AzureBlobEvidenceStore()


def test_exact_example_cli_exposes_explicit_blob_identity_flags() -> None:
    parsed: Any = _argument_parser().parse_args(
        [
            "use_case/pipeline_configs/example.ppln",
            "--benchmark-key",
            "pump-failures",
            "--example-id",
            "example-1",
            "--azure-storage-account-url",
            "https://evidence.blob.core.windows.net",
            "--azure-storage-container",
            "source-snapshots",
        ]
    )

    assert (
        parsed.azure_storage_account_url
        == "https://evidence.blob.core.windows.net"
    )
    assert parsed.azure_storage_container == "source-snapshots"


def test_exact_example_cli_rejects_identity_mismatch_before_catalog_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = tmp_path / "pipeline.ppln"
    pipeline.write_text("{}\n", encoding="utf-8")
    (tmp_path / "workbench.project.json").write_text(
        _project_contract().model_dump_json(),
        encoding="utf-8",
    )
    called = False

    def fail_if_called(**_: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("catalog access must follow identity validation")

    monkeypatch.setattr(
        pipeline_run_from_yaml,
        "bootstrap_environment",
        lambda: None,
    )
    monkeypatch.setattr(
        pipeline_run_from_yaml,
        "load_benchmark_example",
        fail_if_called,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pipeline-run",
            str(pipeline),
            "--project-key",
            "acme-pumps",
            "--azure-postgres-host",
            "benchmarks.postgres.database.azure.com",
            "--azure-postgres-database",
            "benchmark_studio",
            "--azure-postgres-user",
            "operator@example.com",
            "--azure-storage-account-url",
            "https://other.blob.core.windows.net",
            "--azure-storage-container",
            "source-snapshots",
            "--benchmark-key",
            "pump-failures",
            "--benchmark-version",
            "3",
            "--example-id",
            "example-1",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        pipeline_run_from_yaml.main()

    assert raised.value.code == 2
    assert called is False
