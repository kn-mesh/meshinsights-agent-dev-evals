"""Shared conservative secret detection for local evaluation artifacts."""

from __future__ import annotations

from pathlib import PurePath
import re


_SENSITIVE_EXACT_NAMES = frozenset(
    {
        ".env",
        ".git-credentials",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "application_default_credentials.json",
        "azureauth.json",
        "client_secret.json",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "service-account.json",
        "secrets.json",
    }
)
_SENSITIVE_DIRECTORY_NAMES = frozenset(
    {".aws", ".azure", ".gnupg", ".kube", ".ssh", "credentials", "secrets"}
)
_SENSITIVE_SUFFIXES = (".jks", ".key", ".kdbx", ".p12", ".pem", ".pfx")
_SENSITIVE_STEMS = re.compile(
    r"(?:^|[._-])(?:api[_-]?key|client[_-]?secret|credential|password|"
    r"private[_-]?key|service[_-]?account|token)(?:$|[._-])",
    re.IGNORECASE,
)
_SENSITIVE_KEY_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "authorization_header",
        "client_secret",
        "connection_string",
        "credential",
        "database_url",
        "database_uri",
        "password",
        "private_key",
        "sas_token",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_NORMALIZED_KEYS = frozenset(
    re.sub(r"[^a-z0-9]", "", key) for key in _SENSITIVE_KEY_NAMES
)
_SENSITIVE_KEY_SUFFIXES = (
    "apikey",
    "authorization",
    "authorizationheader",
    "connectionstring",
    "credential",
    "password",
    "privatekey",
    "secret",
    "token",
)


def is_sensitive_path(path: str | PurePath) -> bool:
    """Return whether a relative artifact path looks credential-bearing."""
    pure = PurePath(path)
    lowered_parts = tuple(part.lower() for part in pure.parts)
    if any(part in _SENSITIVE_DIRECTORY_NAMES for part in lowered_parts[:-1]):
        return True
    name = pure.name.lower()
    return (
        name in _SENSITIVE_EXACT_NAMES
        or name.startswith(".env")
        or name.startswith("secrets.")
        or (name.startswith("id_") and not name.endswith(".pub"))
        or name.endswith(_SENSITIVE_SUFFIXES)
        or bool(_SENSITIVE_STEMS.search(name))
    )


def is_sensitive_key(key: str) -> bool:
    """Return whether a structured field name normally contains a secret."""
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _SENSITIVE_NORMALIZED_KEYS or normalized.endswith(
        _SENSITIVE_KEY_SUFFIXES
    )

