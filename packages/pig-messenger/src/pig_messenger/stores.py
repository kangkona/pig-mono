"""Store interfaces for credentials and connections with encryption utilities."""

import os
import time
from abc import ABC, abstractmethod
from typing import Any

try:
    from cryptography.fernet import Fernet  # type: ignore[import-not-found]
except ImportError:
    Fernet = None  # type: ignore[assignment]


class WorkspaceAlreadyClaimedError(Exception):
    """Raised when workspace is already connected to a different user."""

    pass


class CredentialStore(ABC):
    """Abstract credential store for bot tokens."""

    @abstractmethod
    async def get_bot_token(self, messenger_type: str, workspace_id: str) -> str | None:
        """Get bot token for workspace.

        Args:
            messenger_type: Platform type
            workspace_id: Workspace ID

        Returns:
            Bot token or None if not found
        """
        pass

    @abstractmethod
    async def store_credentials(
        self, messenger_type: str, workspace_id: str, credentials: dict[str, Any]
    ) -> None:
        """Store credentials for workspace.

        Args:
            messenger_type: Platform type
            workspace_id: Workspace ID
            credentials: Credential data
        """
        pass

    @abstractmethod
    async def invalidate_cache(self, messenger_type: str, workspace_id: str) -> None:
        """Invalidate cached credentials (for token rotation).

        Args:
            messenger_type: Platform type
            workspace_id: Workspace ID
        """
        pass


class ConnectionStore(ABC):
    """Abstract connection store for messenger connections."""

    @abstractmethod
    async def get_owner(self, messenger_type: str, channel_id: str) -> str | None:
        """Get owner user ID for channel.

        Args:
            messenger_type: Platform type
            channel_id: Channel ID

        Returns:
            User ID or None if not found
        """
        pass

    @abstractmethod
    async def create_connection(
        self,
        messenger_type: str,
        channel_id: str,
        user_id: str,
        workspace_id: str,
        metadata: dict[str, Any],
    ) -> str:
        """Create messenger connection.

        Args:
            messenger_type: Platform type
            channel_id: Channel ID
            user_id: User ID
            workspace_id: Workspace ID
            metadata: Connection metadata

        Returns:
            Connection ID

        Raises:
            WorkspaceAlreadyClaimedError: If workspace already connected to different user
        """
        pass

    @abstractmethod
    async def revoke_connection(self, messenger_type: str, channel_id: str) -> bool:
        """Revoke messenger connection.

        Args:
            messenger_type: Platform type
            channel_id: Channel ID

        Returns:
            True if revoked
        """
        pass

    @abstractmethod
    async def list_connections(self, user_id: str) -> list[dict[str, Any]]:
        """List connections for user.

        Args:
            user_id: User ID

        Returns:
            List of connection data dicts
        """
        pass


class _TTLCache:
    """Simple in-memory TTL cache."""

    def __init__(self) -> None:
        """Initialize cache."""
        self._data: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Value or None if expired/not found
        """
        if key not in self._data:
            return None

        value, expiry = self._data[key]
        if time.time() > expiry:
            del self._data[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        expiry = time.time() + ttl
        self._data[key] = (value, expiry)

    def pop(self, key: str) -> Any | None:
        """Remove and return value.

        Args:
            key: Cache key

        Returns:
            Value or None if not found
        """
        if key in self._data:
            value, _ = self._data[key]
            del self._data[key]
            return value
        return None

    def keys_with_prefix(self, prefix: str) -> list[str]:
        """Get all keys with prefix.

        Args:
            prefix: Key prefix

        Returns:
            List of matching keys
        """
        return [k for k in self._data.keys() if k.startswith(prefix)]

    def delete_matching(self, prefix: str) -> int:
        """Delete all keys matching prefix.

        Args:
            prefix: Key prefix

        Returns:
            Number of keys deleted
        """
        keys = self.keys_with_prefix(prefix)
        for key in keys:
            del self._data[key]
        return len(keys)


def encrypt_value(value: str, key: str | None = None) -> str:
    """Encrypt value using Fernet.

    Args:
        value: Value to encrypt
        key: Encryption key (base64 encoded) or None to use env var

    Returns:
        Encrypted value (base64 encoded)
    """
    if Fernet is None:
        raise ImportError("cryptography is required for encryption")

    if key is None:
        key = os.getenv("MESSENGER_ENCRYPTION_KEY")
        if not key:
            raise ValueError("MESSENGER_ENCRYPTION_KEY not set")

    fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str, key: str | None = None) -> str:
    """Decrypt value using Fernet.

    Args:
        encrypted: Encrypted value (base64 encoded)
        key: Encryption key (base64 encoded) or None to use env var

    Returns:
        Decrypted value
    """
    if Fernet is None:
        raise ImportError("cryptography is required for decryption")

    if key is None:
        key = os.getenv("MESSENGER_ENCRYPTION_KEY")
        if not key:
            raise ValueError("MESSENGER_ENCRYPTION_KEY not set")

    fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return fernet.decrypt(encrypted.encode()).decode()
