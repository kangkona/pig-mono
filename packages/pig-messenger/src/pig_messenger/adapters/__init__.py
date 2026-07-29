"""Platform adapters.

Each adapter has optional dependencies (slack-sdk, discord.py, etc.).
Imports are lazy so you only need the deps for the adapters you use.
"""

from typing import Any

__all__ = [
    "SlackAdapter",
    "DiscordAdapter",
    "TelegramAdapter",
    "WhatsAppAdapter",
    "FeishuAdapter",
]


def __getattr__(name: str) -> Any:
    if name == "SlackAdapter":
        from .slack import SlackMessengerAdapter

        return SlackMessengerAdapter
    if name == "DiscordAdapter":
        from .discord import DiscordMessengerAdapter

        return DiscordMessengerAdapter
    if name == "TelegramAdapter":
        from .telegram import TelegramMessengerAdapter

        return TelegramMessengerAdapter
    if name == "WhatsAppAdapter":
        from .whatsapp import WhatsAppMessengerAdapter

        return WhatsAppMessengerAdapter
    if name == "FeishuAdapter":
        from .feishu import FeishuAdapter

        return FeishuAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
