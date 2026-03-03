"""Tests for token_counter module."""

from pig_agent_core.token_counter import CHARS_PER_TOKEN, clear_cache, count_tokens


class TestTokenCounter:
    """Test token counting functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()

    def test_empty_string(self):
        """Test counting tokens in empty string."""
        assert count_tokens("") == 0
        assert count_tokens("", model="gpt-4") == 0

    def test_simple_text_no_model(self):
        """Test character-based estimation without model."""
        text = "Hello world"
        expected = max(1, len(text) // CHARS_PER_TOKEN)
        assert count_tokens(text) == expected

    def test_simple_text_with_model(self):
        """Test token counting with model (falls back to estimation if tiktoken unavailable)."""
        text = "Hello world"
        result = count_tokens(text, model="gpt-4")
        # Should return a positive integer
        assert isinstance(result, int)
        assert result > 0

    def test_long_text(self):
        """Test counting tokens in longer text."""
        text = "This is a longer piece of text that should have more tokens. " * 10
        result = count_tokens(text)
        assert result > 10  # Should have many tokens

    def test_unicode_text(self):
        """Test counting tokens with unicode characters."""
        text = "Hello 世界 🌍"
        result = count_tokens(text)
        assert result > 0

    def test_cache_usage(self):
        """Test that tokenizer cache is used."""
        text = "Hello world"
        model = "gpt-4"

        # First call
        result1 = count_tokens(text, model=model)

        # Second call should use cache
        result2 = count_tokens(text, model=model)

        assert result1 == result2

    def test_clear_cache(self):
        """Test cache clearing."""
        count_tokens("test", model="gpt-4")
        clear_cache()
        # Should still work after cache clear
        result = count_tokens("test", model="gpt-4")
        assert result > 0

    def test_different_models(self):
        """Test counting with different models."""
        text = "Hello world"

        result1 = count_tokens(text, model="gpt-4")
        result2 = count_tokens(text, model="gpt-3.5-turbo")

        # Both should return positive integers
        assert isinstance(result1, int) and result1 > 0
        assert isinstance(result2, int) and result2 > 0

    def test_unknown_model(self):
        """Test counting with unknown model (should fall back gracefully)."""
        text = "Hello world"
        result = count_tokens(text, model="unknown-model-xyz")
        assert isinstance(result, int)
        assert result > 0

    def test_minimum_token_count(self):
        """Test that single character returns at least 1 token."""
        assert count_tokens("a") >= 1
        assert count_tokens("a", model="gpt-4") >= 1

    def test_whitespace_only(self):
        """Test counting tokens in whitespace."""
        text = "   \n\t  "
        result = count_tokens(text)
        assert result >= 0

    def test_special_characters(self):
        """Test counting tokens with special characters."""
        text = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        result = count_tokens(text)
        assert result > 0

    def test_newlines_and_formatting(self):
        """Test counting tokens with newlines and formatting."""
        text = "Line 1\nLine 2\n\nLine 3\t\tTabbed"
        result = count_tokens(text)
        assert result > 0

    def test_code_snippet(self):
        """Test counting tokens in code."""
        code = """
def hello():
    print("Hello, world!")
    return 42
"""
        result = count_tokens(code)
        assert result > 5  # Should have multiple tokens

    def test_json_like_text(self):
        """Test counting tokens in JSON-like text."""
        text = '{"key": "value", "number": 123, "nested": {"inner": true}}'
        result = count_tokens(text)
        assert result > 10

    def test_very_long_text(self):
        """Test counting tokens in very long text."""
        text = "word " * 10000
        result = count_tokens(text)
        assert result > 1000  # Should have many tokens

    def test_estimation_consistency(self):
        """Test that estimation is consistent."""
        text = "This is a test sentence."
        result1 = count_tokens(text)
        result2 = count_tokens(text)
        assert result1 == result2
