"""Resilient LLM calls with retry and fallback.

Extracted from sophia-pro LiteAgent's resilience system.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from pig_llm import LLM, Message, Response, StreamChunk

from ..observability.events import (
    AgentEvent,
    AgentEventCallback,
    AgentEventType,
    credential_fingerprint,
    emit,
)
from .profile import APIProfile, ProfileManager

logger = logging.getLogger(__name__)


async def _stream_chunks(
    llm: LLM,
    *,
    messages: list[Message],
    **kwargs: Any,
) -> AsyncIterator[StreamChunk]:
    """Iterate the public ``LLM.achat_stream`` contract."""
    async for chunk in llm.achat_stream(messages=messages, **kwargs):
        yield chunk


def _rotate_llm(llm: LLM, *, api_key: str, model: str) -> LLM | None:
    """Return a client actually rebound to a profile, or decline rotation."""
    factory = getattr(type(llm), "with_profile", None)
    if not callable(factory):
        return None
    rotated = factory(llm, api_key=api_key, model=model)
    return rotated if rotated is not llm else None


def _active_llm(llm: LLM, profile_manager: ProfileManager | None) -> LLM:
    """Reuse the manager's explicitly active client across calls and agent rounds."""
    if profile_manager is None:
        return llm
    config = llm.config
    config_provider = getattr(config, "provider", None)
    active_identity = profile_manager.active_profile
    persisted = profile_manager.active_client
    if (
        active_identity is not None
        and active_identity.provider_id is None
        and persisted is not None
    ):
        persisted_provider = getattr(persisted.config, "provider", None)
        if isinstance(persisted_provider, str):
            active_identity.provider = persisted_provider
    active_provider_matches = (
        active_identity is not None and active_identity.provider_id == config_provider
    )
    persisted_key = getattr(persisted.config, "api_key", None) if persisted is not None else None
    persisted_provider = (
        getattr(persisted.config, "provider", None) if persisted is not None else None
    )
    persisted_matches_identity = (
        active_identity is not None
        and persisted_key == active_identity.api_key
        and persisted_provider == config_provider
    )
    if persisted is not None and active_provider_matches and persisted_matches_identity:
        return cast(LLM, persisted)
    if active_identity is not None and active_provider_matches:
        if active_identity.is_available():
            matched_key = getattr(config, "api_key", None) == active_identity.api_key
            matched_provider = getattr(config, "provider", None) in {
                None,
                active_identity.provider_id,
            }
            if matched_key and matched_provider:
                profile_manager.bind_active_client(llm)
                return llm
            rotated = _rotate_llm(
                llm,
                api_key=active_identity.api_key,
                model=active_identity.model,
            )
            if rotated is not None:
                profile_manager.set_active(active_identity, rotated)
                return rotated
        else:
            candidate = profile_manager.get_failover_profile(active_identity)
            if candidate is not None:
                rotated = _rotate_llm(llm, api_key=candidate.api_key, model=candidate.model)
                if rotated is not None:
                    profile_manager.set_active(candidate, rotated)
                    return rotated
    matched = profile_manager.find_profile(
        provider=getattr(config, "provider", None),
        api_key=getattr(config, "api_key", None),
    )
    if matched is None:
        return llm
    if matched.provider_id is None and isinstance(config_provider, str):
        matched.provider = config_provider
    if matched.is_available():
        profile_manager.set_active(matched, llm)
        return llm
    candidate = profile_manager.get_failover_profile(matched)
    if candidate is not None:
        rotated = _rotate_llm(llm, api_key=candidate.api_key, model=candidate.model)
        if rotated is not None:
            profile_manager.set_active(candidate, rotated)
            return rotated
    return llm


def _active_provider(llm: LLM, profile_manager: ProfileManager | None) -> str | None:
    config_provider = getattr(llm.config, "provider", None)
    if profile_manager and profile_manager.active_profile is not None:
        active_provider = profile_manager.active_profile.provider_id
        if active_provider in {None, config_provider}:
            return active_provider or config_provider
    return config_provider


