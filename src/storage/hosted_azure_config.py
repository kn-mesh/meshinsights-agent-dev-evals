"""Resolve deployed Azure Blob configuration without using local Azurite values."""

from __future__ import annotations

import subprocess


def load_hosted_blob_configuration(
    *,
    resource_group: str,
    container_app: str,
    container_name: str = "source-snapshots",
) -> tuple[str, str]:
    """Read the deployed storage secret through the caller's Azure CLI identity."""
    command = [
        "az",
        "containerapp",
        "secret",
        "show",
        "--name",
        container_app,
        "--resource-group",
        resource_group,
        "--secret-name",
        "storage-connection-string",
        "--query",
        "value",
        "--output",
        "tsv",
        "--only-show-errors",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise ValueError(
            "Azure CLI is required to resolve hosted benchmark evidence storage."
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "Azure CLI secret lookup failed."
        raise ValueError(
            "Could not resolve hosted benchmark evidence storage: " + detail
        ) from error
    connection_string = result.stdout.strip()
    if not connection_string:
        raise ValueError("Hosted Azure storage connection string was empty.")
    return connection_string, container_name
