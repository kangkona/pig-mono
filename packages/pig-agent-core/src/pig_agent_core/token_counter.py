"""Token counting utilities for context management.

Provides accurate token counting using tiktoken when available,
with fallback to character-based estimation.
"""

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cache for tokenizer instances
_tokenizer_cache: dict[str, Any] = {}

# Character-to-token ratio for estimation (conservative estimate)
CHARS_PER_TOKEN = 4
IMAGE_TOKEN_ESTIMATE = 765


def count_tokens(text: str, model: str | None = None) -> int:
    """Count tokens in text for the given model.

    Args:
        text: Text to count tokens for
        model: Model name (e.g., "gpt-4", "claude-3-opus"). If None, uses estimation.

    Returns:
        Estimated token count

    Examples:
        >>> count_tokens("Hello world")
        3
        >>> count_tokens("Hello world", model="gpt-4")
        2
    """
    if not text:
        return 0

    # Try tiktoken if available
    if model:
        try:
            tiktoken = importlib.import_module("tiktoken")

            # Check cache first
            if model not in _tokenizer_cache:
                try:
                    # Try to get encoding for model
                    encoding = tiktoken.encoding_for_model(model)
                    _tokenizer_cache[model] = encoding
                except KeyError:
                    # Model not recognized, use cl100k_base (GPT-4 default)
                    logger.debug(f"Model {model} not recognized, using cl100k_base encoding")
                    encoding = tiktoken.get_encoding("cl100k_base")
                    _tokenizer_cache[model] = encoding

            encoding = _tokenizer_cache[model]
            return len(encoding.encode(text))

        except ImportError:
            # tiktoken not available, fall through to estimation
            logger.debug("tiktoken not available, using character-based estimation")
        except Exception as e:
            # Any other error, fall through to estimation
            logger.warning(f"Error using tiktoken: {e}, falling back to estimation")

    # Fallback: character-based estimation
    return max(1, len(text) // CHARS_PER_TOKEN)


def count_content_tokens(content: Any, model: str | None = None) -> int:
    """Count tokens for text or multimodal content blocks.

    OpenAI-style content arrays may include text and image blocks. The exact
    token cost depends on provider/image size, so image blocks use a stable
    conservative estimate to make context budgeting include them.
    """
    if isinstance(content, str):
        return count_tokens(content, model)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, str):
                total += count_tokens(block, model)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type in {"image", "image_url", "input_image"} or "image_url" in block:
                    total += IMAGE_TOKEN_ESTIMATE
                else:
                    total += count_tokens(
                        str(block.get("text") or block.get("content") or ""), model
                    )
        return total
    return count_tokens(str(content), model)


def count_message_tokens(messages: list[dict[str, Any]], model: str | None = None) -> int:
    """Estimate tokens for chat messages including tool and image content."""
    total = 0
    for message in messages:
        total += 4  # role and message framing overhead
        total += count_tokens(str(message.get("role", "")), model)
        total += count_content_tokens(message.get("content", ""), model)
        for tool_call in message.get("tool_calls", []) or []:
            total += count_tokens(str(tool_call), model)
        if message.get("role") == "tool":
            total += 2
    return total


def clear_cache() -> None:
    """Clear the tokenizer cache.

    Useful for testing or memory management.
    """
    _tokenizer_cache.clear()