def _profile_for_client(
    llm: LLM,
    profile_manager: ProfileManager | None,
) -> APIProfile | None:
    """Return only the profile whose credential the client will actually use."""
    if profile_manager is None:
        return None
    config = llm.config
    api_key = getattr(config, "api_key", None)
    if not isinstance(api_key, str):
        for attribute in ("api_key", "key"):
            candidate = getattr(llm, attribute, None)
            if isinstance(candidate, str):
                api_key = candidate
                break
    if not isinstance(api_key, str):
        return None
    return profile_manager.find_profile(
        provider=getattr(config, "provider", None),
        api_key=api_key,
    )


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


def _retry_reason(error: Exception) -> str:
    """Classify a failure into a stable, non-provider-specific reason."""
    if _is_context_overflow(error):
        return "context_overflow"
    if _is_error_type(error, RATE_LIMIT_ERRORS):
        return "rate_limit"
    if _is_error_type(error, AUTH_ERRORS):
        return "authentication"
    if _is_error_type(error, TIMEOUT_ERRORS):
        return "transport"
    return "provider_error"


def _emit_retry_event(
    callback: AgentEventCallback | None,
    *,
    retry_id: str,
    subtype: str,
    phase: str,
    reason: str,
    attempt: int,
    max_retries: int,
    **data: Any,
) -> None:
    """Emit a backwards-compatible resilience event with stable lifecycle fields."""
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.SPAN_START,
            data={
                "event_subtype": subtype,
                "retry_id": retry_id,
                "phase": phase,
                "reason": reason,
                "attempt": attempt,
                "max_retries": max_retries,
                **data,
            },
        ),
    )


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
        max_retries: Additional retries after the initial attempt
        event_callback: Optional callback for resilience events
        **llm_kwargs: Additional LLM arguments

    Yields:
        StreamChunk from LLM

    Raises:
        ResilienceExhaustedError: If all retry attempts fail
    """
    current_messages = messages
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    total_attempts = 1 + max_retries
    active_llm = _active_llm(llm, profile_manager)
    current_profile = _profile_for_client(active_llm, profile_manager)
    current_model = llm_kwargs.get("model", active_llm.config.model)
    if current_profile is not None:
        current_model = current_profile.model
        llm_kwargs["model"] = current_model
    strategies_tried: list[str] = []
    retry_id = str(uuid.uuid4())
    compaction_checkpoint_id: str | None = None

    # Layer 1: Profile rotation
    for attempt in range(total_attempts):
        yielded_output = False
        try:
            # Try with current profile
            async for chunk in _stream_chunks(
                active_llm,
                messages=current_messages,
                **llm_kwargs,
            ):
                yielded_output = True
                yield chunk
            if attempt > 0:
                if current_messages is not messages:
                    messages[:] = current_messages
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_succeeded",
                    phase="succeeded",
                    reason="retry_succeeded",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    model=current_model,
                    compaction_checkpoint_id=compaction_checkpoint_id,
                )
            return  # Success!

        except Exception as e:
            logger.warning(f"LLM call failed (attempt {attempt + 1}/{total_attempts}): {e}")

            # Emit retry event. Once output has been yielded, replaying the call
            # could duplicate visible output or tool requests, so fail closed.
            _emit_retry_event(
                event_callback,
                retry_id=retry_id,
                subtype="resilience_retry",
                phase="failed",
                reason=_retry_reason(e),
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e),
                model=current_model,
                partial_output=yielded_output,
            )
            if yielded_output:
                strategies_tried.append("partial_stream_no_retry")
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_exhausted",
                    phase="exhausted",
                    reason="partial_output",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    model=current_model,
                )
                raise ResilienceExhaustedError(
                    "Streaming call failed after yielding output; retry suppressed",
                    original_error=e,
                    attempts=attempt + 1,
                    strategies_tried=strategies_tried,
                ) from e

            failed_profile = None
            if profile_manager and _should_rotate_profile(e):
                failed_profile = current_profile
                if failed_profile is not None:
                    profile_manager.mark_profile_failed_with_error(failed_profile, e)

            # The final failed attempt may update profile health, but it must
            # not announce or apply a strategy that cannot be executed.
            if attempt == total_attempts - 1:
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_exhausted",
                    phase="exhausted",
                    reason="retries_exhausted",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    model=current_model,
                )
                raise ResilienceExhaustedError(
                    f"All resilience strategies exhausted after {total_attempts} attempts",
                    original_error=e,
                    attempts=total_attempts,
                    strategies_tried=strategies_tried,
                ) from e

            # Check if we should rotate profile
            if profile_manager and failed_profile is not None:
                # Try next profile
                next_profile = profile_manager.get_failover_profile(failed_profile)
                if next_profile:
                    rotated_llm = _rotate_llm(
                        active_llm,
                        api_key=next_profile.api_key,
                        model=next_profile.model,
                    )
                    if rotated_llm is not None:
                        logger.info(
                            "Rotating API profile to %s",
                            credential_fingerprint(next_profile.api_key),
                        )
                        active_llm = rotated_llm
                        profile_manager.set_active(next_profile, rotated_llm)
                        current_profile = next_profile
                        current_model = next_profile.model
                        llm_kwargs["model"] = current_model
                        strategies_tried.append("profile_rotation")
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_profile_rotation",
                            phase="strategy",
                            reason="profile_rotation",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_profile=(
                                credential_fingerprint(failed_profile.api_key)
                                if failed_profile
                                else None
                            ),
                            to_profile=credential_fingerprint(next_profile.api_key),
                        )
                        continue

            # Check if context overflow
            if _is_context_overflow(e):
                # Layer 2: Context compression
                if compress_fn:
                    logger.info("Context overflow detected, compressing messages...")
                    original_count = len(current_messages)
                    compressed = compress_fn(current_messages)
                    if len(compressed) < len(current_messages):
                        current_messages = compressed
                        strategies_tried.append("context_compression")
                        logger.info(
                            f"Compressed messages from {len(messages)} to {len(compressed)}"
                        )

                        # Emit compression event
                        compaction_checkpoint_id = str(uuid.uuid4())
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_compact",
                            phase="strategy",
                            reason="overflow",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            checkpoint_id=compaction_checkpoint_id,
                            original_count=original_count,
                            compressed_count=len(compressed),
                        )
                        continue
                    else:
                        logger.warning("Compression did not reduce message count")

                # Layer 3: Fallback model
                if profile_manager and isinstance(current_model, str):
                    fallback_model = profile_manager.get_fallback_model(
                        current_model, _active_provider(llm, profile_manager)
                    )
                    if fallback_model:
                        previous_model = current_model
                        logger.info(f"Falling back to model: {fallback_model}")
                        llm_kwargs["model"] = fallback_model
                        current_model = fallback_model
                        strategies_tried.append("model_fallback")

                        # Emit fallback event
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_fallback",
                            phase="strategy",
                            reason="model_fallback",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_model=previous_model,
                            to_model=fallback_model,
                        )
                        continue

            # Exponential backoff
            await asyncio.sleep(2**attempt)

    raise AssertionError("retry loop exited without returning or raising")


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
        max_retries: Additional retries after the initial attempt
        event_callback: Optional callback for resilience events
        **llm_kwargs: Additional LLM arguments

    Returns:
        Complete response text

    Raises:
        ResilienceExhaustedError: If all retry attempts fail
    """
    current_messages = messages
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    total_attempts = 1 + max_retries
    active_llm = _active_llm(llm, profile_manager)
    current_profile = _profile_for_client(active_llm, profile_manager)
    current_model = llm_kwargs.get("model", active_llm.config.model)
    if current_profile is not None:
        current_model = current_profile.model
        llm_kwargs["model"] = current_model
    strategies_tried: list[str] = []
    retry_id = str(uuid.uuid4())
    compaction_checkpoint_id: str | None = None

    # Layer 1: Profile rotation
    for attempt in range(total_attempts):
        try:
            # Try with current profile
            response = await active_llm.achat(messages=current_messages, **llm_kwargs)
            if attempt > 0:
                if current_messages is not messages:
                    messages[:] = current_messages
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_succeeded",
                    phase="succeeded",
                    reason="retry_succeeded",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    model=current_model,
                    compaction_checkpoint_id=compaction_checkpoint_id,
                )
            return response.content

        except Exception as e:
            logger.warning(f"LLM call failed (attempt {attempt + 1}/{total_attempts}): {e}")

            # Emit retry event
            _emit_retry_event(
                event_callback,
                retry_id=retry_id,
                subtype="resilience_retry",
                phase="failed",
                reason=_retry_reason(e),
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e),
                model=current_model,
            )

            failed_profile = None
            if profile_manager and _should_rotate_profile(e):
                failed_profile = current_profile
                if failed_profile is not None:
                    profile_manager.mark_profile_failed_with_error(failed_profile, e)

            if attempt == total_attempts - 1:
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_exhausted",
                    phase="exhausted",
                    reason="retries_exhausted",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    model=current_model,
                )
                raise ResilienceExhaustedError(
                    f"All resilience strategies exhausted after {total_attempts} attempts",
                    original_error=e,
                    attempts=total_attempts,
                    strategies_tried=strategies_tried,
                ) from e

            # Check if we should rotate profile
            if profile_manager and failed_profile is not None:
                # Try next profile
                next_profile = profile_manager.get_failover_profile(failed_profile)
                if next_profile:
                    rotated_llm = _rotate_llm(
                        active_llm,
                        api_key=next_profile.api_key,
                        model=next_profile.model,
                    )
                    if rotated_llm is not None:
                        logger.info(
                            "Rotating API profile to %s",
                            credential_fingerprint(next_profile.api_key),
                        )
                        active_llm = rotated_llm
                        profile_manager.set_active(next_profile, rotated_llm)
                        current_profile = next_profile
                        current_model = next_profile.model
                        llm_kwargs["model"] = current_model
                        strategies_tried.append("profile_rotation")
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_profile_rotation",
                            phase="strategy",
                            reason="profile_rotation",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_profile=(
                                credential_fingerprint(failed_profile.api_key)
                                if failed_profile
                                else None
                            ),
                            to_profile=credential_fingerprint(next_profile.api_key),
                        )
                        continue

            # Check if context overflow
            if _is_context_overflow(e):
                # Layer 2: Context compression
                if compress_fn:
                    logger.info("Context overflow detected, compressing messages...")
                    original_count = len(current_messages)
                    compressed = compress_fn(current_messages)
                    if len(compressed) < len(current_messages):
                        current_messages = compressed
                        strategies_tried.append("context_compression")
                        logger.info(
                            f"Compressed messages from {len(messages)} to {len(compressed)}"
                        )

                        # Emit compression event
                        compaction_checkpoint_id = str(uuid.uuid4())
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_compact",
                            phase="strategy",
                            reason="overflow",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            checkpoint_id=compaction_checkpoint_id,
                            original_count=original_count,
                            compressed_count=len(compressed),
                        )
                        continue
                    else:
                        logger.warning("Compression did not reduce message count")

                # Layer 3: Fallback model
                if profile_manager and isinstance(current_model, str):
                    fallback_model = profile_manager.get_fallback_model(
                        current_model, _active_provider(llm, profile_manager)
                    )
                    if fallback_model:
                        previous_model = current_model
                        logger.info(f"Falling back to model: {fallback_model}")
                        llm_kwargs["model"] = fallback_model
                        current_model = fallback_model
                        strategies_tried.append("model_fallback")

                        # Emit fallback event
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_fallback",
                            phase="strategy",
                            reason="model_fallback",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_model=previous_model,
                            to_model=fallback_model,
                        )
                        continue

            # Exponential backoff
            await asyncio.sleep(2**attempt)

    raise AssertionError("retry loop exited without returning or raising")


