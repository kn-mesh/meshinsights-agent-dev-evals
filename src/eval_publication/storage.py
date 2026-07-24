"""Azure create-only storage adapter for eval publication bundles."""

from __future__ import annotations

import os
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from src.storage.azure_blob import AZURE_BLOB_SERVICE_API_VERSION


class PublicationStore(Protocol):
    """Small storage contract used by the publication transaction."""

    def create(self, blob_name: str, content: bytes) -> None: ...

    def read(self, blob_name: str) -> bytes: ...


class AzureBlobPublicationStore:
    """Create and verify blobs in a dedicated eval-results container."""

    def __init__(
        self,
        *,
        account_url: str | None = None,
        container: str | None = None,
        credential: Any | None = None,
        container_client: Any | None = None,
    ) -> None:
        if container_client is not None:
            self._container = container_client
            return
        resolved_account_url = (
            (account_url or os.getenv("AZURE_EVAL_RESULTS_ACCOUNT_URL", ""))
            .strip()
            .rstrip("/")
        )
        resolved_container = (
            container or os.getenv("AZURE_EVAL_RESULTS_CONTAINER", "")
        ).strip()
        if not resolved_account_url.startswith("https://"):
            raise ValueError(
                "AZURE_EVAL_RESULTS_ACCOUNT_URL must be an HTTPS Azure Blob URL."
            )
        if not resolved_container:
            raise ValueError("AZURE_EVAL_RESULTS_CONTAINER is required.")
        service = BlobServiceClient(
            account_url=resolved_account_url,
            credential=credential or DefaultAzureCredential(),
            api_version=AZURE_BLOB_SERVICE_API_VERSION,
        )
        self._container = service.get_container_client(resolved_container)

    def create(self, blob_name: str, content: bytes) -> None:
        """Create one blob conditionally; never overwrite an existing name."""
        self._container.upload_blob(
            name=blob_name,
            data=content,
            overwrite=False,
        )

    def read(self, blob_name: str) -> bytes:
        """Download one just-created blob for byte-for-byte verification."""
        return self._container.download_blob(blob_name).readall()
