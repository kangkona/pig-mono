"""Pig Messenger - Universal messenger abstraction library."""

from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerThread,
    MessengerType,
    MessengerUser,
)
from pig_messenger.config import (
    DiscordConfig,
    SlackConfig,
    TelegramConfig,
    WhatsAppConfig,
)
from pig_messenger.manager import MessengerManager, split_message
from pig_messenger.registry import MessengerRegistry
from pig_messenger.state import MessengerState
from pig_messenger.stores import (
    ConnectionStore,
    CredentialStore,
    WorkspaceAlreadyClaimedError,
    decrypt_value,
    encrypt_value,
)

__all__ = [
    # Base
    "BaseMessengerAdapter",
    "IncomingMessage",
    "MessengerCapabilities",
    "MessengerThread",
    "MessengerType",
    "MessengerUser",
    # Config
    "DiscordConfig",
    "SlackConfig",
    "TelegramConfig",
    "WhatsAppConfig",
    # Manager
    "MessengerManager",
    "split_message",
    # Registry
    "MessengerRegistry",
    # State
    "MessengerState",
    # Stores
    "ConnectionStore",
    "CredentialStore",
    "WorkspaceAlreadyClaimedError",
    "decrypt_value",
    "encrypt_value",
]

__version__ = "0.2.0"
