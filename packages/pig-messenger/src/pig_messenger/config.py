"""Platform configuration dataclasses with environment variable loading."""

import os
from dataclasses import dataclass
from typing import Protocol


class SecretProvider(Protocol):
    """Protocol for secret providers."""

    def get_secret(self, path: str) -> dict[str, str]:
        """Get secret from provider.

        Args:
            path: Secret path

        Returns:
            Secret data as dict
        """
        ...


class EnvSecretProvider:
    """Default secret provider that reads from environment variables."""

    def get_secret(self, path: str) -> dict[str, str]:
        """Get secret from environment variables.

        Args:
            path: Not used, kept for protocol compatibility

        Returns:
            Empty dict (env vars accessed directly)
        """
        return {}


@dataclass
class SlackConfig:
    """Slack platform configuration."""

    client_id: str
    client_secret: str
    signing_secret: str
    bot_token: str
    app_token: str

    @classmethod
    def from_env(cls, prefix: str = "SLACK_") -> "SlackConfig":
        """Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            SlackConfig instance
        """
        return cls(
            client_id=os.getenv(f"{prefix}CLIENT_ID", ""),
            client_secret=os.getenv(f"{prefix}CLIENT_SECRET", ""),
            signing_secret=os.getenv(f"{prefix}SIGNING_SECRET", ""),
            bot_token=os.getenv(f"{prefix}BOT_TOKEN", ""),
            app_token=os.getenv(f"{prefix}APP_TOKEN", ""),
        )


@dataclass
class DiscordConfig:
    """Discord platform configuration."""

    bot_token: str
    client_id: str
    client_secret: str
    public_key: str

    @classmethod
    def from_env(cls, prefix: str = "DISCORD_") -> "DiscordConfig":
        """Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            DiscordConfig instance
        """
        return cls(
            bot_token=os.getenv(f"{prefix}BOT_TOKEN", ""),
            client_id=os.getenv(f"{prefix}CLIENT_ID", ""),
            client_secret=os.getenv(f"{prefix}CLIENT_SECRET", ""),
            public_key=os.getenv(f"{prefix}PUBLIC_KEY", ""),
        )


@dataclass
class TelegramConfig:
    """Telegram platform configuration."""

    bot_token: str
    webhook_secret: str

    @classmethod
    def from_env(cls, prefix: str = "TELEGRAM_") -> "TelegramConfig":
        """Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            TelegramConfig instance
        """
        return cls(
            bot_token=os.getenv(f"{prefix}BOT_TOKEN", ""),
            webhook_secret=os.getenv(f"{prefix}WEBHOOK_SECRET", ""),
        )


@dataclass
class WhatsAppConfig:
    """WhatsApp platform configuration."""

    account_sid: str
    auth_token: str
    from_number: str
    webhook_url: str

    @classmethod
    def from_env(cls, prefix: str = "WHATSAPP_") -> "WhatsAppConfig":
        """Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix

        Returns:
            WhatsAppConfig instance
        """
        return cls(
            account_sid=os.getenv(f"{prefix}ACCOUNT_SID", ""),
            auth_token=os.getenv(f"{prefix}AUTH_TOKEN", ""),
            from_number=os.getenv(f"{prefix}FROM_NUMBER", ""),
            webhook_url=os.getenv(f"{prefix}WEBHOOK_URL", ""),
        )
