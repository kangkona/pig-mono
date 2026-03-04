"""Tests for messenger config dataclasses."""

from pig_messenger.config import (
    DiscordConfig,
    EnvSecretProvider,
    SlackConfig,
    TelegramConfig,
    WhatsAppConfig,
)


def test_slack_config_from_env(monkeypatch):
    """Test SlackConfig.from_env()."""
    monkeypatch.setenv("SLACK_CLIENT_ID", "client_123")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret_456")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing_789")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-token")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-token")

    config = SlackConfig.from_env()
    assert config.client_id == "client_123"
    assert config.client_secret == "secret_456"
    assert config.signing_secret == "signing_789"
    assert config.bot_token == "xoxb-token"
    assert config.app_token == "xapp-token"


def test_slack_config_custom_prefix(monkeypatch):
    """Test SlackConfig with custom prefix."""
    monkeypatch.setenv("CUSTOM_CLIENT_ID", "custom_123")
    monkeypatch.setenv("CUSTOM_CLIENT_SECRET", "custom_secret")
    monkeypatch.setenv("CUSTOM_SIGNING_SECRET", "custom_signing")
    monkeypatch.setenv("CUSTOM_BOT_TOKEN", "custom_bot")
    monkeypatch.setenv("CUSTOM_APP_TOKEN", "custom_app")

    config = SlackConfig.from_env(prefix="CUSTOM_")
    assert config.client_id == "custom_123"
    assert config.client_secret == "custom_secret"


def test_discord_config_from_env(monkeypatch):
    """Test DiscordConfig.from_env()."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "discord_client")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "discord_secret")
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", "discord_key")

    config = DiscordConfig.from_env()
    assert config.bot_token == "discord_token"
    assert config.client_id == "discord_client"
    assert config.client_secret == "discord_secret"
    assert config.public_key == "discord_key"


def test_telegram_config_from_env(monkeypatch):
    """Test TelegramConfig.from_env()."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram_token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook_secret")

    config = TelegramConfig.from_env()
    assert config.bot_token == "telegram_token"
    assert config.webhook_secret == "webhook_secret"


def test_whatsapp_config_from_env(monkeypatch):
    """Test WhatsAppConfig.from_env()."""
    monkeypatch.setenv("WHATSAPP_ACCOUNT_SID", "account_sid")
    monkeypatch.setenv("WHATSAPP_AUTH_TOKEN", "auth_token")
    monkeypatch.setenv("WHATSAPP_FROM_NUMBER", "+1234567890")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_URL", "https://example.com/webhook")

    config = WhatsAppConfig.from_env()
    assert config.account_sid == "account_sid"
    assert config.auth_token == "auth_token"
    assert config.from_number == "+1234567890"
    assert config.webhook_url == "https://example.com/webhook"


def test_config_defaults():
    """Test config defaults when env vars not set."""
    config = SlackConfig.from_env(prefix="NONEXISTENT_")
    assert config.client_id == ""
    assert config.client_secret == ""
    assert config.signing_secret == ""
    assert config.bot_token == ""
    assert config.app_token == ""


def test_env_secret_provider():
    """Test EnvSecretProvider."""
    provider = EnvSecretProvider()
    result = provider.get_secret("any/path")
    assert result == {}
