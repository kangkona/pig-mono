"""Web UI components for AI chat interfaces."""

from .models import ChatMessage, ChatRequest, ChatResponse
from .server import ChatServer

__version__ = "0.2.0"

__all__ = [
    "ChatServer",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
]
