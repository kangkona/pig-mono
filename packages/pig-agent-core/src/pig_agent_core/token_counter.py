"""Token counting utilities for context management.

Provides accurate token counting using tiktoken when available,
with fallback to character-based estimation.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cache for tokenizer instances
_tokenizer_cache: dict[str, Any] = {}

# Character-to-token ratio for estimation (conservative estimate)
CHARS_PER_TOKEN = 4


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
            import tiktoken

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


def clear_cache() -> None:
    """Clear the tokenizer cache.

    Useful for testing or memory management.
    """
    _tokenizer_cache.clear()
