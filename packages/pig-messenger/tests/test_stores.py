"""Tests for messenger store interfaces and utilities."""

import time

import pytest
from cryptography.fernet import Fernet
from pig_messenger.stores import (
    ConnectionStore,
    CredentialStore,
    WorkspaceAlreadyClaimedError,
    _TTLCache,
    decrypt_value,
    encrypt_value,
)


def test_ttl_cache_get_set():
    """Test TTLCache get and set."""
    cache = _TTLCache()

    cache.set("key1", "value1", ttl=10)
    assert cache.get("key1") == "value1"

    # Non-existent key
    assert cache.get("key2") is None


def test_ttl_cache_expiry():
    """Test TTLCache expiry."""
    cache = _TTLCache()

    cache.set("key1", "value1", ttl=1)
    assert cache.get("key1") == "value1"

    # Wait for expiry
    time.sleep(1.1)
    assert cache.get("key1") is None


def test_ttl_cache_pop():
    """Test TTLCache pop."""
    cache = _TTLCache()

    cache.set("key1", "value1", ttl=10)
    value = cache.pop("key1")
    assert value == "value1"

    # Key should be removed
    assert cache.get("key1") is None

    # Pop non-existent key
    assert cache.pop("key2") is None


def test_ttl_cache_keys_with_prefix():
    """Test TTLCache keys_with_prefix."""
    cache = _TTLCache()

    cache.set("user:1", "data1", ttl=10)
    cache.set("user:2", "data2", ttl=10)
    cache.set("session:1", "data3", ttl=10)

    keys = cache.keys_with_prefix("user:")
    assert len(keys) == 2
    assert "user:1" in keys
    assert "user:2" in keys


def test_ttl_cache_delete_matching():
    """Test TTLCache delete_matching."""
    cache = _TTLCache()

    cache.set("user:1", "data1", ttl=10)
    cache.set("user:2", "data2", ttl=10)
    cache.set("session:1", "data3", ttl=10)

    deleted = cache.delete_matching("user:")
    assert deleted == 2

    # User keys should be gone
    assert cache.get("user:1") is None
    assert cache.get("user:2") is None

    # Session key should remain
    assert cache.get("session:1") == "data3"


def test_encrypt_decrypt_value():
    """Test encrypt and decrypt utilities."""
    # Generate a key
    key = Fernet.generate_key().decode()

    value = "secret_token_123"
    encrypted = encrypt_value(value, key)

    # Encrypted should be different
    assert encrypted != value

    # Decrypt should return original
    decrypted = decrypt_value(encrypted, key)
    assert decrypted == value


def test_encrypt_decrypt_with_env(monkeypatch):
    """Test encrypt/decrypt using env var."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("MESSENGER_ENCRYPTION_KEY", key)

    value = "secret_token_456"
    encrypted = encrypt_value(value)
    decrypted = decrypt_value(encrypted)

    assert decrypted == value


def test_encrypt_no_key():
    """Test encrypt without key raises error."""
    with pytest.raises(ValueError, match="MESSENGER_ENCRYPTION_KEY not set"):
        encrypt_value("value")


def test_decrypt_no_key():
    """Test decrypt without key raises error."""
    with pytest.raises(ValueError, match="MESSENGER_ENCRYPTION_KEY not set"):
        decrypt_value("encrypted")


def test_workspace_already_claimed_error():
    """Test WorkspaceAlreadyClaimedError."""
    error = WorkspaceAlreadyClaimedError("Workspace claimed")
    assert str(error) == "Workspace claimed"


def test_credential_store_interface():
    """Test CredentialStore is abstract."""
    with pytest.raises(TypeError):
        CredentialStore()  # type: ignore


def test_connection_store_interface():
    """Test ConnectionStore is abstract."""
    with pytest.raises(TypeError):
        ConnectionStore()  # type: ignore
