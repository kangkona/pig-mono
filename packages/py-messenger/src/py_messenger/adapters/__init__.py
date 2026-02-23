"""Platform adapters."""

from .slack import SlackAdapter
from .discord import DiscordAdapter
from .telegram import TelegramAdapter
from .whatsapp import WhatsAppAdapter
from .feishu import FeishuAdapter

__all__ = [
    "SlackAdapter",
    "DiscordAdapter",
    "TelegramAdapter",
    "WhatsAppAdapter",
    "FeishuAdapter",
]
