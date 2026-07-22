"""Tests for shared conservative local-artifact secret detection."""

from evaluation import is_sensitive_key, is_sensitive_path


def test_sensitive_path_policy_covers_common_credential_names() -> None:
    for path in (
        ".env.production",
        ".ssh/id_ed25519",
        "config/api_key.json",
        "config/client-secret.pem",
        "private-key.txt",
        "azureauth.json",
    ):
        assert is_sensitive_path(path), path

    assert is_sensitive_path(".env.example")
    assert not is_sensitive_path("src/tokenizer.py")


def test_sensitive_key_policy_covers_nested_configuration_keys() -> None:
    assert is_sensitive_key("service_api_key")
    assert is_sensitive_key("authorizationHeader")
    assert is_sensitive_key("database-url")
    assert not is_sensitive_key("benchmark_key")
