"""Fail-closed hosted data-plane identity resolution for operator commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os

from workbench.project_bootstrap.models import ProjectContract


@dataclass(frozen=True)
class HostedDataPlaneIdentity:
    """Effective non-secret identities used by one hosted operator command."""

    project_key: str
    postgres_host: str
    postgres_database: str
    postgres_user: str
    storage_account_url: str
    storage_container: str


def resolve_hosted_data_plane_identity(
    project: ProjectContract,
    *,
    project_key: str | None = None,
    postgres_host: str | None = None,
    postgres_database: str | None = None,
    postgres_user: str | None = None,
    storage_account_url: str | None = None,
    storage_container: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> HostedDataPlaneIdentity:
    """Resolve CLI/env inputs and bind them to ``workbench.project.json``."""
    environment = os.environ if environ is None else environ

    def resolve(override: str | None, name: str) -> str:
        return (override or environment.get(name, "")).strip()

    identity = HostedDataPlaneIdentity(
        project_key=resolve(project_key, "APP_PROJECT_KEY"),
        postgres_host=resolve(postgres_host, "AZURE_POSTGRES_HOST").lower(),
        postgres_database=resolve(postgres_database, "AZURE_POSTGRES_DATABASE"),
        postgres_user=resolve(postgres_user, "AZURE_POSTGRES_USER"),
        storage_account_url=resolve(
            storage_account_url, "AZURE_STORAGE_ACCOUNT_URL"
        )
        .rstrip("/")
        .lower(),
        storage_container=resolve(
            storage_container, "AZURE_STORAGE_CONTAINER"
        ).lower(),
    )
    missing = [
        name
        for name, value in (
            ("APP_PROJECT_KEY", identity.project_key),
            ("AZURE_POSTGRES_HOST", identity.postgres_host),
            ("AZURE_POSTGRES_DATABASE", identity.postgres_database),
            ("AZURE_POSTGRES_USER", identity.postgres_user),
            ("AZURE_STORAGE_ACCOUNT_URL", identity.storage_account_url),
            ("AZURE_STORAGE_CONTAINER", identity.storage_container),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "Direct Entra operator execution requires: " + ", ".join(missing)
        )

    studio = project.benchmark_studio
    expected = {
        "APP_PROJECT_KEY": studio.project_key,
        "AZURE_POSTGRES_HOST": studio.postgres_host.lower(),
        "AZURE_POSTGRES_DATABASE": studio.postgres_database,
        "AZURE_STORAGE_ACCOUNT_URL": studio.storage_account_url.rstrip("/").lower(),
        "AZURE_STORAGE_CONTAINER": studio.storage_container.lower(),
    }
    actual = {
        "APP_PROJECT_KEY": identity.project_key,
        "AZURE_POSTGRES_HOST": identity.postgres_host,
        "AZURE_POSTGRES_DATABASE": identity.postgres_database,
        "AZURE_STORAGE_ACCOUNT_URL": identity.storage_account_url,
        "AZURE_STORAGE_CONTAINER": identity.storage_container,
    }
    mismatches = [
        f"{name}={actual[name]!r} (project contract: {expected[name]!r})"
        for name in expected
        if actual[name] != expected[name]
    ]
    if mismatches:
        raise ValueError(
            "Hosted data-plane identity does not match workbench.project.json: "
            + "; ".join(mismatches)
        )
    return identity
