"""Hosted evidence storage clients."""

from src.storage.azure_blob import AzureBlobEvidenceStore, EvidenceStore

__all__ = ["AzureBlobEvidenceStore", "EvidenceStore"]
