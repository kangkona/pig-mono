"""Universal multi-platform bot framework."""

from .bot import MessengerBot
from .platform import MessagePlatform, PlatformConfig
from .message import UniversalMessage, UniversalResponse, Attachment
from .session_manager import MultiPlatformSessionManager

__version__ = "0.0.1"

__all__ = [
    "MessengerBot",
    "MessagePlatform",
    "PlatformConfig",
    "UniversalMessage",
    "UniversalResponse",
    "Attachment",
    "MultiPlatformSessionManager",
]
