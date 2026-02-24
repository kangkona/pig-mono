"""Platform adapters.

Each adapter has optional dependencies (slack-sdk, discord.py, etc.).
Imports are lazy so you only need the deps for the adapters you use.
"""

__all__ = [
    "SlackAdapter",
    "DiscordAdapter",
    "TelegramAdapter",
    "WhatsAppAdapter",
    "FeishuAdapter",
]


def __getattr__(name: str):
    if name == "SlackAdapter":
        from .slack import SlackAdapter
        return SlackAdapter
    if name == "DiscordAdapter":
        from .discord import DiscordAdapter
        return DiscordAdapter
    if name == "TelegramAdapter":
        from .telegram import TelegramAdapter
        return TelegramAdapter
    if name == "WhatsAppAdapter":
        from .whatsapp import WhatsAppAdapter
        return WhatsAppAdapter
    if name == "FeishuAdapter":
        from .feishu import FeishuAdapter
        return FeishuAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
