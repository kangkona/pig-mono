"""Universal message format.

DEPRECATED: This module is kept for backward compatibility.
Use pig_messenger.base instead.
"""

import warnings
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

warnings.warn(
    "pig_messenger.message is deprecated. Use pig_messenger.base instead.",
    DeprecationWarning,
    stacklevel=2,
)


class Attachment(BaseModel):
    """Message attachment."""

    id: str
    filename: str
    content_type: str
    size: int
    url: str | None = None
    data: bytes | None = None


class UniversalMessage(BaseModel):
    """Platform-agnostic message format."""

    # Identity
    id: str = Field(description="Message ID")
    platform: str = Field(description="Platform name (slack, discord, etc.)")

    # Location
    channel_id: str = Field(description="Channel/chat ID")
    channel_name: str | None = None
    thread_id: str | None = None

    # Sender
    user_id: str = Field(description="User ID")
    username: str = Field(description="User display name")
    user_email: str | None = None

    # Content
    text: str = Field(description="Message text")
    attachments: list[Attachment] = Field(default_factory=list)

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_mention: bool = Field(default=False, description="Is bot mentioned")
    is_dm: bool = Field(default=False, description="Is direct message")
    is_thread: bool = Field(default=False, description="Is in thread")

    # Original
    raw_data: dict[str, Any] = Field(default_factory=dict, description="Platform-specific data")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class UniversalResponse(BaseModel):
    """Platform-agnostic response format."""

    text: str
    attachments: list[Attachment] = Field(default_factory=list)
    reply_to_thread: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)
