"""Read-only, integrity-checked access to immutable Azure Blob evidence."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from src.benchmarks.models import SourceArtifact

AZURE_BLOB_SERVICE_API_VERSION = "2025-11-05"


class EvidenceStore(Protocol):
    """Minimal read-only store contract used by the evidence retriever."""

    def read_verified(self, artifact: SourceArtifact) -> bytes: ...


class AzureBlobEvidenceStore:
    """Download benchmark-frozen artifacts without local storage fallback."""

    def __init__(
        self,
        *,
        connection_string: str | None = None,
        account_url: str | None = None,
        credential: Any | None = None,
        container: str | None = None,
        container_client: Any | None = None,
    ) -> None:
        """Use the labeling product's Azure storage configuration."""
        if container_client is not None:
            self._container = container_client
            return
        resolved_account_url = (
            account_url or os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")
        ).strip().rstrip("/")
        resolved_connection = (
            connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        ).strip()
        resolved_container = (
            container or os.getenv("AZURE_STORAGE_CONTAINER", "")
        ).strip()
        if not resolved_container:
            raise ValueError("AZURE_STORAGE_CONTAINER is required for evidence retrieval.")
        if resolved_account_url:
            service = BlobServiceClient(
                account_url=resolved_account_url,
                credential=credential or DefaultAzureCredential(),
                api_version=AZURE_BLOB_SERVICE_API_VERSION,
            )
            self._container = service.get_container_client(resolved_container)
            return
        if not resolved_connection:
            raise ValueError(
                "AZURE_STORAGE_ACCOUNT_URL or AZURE_STORAGE_CONNECTION_STRING is "
                "required for evidence retrieval."
            )
        service = BlobServiceClient.from_connection_string(
            resolved_connection,
            api_version=AZURE_BLOB_SERVICE_API_VERSION,
        )
        self._container = service.get_container_client(resolved_container)

    def read_verified(self, artifact: SourceArtifact) -> bytes:
        """Download one artifact and enforce its frozen length and SHA-256 hash."""
        try:
            content = self._container.download_blob(artifact.object_key).readall()
        except ResourceNotFoundError as error:
            raise FileNotFoundError(
                f"Benchmark evidence artifact does not exist: {artifact.object_key}"
            ) from error
        if len(content) != artifact.byte_size:
            raise ValueError(
                f"Benchmark evidence byte-size mismatch: {artifact.object_key}"
            )
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != artifact.content_sha256:
            raise ValueError(
                f"Benchmark evidence checksum mismatch: {artifact.object_key}"
            )
        return content