def resilient_sync_call(
    llm: LLM,
    messages: list[Message],
    profile_manager: ProfileManager | None = None,
    compress_fn: Callable[[list[Message]], list[Message]] | None = None,
    max_retries: int = 3,
    event_callback: AgentEventCallback | None = None,
    **llm_kwargs: Any,
) -> Response:
    """Use the same correlated contract; ``max_retries`` is additional retries."""
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    total_attempts = 1 + max_retries
    current_messages = messages
    active_llm = _active_llm(llm, profile_manager)
    current_profile = _profile_for_client(active_llm, profile_manager)
    current_model = llm_kwargs.get("model", active_llm.config.model)
    if current_profile is not None:
        current_model = current_profile.model
        llm_kwargs["model"] = current_model
    strategies_tried: list[str] = []
    retry_id = str(uuid.uuid4())
    compaction_checkpoint_id: str | None = None

    for attempt in range(total_attempts):
        try:
            response = active_llm.chat(messages=current_messages, **llm_kwargs)
            if attempt > 0:
                if current_messages is not messages:
                    messages[:] = current_messages
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_succeeded",
                    phase="succeeded",
                    reason="retry_succeeded",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    model=current_model,
                    compaction_checkpoint_id=compaction_checkpoint_id,
                )
            return response
        except Exception as exc:
            _emit_retry_event(
                event_callback,
                retry_id=retry_id,
                subtype="resilience_retry",
                phase="failed",
                reason=_retry_reason(exc),
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(exc),
                model=current_model,
            )

            failed_profile = None
            if profile_manager and _should_rotate_profile(exc):
                failed_profile = current_profile
                if failed_profile is not None:
                    profile_manager.mark_profile_failed_with_error(failed_profile, exc)

            if attempt == total_attempts - 1:
                _emit_retry_event(
                    event_callback,
                    retry_id=retry_id,
                    subtype="resilience_retry_exhausted",
                    phase="exhausted",
                    reason="retries_exhausted",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(exc),
                    model=current_model,
                )
                raise ResilienceExhaustedError(
                    f"All resilience strategies exhausted after {total_attempts} attempts",
                    original_error=exc,
                    attempts=total_attempts,
                    strategies_tried=strategies_tried,
                ) from exc

            if profile_manager and failed_profile is not None:
                next_profile = profile_manager.get_failover_profile(failed_profile)
                if next_profile:
                    rotated_llm = _rotate_llm(
                        active_llm,
                        api_key=next_profile.api_key,
                        model=next_profile.model,
                    )
                    if rotated_llm is not None:
                        active_llm = rotated_llm
                        profile_manager.set_active(next_profile, rotated_llm)
                        current_profile = next_profile
                        current_model = next_profile.model
                        llm_kwargs["model"] = current_model
                        strategies_tried.append("profile_rotation")
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_profile_rotation",
                            phase="strategy",
                            reason="profile_rotation",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_profile=(
                                credential_fingerprint(failed_profile.api_key)
                                if failed_profile
                                else None
                            ),
                            to_profile=credential_fingerprint(next_profile.api_key),
                        )
                        continue

            if _is_context_overflow(exc):
                if compress_fn:
                    original_count = len(current_messages)
                    compressed = compress_fn(current_messages)
                    if len(compressed) < original_count:
                        current_messages = compressed
                        strategies_tried.append("context_compression")
                        compaction_checkpoint_id = str(uuid.uuid4())
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_compact",
                            phase="strategy",
                            reason="overflow",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            checkpoint_id=compaction_checkpoint_id,
                            original_count=original_count,
                            compressed_count=len(compressed),
                        )
                        continue
                if profile_manager and isinstance(current_model, str):
                    fallback_model = profile_manager.get_fallback_model(
                        current_model, _active_provider(llm, profile_manager)
                    )
                    if fallback_model:
                        previous_model = current_model
                        llm_kwargs["model"] = fallback_model
                        current_model = fallback_model
                        strategies_tried.append("model_fallback")
                        _emit_retry_event(
                            event_callback,
                            retry_id=retry_id,
                            subtype="resilience_fallback",
                            phase="strategy",
                            reason="model_fallback",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            from_model=previous_model,
                            to_model=fallback_model,
                        )
                        continue

    raise AssertionError("retry loop exited without returning or raising")
