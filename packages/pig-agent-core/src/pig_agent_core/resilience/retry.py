"""Resilient LLM calls with retry and fallback.

Extracted from sophia-pro LiteAgent's resilience system.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from pig_llm import LLM, Message, StreamChunk

from ..observability.events import AgentEvent, AgentEventCallback, AgentEventType, emit
from .profile import ProfileManager

logger = logging.getLogger(__name__)


class ResilienceExhaustedError(Exception):
    """Raised when all resilience strategies have been exhausted.

    Attributes:
        original_error: The original error that triggered resilience
        attempts: Number of retry attempts made
        strategies_tried: List of resilience strategies that were attempted
    """

    def __init__(
        self,
        message: str,
        original_error: Exception,
        attempts: int = 0,
        strategies_tried: list[str] | None = None,
    ):
        """Initialize ResilienceExhaustedError.

        Args:
            message: Error message
            original_error: Original exception that triggered resilience
            attempts: Number of retry attempts
            strategies_tried: List of strategies attempted
        """
        super().__init__(message)
        self.original_error = original_error
        self.attempts = attempts
        self.strategies_tried = strategies_tried or []


# Error types that trigger profile rotation
RATE_LIMIT_ERRORS = (
    "rate_limit",
    "rate limit",
    "429",
    "too many requests",
    "quota exceeded",
)

AUTH_ERRORS = (
    "authentication",
    "unauthorized",
    "401",
    "invalid api key",
    "api key",
)

TIMEOUT_ERRORS = (
    "timeout",
    "timed out",
    "connection",
    "network",
)

CONTEXT_OVERFLOW_ERRORS = (
    "context_length",
    "context length",
    "maximum context",
    "token limit",
    "too long",
)


def _is_error_type(error: Exception, error_patterns: tuple[str, ...]) -> bool:
    """Check if error matches any of the patterns.

    Args:
        error: Exception to check
        error_patterns: Tuple of error patterns to match

    Returns:
        True if error matches any pattern
    """
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in error_patterns)


def _should_rotate_profile(error: Exception) -> bool:
    """Check if error should trigger profile rotation.

    Args:
        error: Exception to check

    Returns:
        True if profile should be rotated
    """
    return (
        _is_error_type(error, RATE_LIMIT_ERRORS)
        or _is_error_type(error, AUTH_ERRORS)
        or _is_error_type(error, TIMEOUT_ERRORS)
    )


def _is_context_overflow(error: Exception) -> bool:
    """Check if error is context overflow.

    Args:
        error: Exception to check

    Returns:
        True if context overflow
    """
    return _is_error_type(error, CONTEXT_OVERFLOW_ERRORS)


async def resilient_streaming_call(
    llm: LLM,
    messages: list[Message],
    profile_manager: ProfileManager | None = None,
    compress_fn: Callable[[list[Message]], list[Message]] | None = None,
    max_retries: int = 3,
    event_callback: AgentEventCallback | None = None,
    **llm_kwargs: Any,
) -> AsyncIterator[StreamChunk]:
    """Make a resilient streaming LLM call with retry and fallback.

    Implements three layers of resilience:
    1. Profile rotation on rate_limit/auth/timeout errors
    2. Context overflow recovery (compress and retry)
    3. Fallback to alternative models

    Args:
        llm: LLM client
        messages: Messages to send
        profile_manager: Optional profile manager for key rotation
        compress_fn: Optional function to compress messages on context overflow
        max_retries: Maximum number of retries per layer
        event_callback: Optional callback for resilience events
        **llm_kwargs: Additional LLM arguments

    Yields:
        StreamChunk from LLM

    Raises:
        ResilienceExhaustedError: If all retry attempts fail
    """
    current_messages = messages
    current_model = llm_kwargs.get("model", llm.config.model)
    last_error = None
    strategies_tried = []

    # Layer 1: Profile rotation
    for attempt in range(max_retries):
        try:
            # Try with current profile
            async for chunk in llm.astream(messages=current_messages, **llm_kwargs):
                yield chunk
            return  # Success!

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")

            # Emit retry event
            emit(
                event_callback,
                AgentEvent(
                    type=AgentEventType.SPAN_START,
                    data={
                        "event_subtype": "resilience_retry",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(e),
                    },
                ),
            )

            # Check if we should rotate profile
            if profile_manager and _should_rotate_profile(e):
                # Mark current profile as failed
                current_profile = profile_manager.get_next_profile()
                if current_profile:
                    profile_manager.mark_profile_failed(current_profile, cooldown=60.0)

                # Try next profile
                next_profile = profile_manager.get_next_profile()
                if next_profile:
                    logger.info(f"Rotating to next API key: {next_profile.api_key[:8]}...")
                    strategies_tried.append("profile_rotation")

                    # Emit profile rotation event
                    emit(
                        event_callback,
                        AgentEvent(
                            type=AgentEventType.SPAN_START,
                            data={
                                "event_subtype": "resilience_profile_rotation",
                                "from_key": current_profile.api_key[:8]
                                if current_profile
                                else None,
                                "to_key": next_profile.api_key[:8],
                            },
                        ),
                    )
                    # Update LLM with new API key
                    # Note: This assumes LLM has a way to update API key
                    # In practice, you might need to create a new LLM instance
                    continue

            # Check if context overflow
            if _is_context_overflow(e):
                # Layer 2: Context compression
                if compress_fn:
                    logger.info("Context overflow detected, compressing messages...")
                    compressed = compress_fn(current_messages)
                    if len(compressed) < len(current_messages):
                        current_messages = compressed
                        strategies_tried.append("context_compression")
                        logger.info(
                            f"Compressed messages from {len(messages)} to {len(compressed)}"
                        )

                        # Emit compression event
                        emit(
                            event_callback,
                            AgentEvent(
                                type=AgentEventType.SPAN_START,
                                data={
                                    "event_subtype": "resilience_compact",
                                    "original_count": len(messages),
                                    "compressed_count": len(compressed),
                                },
                            ),
                        )
                        continue
                    else:
                        logger.warning("Compression did not reduce message count")

                # Layer 3: Fallback model
                if profile_manager:
                    fallback_model = profile_manager.get_fallback_model(current_model)
                    if fallback_model:
                        logger.info(f"Falling back to model: {fallback_model}")
                        llm_kwargs["model"] = fallback_model
                        current_model = fallback_model
                        strategies_tried.append("model_fallback")

                        # Emit fallback event
                        emit(
                            event_callback,
                            AgentEvent(
                                type=AgentEventType.SPAN_START,
                                data={
                                    "event_subtype": "resilience_fallback",
                                    "from_model": llm_kwargs.get("model", llm.config.model),
                                    "to_model": fallback_model,
                                },
                            ),
                        )
                        continue

            # If not a retriable error, raise immediately
            if attempt == max_retries - 1:
                raise ResilienceExhaustedError(
                    f"All resilience strategies exhausted after {max_retries} attempts",
                    original_error=e,
                    attempts=max_retries,
                    strategies_tried=strategies_tried,
                ) from e

            # Exponential backoff
            await asyncio.sleep(2**attempt)

    # All retries exhausted
    if last_error:
        raise ResilienceExhaustedError(
            f"All resilience strategies exhausted after {max_retries} attempts",
            original_error=last_error,
            attempts=max_retries,
            strategies_tried=strategies_tried,
        ) from last_error
    else:
        raise ResilienceExhaustedError(
            "All retry attempts failed",
            original_error=RuntimeError("Unknown error"),
            attempts=max_retries,
            strategies_tried=strategies_tried,
        )


async def resilient_call(
    llm: LLM,
    messages: list[Message],
    profile_manager: ProfileManager | None = None,
    compress_fn: Callable[[list[Message]], list[Message]] | None = None,
    max_retries: int = 3,
    event_callback: AgentEventCallback | None = None,
    **llm_kwargs: Any,
) -> str:
    """Make a resilient non-streaming LLM call with retry and fallback.

    Same resilience layers as resilient_streaming_call but returns complete response.

    Args:
        llm: LLM client
        messages: Messages to send
        profile_manager: Optional profile manager for key rotation
        compress_fn: Optional function to compress messages on context overflow
        max_retries: Maximum number of retries per layer
        event_callback: Optional callback for resilience events
        **llm_kwargs: Additional LLM arguments

    Returns:
        Complete response text

    Raises:
        ResilienceExhaustedError: If all retry attempts fail
    """
    current_messages = messages
    current_model = llm_kwargs.get("model", llm.config.model)
    last_error = None
    strategies_tried = []

    # Layer 1: Profile rotation
    for attempt in range(max_retries):
        try:
            # Try with current profile
            response = await llm.achat(messages=current_messages, **llm_kwargs)
            return response.content

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")

            # Emit retry event
            emit(
                event_callback,
                AgentEvent(
                    type=AgentEventType.SPAN_START,
                    data={
                        "event_subtype": "resilience_retry",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(e),
                    },
                ),
            )

            # Check if we should rotate profile
            if profile_manager and _should_rotate_profile(e):
                # Mark current profile as failed
                current_profile = profile_manager.get_next_profile()
                if current_profile:
                    profile_manager.mark_profile_failed(current_profile, cooldown=60.0)

                # Try next profile
                next_profile = profile_manager.get_next_profile()
                if next_profile:
                    logger.info(f"Rotating to next API key: {next_profile.api_key[:8]}...")
                    strategies_tried.append("profile_rotation")

                    # Emit profile rotation event
                    emit(
                        event_callback,
                        AgentEvent(
                            type=AgentEventType.SPAN_START,
                            data={
                                "event_subtype": "resilience_profile_rotation",
                                "from_key": current_profile.api_key[:8]
                                if current_profile
                                else None,
                                "to_key": next_profile.api_key[:8],
                            },
                        ),
                    )
                    continue

            # Check if context overflow
            if _is_context_overflow(e):
                # Layer 2: Context compression
                if compress_fn:
                    logger.info("Context overflow detected, compressing messages...")
                    compressed = compress_fn(current_messages)
                    if len(compressed) < len(current_messages):
                        current_messages = compressed
                        strategies_tried.append("context_compression")
                        logger.info(
                            f"Compressed messages from {len(messages)} to {len(compressed)}"
                        )

                        # Emit compression event
                        emit(
                            event_callback,
                            AgentEvent(
                                type=AgentEventType.SPAN_START,
                                data={
                                    "event_subtype": "resilience_compact",
                                    "original_count": len(messages),
                                    "compressed_count": len(compressed),
                                },
                            ),
                        )
                        continue
                    else:
                        logger.warning("Compression did not reduce message count")

                # Layer 3: Fallback model
                if profile_manager:
                    fallback_model = profile_manager.get_fallback_model(current_model)
                    if fallback_model:
                        logger.info(f"Falling back to model: {fallback_model}")
                        llm_kwargs["model"] = fallback_model
                        current_model = fallback_model
                        strategies_tried.append("model_fallback")

                        # Emit fallback event
                        emit(
                            event_callback,
                            AgentEvent(
                                type=AgentEventType.SPAN_START,
                                data={
                                    "event_subtype": "resilience_fallback",
                                    "from_model": llm_kwargs.get("model", llm.config.model),
                                    "to_model": fallback_model,
                                },
                            ),
                        )
                        continue

            # If not a retriable error, raise immediately
            if attempt == max_retries - 1:
                raise ResilienceExhaustedError(
                    f"All resilience strategies exhausted after {max_retries} attempts",
                    original_error=e,
                    attempts=max_retries,
                    strategies_tried=strategies_tried,
                ) from e

            # Exponential backoff
            await asyncio.sleep(2**attempt)

    # All retries exhausted
    if last_error:
        raise ResilienceExhaustedError(
            f"All resilience strategies exhausted after {max_retries} attempts",
            original_error=last_error,
            attempts=max_retries,
            strategies_tried=strategies_tried,
        ) from last_error
    else:
        raise ResilienceExhaustedError(
            "All retry attempts failed",
            original_error=RuntimeError("Unknown error"),
            attempts=max_retries,
            strategies_tried=strategies_tried,
        )
