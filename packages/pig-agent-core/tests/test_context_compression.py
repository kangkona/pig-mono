"""Tests for context compression functionality."""

import pytest
from pig_agent_core.context import (
    CompressionConfig,
    compress_level1,
    compress_level2,
    compress_level3,
    compress_messages,
)


class TestCompressionLevel1:
    """Test Level 1 compression (truncate tool results)."""

    def test_truncate_long_tool_result(self):
        """Test truncating long tool results."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "content": "x" * 2000, "tool_call_id": "call_1"},
        ]

        compressed = compress_level1(messages, max_chars=1000)

        assert len(compressed) == 2
        assert compressed[0] == messages[0]  # User message unchanged
        assert len(compressed[1]["content"]) < 2000
        assert "truncated" in compressed[1]["content"]

    def test_keep_short_tool_result(self):
        """Test that short tool results are not truncated."""
        messages = [
            {"role": "tool", "content": "Short result", "tool_call_id": "call_1"},
        ]

        compressed = compress_level1(messages, max_chars=1000)

        assert compressed == messages

    def test_non_tool_messages_unchanged(self):
        """Test that non-tool messages are not affected."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "Assistant response"},
        ]

        compressed = compress_level1(messages)

        assert compressed == messages

    def test_multiple_tool_results(self):
        """Test truncating multiple tool results."""
        messages = [
            {"role": "tool", "content": "x" * 2000, "tool_call_id": "call_1"},
            {"role": "tool", "content": "y" * 1500, "tool_call_id": "call_2"},
            {"role": "tool", "content": "Short", "tool_call_id": "call_3"},
        ]

        compressed = compress_level1(messages, max_chars=1000)

        assert len(compressed) == 3
        assert len(compressed[0]["content"]) < 2000
        assert len(compressed[1]["content"]) < 1500
        assert compressed[2]["content"] == "Short"


class TestCompressionLevel2:
    """Test Level 2 compression (replace with summaries)."""

    def test_replace_tool_call_with_summary(self):
        """Test replacing tool call/result pairs with summary."""
        messages = [
            {"role": "user", "content": "Search for Python"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "search_web", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "content": "Search results...",
                "tool_call_id": "call_1",
            },
            {"role": "assistant", "content": "Here are the results"},
        ]

        compressed = compress_level2(messages)

        assert len(compressed) == 3
        assert compressed[0] == messages[0]
        assert "Tool execution" in compressed[1]["content"]
        assert "search_web" in compressed[1]["content"]
        assert compressed[2] == messages[3]

    def test_multiple_tool_calls(self):
        """Test summarizing multiple tool calls."""
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "search", "arguments": "{}"}},
                    {"id": "call_2", "function": {"name": "read", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "content": "Result 1", "tool_call_id": "call_1"},
            {"role": "tool", "content": "Result 2", "tool_call_id": "call_2"},
        ]

        compressed = compress_level2(messages)

        assert len(compressed) == 1
        assert "search" in compressed[0]["content"]
        assert "read" in compressed[0]["content"]
        assert "2 results" in compressed[0]["content"]

    def test_no_tool_calls(self):
        """Test that messages without tool calls are unchanged."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        compressed = compress_level2(messages)

        assert compressed == messages


class TestCompressionLevel3:
    """Test Level 3 compression (LLM summarization)."""

    @pytest.mark.asyncio
    async def test_summarize_middle_messages(self):
        """Test LLM summarization of middle messages."""

        class MockLLM:
            async def achat(self, messages, max_tokens):
                class Response:
                    content = "User asked about Python, assistant explained basics."

                return Response()

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Tell me about Python"},
            {"role": "assistant", "content": "Python is a programming language..."},
            {"role": "user", "content": "What about variables?"},
            {"role": "assistant", "content": "Variables store data..."},
            {"role": "user", "content": "And functions?"},
            {"role": "assistant", "content": "Functions are reusable code..."},
            {"role": "user", "content": "Thanks!"},
        ]

        llm = MockLLM()
        compressed = await compress_level3(messages, llm)

        # Should keep system, summary, and last 3 messages
        assert len(compressed) < len(messages)
        assert compressed[0]["role"] == "system"
        assert "summary" in compressed[1]["content"].lower()
        assert compressed[-1]["content"] == "Thanks!"

    @pytest.mark.asyncio
    async def test_short_conversation_unchanged(self):
        """Test that short conversations are not compressed."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        class MockLLM:
            pass

        compressed = await compress_level3(messages, MockLLM())

        assert compressed == messages

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        """Test fallback to Level 2 on LLM error."""

        class FailingLLM:
            async def achat(self, messages, max_tokens):
                raise Exception("LLM error")

        messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        llm = FailingLLM()
        compressed = await compress_level3(messages, llm)

        # Should fall back to Level 2 compression
        assert isinstance(compressed, list)


class TestCompressionConfig:
    """Test compression configuration."""

    def test_default_config(self):
        """Test default compression thresholds."""
        config = CompressionConfig()

        assert config.level1_threshold == 0.7
        assert config.level2_threshold == 0.8
        assert config.level3_threshold == 0.9
        assert config.max_tool_result_chars == 1000

    def test_custom_config(self):
        """Test custom compression thresholds."""
        config = CompressionConfig(
            level1_threshold=0.6,
            level2_threshold=0.75,
            level3_threshold=0.85,
            max_tool_result_chars=500,
        )

        assert config.level1_threshold == 0.6
        assert config.level2_threshold == 0.75
        assert config.level3_threshold == 0.85
        assert config.max_tool_result_chars == 500


class TestCompressMessages:
    """Test unified compression function."""

    def test_no_compression_needed(self):
        """Test that no compression is applied when under threshold."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        compressed = compress_messages(
            messages,
            current_tokens=500,
            max_tokens=1000,
        )

        assert compressed == messages

    def test_level1_compression(self):
        """Test Level 1 compression is applied."""
        messages = [
            {"role": "tool", "content": "x" * 2000, "tool_call_id": "call_1"},
        ]

        compressed = compress_messages(
            messages,
            current_tokens=750,  # 75% of max
            max_tokens=1000,
        )

        assert len(compressed[0]["content"]) < 2000

    def test_level2_compression(self):
        """Test Level 2 compression is applied."""
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}],
            },
            {"role": "tool", "content": "Result", "tool_call_id": "call_1"},
        ]

        compressed = compress_messages(
            messages,
            current_tokens=850,  # 85% of max
            max_tokens=1000,
        )

        assert len(compressed) == 1
        assert "Tool execution" in compressed[0]["content"]

    def test_level3_compression(self):
        """Test Level 3 compression is applied."""
        messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
        ]

        # Level 3 falls back to Level 2 in sync context
        compressed = compress_messages(
            messages,
            current_tokens=950,  # 95% of max
            max_tokens=1000,
        )

        assert isinstance(compressed, list)

    def test_custom_config(self):
        """Test compression with custom config."""
        config = CompressionConfig(
            level1_threshold=0.5,
            max_tool_result_chars=500,
        )

        messages = [
            {"role": "tool", "content": "x" * 2000, "tool_call_id": "call_1"},
        ]

        compressed = compress_messages(
            messages,
            current_tokens=600,  # 60% of max
            max_tokens=1000,
            config=config,
        )

        # Should trigger Level 1 with custom threshold
        assert len(compressed[0]["content"]) < 2000
        assert len(compressed[0]["content"]) <= 500 + 100  # Allow for truncation message
