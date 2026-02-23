"""Data models for web UI."""

from typing import Literal, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A chat message."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request from client."""

    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response to client."""

    content: str
    role: Literal["assistant"] = "assistant"
    conversation_id: Optional[str] = None


class StreamChunk(BaseModel):
    """Streaming response chunk."""

    type: Literal["start", "token", "done", "error"]
    content: Optional[str] = None
    error: Optional[str] = None
