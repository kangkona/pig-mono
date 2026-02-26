"""Tests for MessengerBot streaming card flow."""

import asyncio
from unittest.mock import MagicMock

from pig_messenger.bot import MessengerBot
from pig_messenger.message import UniversalMessage
from pig_messenger.platform import MessagePlatform

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeStreamChunk:
    def __init__(self, content: str):
        self.content = content


class _FakeCardPlatform(MessagePlatform):
    """Platform that supports card updates (overrides update_card)."""

    def __init__(self):
        super().__init__("fake_card")
        self.sent_cards: list[tuple[str, str]] = []
        self.updated_cards: list[tuple[str, str]] = []
        self.sent_messages: list[tuple[str, str]] = []

    async def send_message(self, channel_id, text, thread_id=None, **kwargs):
        self.sent_messages.append((channel_id, text))
        return "om_text_001"

    async def send_card(self, channel_id, text, **kwargs):
        self.sent_cards.append((channel_id, text))
        return "om_card_001"

    async def update_card(self, message_id, text, **kwargs):
        self.updated_cards.append((message_id, text))

    async def upload_file(self, channel_id, file_path, caption=None, thread_id=None):
        return "om_file_001"

    async def get_history(self, channel_id, limit=100):
        return []

    async def download_file(self, attachment):
        return b""

    def start(self):
        pass

    def stop(self):
        pass


class _PlainPlatform(MessagePlatform):
    """Platform without card support (uses base class defaults)."""

    def __init__(self):
        super().__init__("plain")
        self.sent_messages: list[tuple[str, str]] = []

    async def send_message(self, channel_id, text, thread_id=None, **kwargs):
        self.sent_messages.append((channel_id, text))
        return "om_plain_001"

    async def upload_file(self, channel_id, file_path, caption=None, thread_id=None):
        return "om_file_001"

    async def get_history(self, channel_id, limit=100):
        return []

    async def download_file(self, attachment):
        return b""

    def start(self):
        pass

    def stop(self):
        pass


def _make_message(text="hello", platform="fake_card", channel_id="oc_test"):
    return UniversalMessage(
        id="om_in_001",
        platform=platform,
        channel_id=channel_id,
        user_id="ou_user",
        username="tester",
        text=text,
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStreamingFlow:
    def _make_bot_with_streaming(self, platform, chunks):
        """Create a bot whose agent.llm.stream() yields the given chunks."""
        agent = MagicMock()
        agent.llm = MagicMock()
        agent.llm.stream = MagicMock(return_value=iter([_FakeStreamChunk(c) for c in chunks]))

        bot = MessengerBot(agent, enable_sessions=False)
        bot.add_platform(platform)
        return bot

    def test_streaming_sends_card_and_updates(self):
        platform = _FakeCardPlatform()
        bot = self._make_bot_with_streaming(platform, ["Hello", " world", "!"])

        msg = _make_message("hi")
        _run(bot.handle_message(msg))

        # Should have sent one placeholder card
        assert len(platform.sent_cards) == 1
        assert platform.sent_cards[0] == ("oc_test", "⏳ 思考中...")

        # Final update should contain the full text without "生成中"
        assert len(platform.updated_cards) >= 1
        final_text = platform.updated_cards[-1][1]
        assert final_text == "Hello world!"
        assert "生成中" not in final_text

    def test_streaming_final_text_correct(self):
        platform = _FakeCardPlatform()
        bot = self._make_bot_with_streaming(platform, ["A", "B", "C"])

        _run(bot.handle_message(_make_message("test")))

        final = platform.updated_cards[-1][1]
        assert final == "ABC"

    def test_fallback_to_standard_when_no_card_support(self):
        """Plain platform should use standard send_message, not streaming."""
        platform = _PlainPlatform()
        agent = MagicMock()
        agent.llm = MagicMock()
        agent.llm.stream = MagicMock()
        response = MagicMock()
        response.content = "standard reply"
        agent.run.return_value = response

        bot = MessengerBot(agent, enable_sessions=False)
        bot.add_platform(platform)

        msg = _make_message("hi", platform="plain")
        _run(bot.handle_message(msg))

        # Should use send_message, not streaming
        assert len(platform.sent_messages) == 1
        assert platform.sent_messages[0][1] == "standard reply"
        agent.llm.stream.assert_not_called()

    def test_streaming_error_sends_error_message(self):
        platform = _FakeCardPlatform()
        agent = MagicMock()
        agent.llm = MagicMock()
        agent.llm.stream = MagicMock(side_effect=RuntimeError("LLM down"))

        bot = MessengerBot(agent, enable_sessions=False)
        bot.add_platform(platform)

        _run(bot.handle_message(_make_message("hi")))

        # Should have attempted to send error
        assert any("Error" in text for _, text in platform.sent_messages)
