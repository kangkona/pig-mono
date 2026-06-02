"""Provider compatibility helpers absorbed from recent pi-mono behavior.

The helpers are intentionally provider-agnostic so model quirks do not spread
across every provider implementation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from .models import Message

SystemRolePolicy = Literal["system", "developer"]
MaxOutputTokenPolicy = Literal["omit_default", "send_when_explicit", "required"]
RetryClassification = Literal["retryable", "quota_or_billing", "auth", "context_overflow", "fatal"]
TokenLimitField = Literal["max_completion_tokens", "max_tokens"]
CacheRetention = Literal["none", "short", "long"]


class ThinkingLevel(str, Enum):
    """Canonical thinking levels used by pig providers."""

    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(frozen=True)
class ProviderCompat:
    """Compatibility metadata for provider request normalization."""

    system_role_policy: SystemRolePolicy = "system"
    max_output_token_policy: MaxOutputTokenPolicy = "send_when_explicit"
    token_limit_field: TokenLimitField = "max_completion_tokens"
    supports_long_cache_retention: bool = True
    send_session_affinity_headers: bool = False
    thinking_level_map: dict[str, Any | None] = field(default_factory=dict)
    reasoning_effort_models: frozenset[str] = frozenset()
    reasoning_effort_level_map: dict[str, dict[str, str | None]] = field(default_factory=dict)
    unsupported_params: frozenset[str] = frozenset()
    context_overflow_patterns: tuple[re.Pattern[str], ...] = ()
    quota_or_billing_patterns: tuple[re.Pattern[str], ...] = ()
    retryable_patterns: tuple[re.Pattern[str], ...] = ()


def _compile_many(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


COMMON_CONTEXT_OVERFLOW_PATTERNS = _compile_many(
    (
        r"context (?:length|window)",
        r"maximum (?:allowed )?input length",
        r"max(?:imum)? context",
        r"request_too_large",
        r"too many tokens",
        r"exceeds? the model'?s maximum context length",
        r"input .* tokens .* exceed",
    )
)

COMMON_QUOTA_OR_BILLING_PATTERNS = _compile_many(
    (
        r"billing",
        r"quota",
        r"insufficient(?:_| )quota",
        r"rate limit.*(?:quota|billing)",
        r"payment required",
    )
)

COMMON_RETRYABLE_PATTERNS = _compile_many(
    (
        r"\b429\b",
        r"\b5\d\d\b",
        r"server_error",
        r"internal_error",
        r"temporar(?:y|ily)",
        r"timeout",
        r"connection (?:lost|reset|closed)",
        r"ended without",
    )
)


OPENAI_COMPAT = ProviderCompat(
    system_role_policy="developer",
    max_output_token_policy="send_when_explicit",
    reasoning_effort_level_map={
        "gpt-5.5": {
            "off": None,
            "minimal": None,
            "low": "low",
            "medium": "medium",
            "high": "high",
            "xhigh": "xhigh",
        },
        "gpt-5.5-pro": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": "medium",
            "high": "high",
            "xhigh": "xhigh",
        },
    },
    thinking_level_map={
        "off": "none",
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
    },
    unsupported_params=frozenset({"max_tokens"}),
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

AZURE_OPENAI_COMPAT = ProviderCompat(
    system_role_policy=OPENAI_COMPAT.system_role_policy,
    max_output_token_policy=OPENAI_COMPAT.max_output_token_policy,
    token_limit_field=OPENAI_COMPAT.token_limit_field,
    supports_long_cache_retention=OPENAI_COMPAT.supports_long_cache_retention,
    send_session_affinity_headers=True,
    thinking_level_map=OPENAI_COMPAT.thinking_level_map,
    reasoning_effort_models=OPENAI_COMPAT.reasoning_effort_models,
    reasoning_effort_level_map=OPENAI_COMPAT.reasoning_effort_level_map,
    unsupported_params=OPENAI_COMPAT.unsupported_params,
    context_overflow_patterns=OPENAI_COMPAT.context_overflow_patterns,
    quota_or_billing_patterns=OPENAI_COMPAT.quota_or_billing_patterns,
    retryable_patterns=OPENAI_COMPAT.retryable_patterns,
)

OPENROUTER_COMPAT = ProviderCompat(
    system_role_policy="system",
    max_output_token_policy="send_when_explicit",
    token_limit_field="max_tokens",
    send_session_affinity_headers=True,
    reasoning_effort_level_map={
        "deepseek/deepseek-v4-flash": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"effort": "high"},
            "xhigh": {"effort": "xhigh"},
        },
        "deepseek/deepseek-v4-pro": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"effort": "high"},
            "xhigh": {"effort": "xhigh"},
        },
        "openai/gpt-5.5-pro": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": {"effort": "medium"},
            "high": {"effort": "high"},
            "xhigh": {"effort": "xhigh"},
        },
    },
    thinking_level_map={
        "off": {"effort": "none"},
        "minimal": {"effort": "low"},
        "low": {"effort": "low"},
        "medium": {"effort": "medium"},
        "high": {"effort": "high"},
        "xhigh": {"effort": "xhigh"},
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

ANTHROPIC_COMPAT = ProviderCompat(
    max_output_token_policy="required",
    thinking_level_map={
        "off": None,
        "minimal": None,
        "low": {"type": "enabled", "budget_tokens": 1024},
        "medium": {"type": "enabled", "budget_tokens": 4096},
        "high": {"type": "enabled", "budget_tokens": 8192},
        "xhigh": {"type": "enabled", "budget_tokens": 16384},
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

BEDROCK_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map=ANTHROPIC_COMPAT.thinking_level_map,
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

DEEPSEEK_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    token_limit_field="max_tokens",
    send_session_affinity_headers=True,
    reasoning_effort_level_map={
        "deepseek-v4-flash": {
            "off": "none",
            "minimal": None,
            "low": None,
            "medium": None,
            "high": "high",
            "xhigh": "max",
        },
        "deepseek-v4-pro": {
            "off": "none",
            "minimal": None,
            "low": None,
            "medium": None,
            "high": "high",
            "xhigh": "max",
        },
    },
    thinking_level_map={
        "off": {"type": "disabled"},
        "minimal": {"type": "enabled"},
        "low": {"type": "enabled"},
        "medium": {"type": "enabled"},
        "high": {"type": "enabled"},
        "xhigh": {"type": "enabled"},
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

TOGETHER_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    token_limit_field="max_tokens",
    supports_long_cache_retention=False,
    send_session_affinity_headers=True,
    reasoning_effort_models=frozenset({"deepseek-ai/deepseek-v4-pro"}),
    reasoning_effort_level_map={
        "minimaxai/minimax-m2.5": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"enabled": True},
            "xhigh": {"enabled": True},
        },
        "minimaxai/minimax-m2.7": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"enabled": True},
            "xhigh": {"enabled": True},
        },
        "moonshotai/kimi-k2.5": {
            "off": None,
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"enabled": True},
            "xhigh": {"enabled": True},
        },
        "moonshotai/kimi-k2.6": {
            "off": {"enabled": False},
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"enabled": True},
            "xhigh": {"enabled": True},
        },
        "deepseek-ai/deepseek-v4-pro": {
            "minimal": None,
            "low": None,
            "medium": None,
            "high": "high",
            "xhigh": None,
        },
    },
    thinking_level_map={
        "off": {"enabled": False},
        "minimal": {"enabled": True},
        "low": {"enabled": True},
        "medium": {"enabled": True},
        "high": {"enabled": True},
        "xhigh": {"enabled": True},
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

GROQ_COMPAT = ProviderCompat(
    system_role_policy=OPENAI_COMPAT.system_role_policy,
    max_output_token_policy=OPENAI_COMPAT.max_output_token_policy,
    token_limit_field=OPENAI_COMPAT.token_limit_field,
    supports_long_cache_retention=OPENAI_COMPAT.supports_long_cache_retention,
    send_session_affinity_headers=True,
    thinking_level_map=OPENAI_COMPAT.thinking_level_map,
    reasoning_effort_models=OPENAI_COMPAT.reasoning_effort_models,
    reasoning_effort_level_map=OPENAI_COMPAT.reasoning_effort_level_map,
    unsupported_params=OPENAI_COMPAT.unsupported_params,
    context_overflow_patterns=OPENAI_COMPAT.context_overflow_patterns,
    quota_or_billing_patterns=OPENAI_COMPAT.quota_or_billing_patterns,
    retryable_patterns=OPENAI_COMPAT.retryable_patterns,
)

QWEN_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map={
        "off": False,
        "minimal": True,
        "low": True,
        "medium": True,
        "high": True,
        "xhigh": True,
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

ZAI_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map=QWEN_COMPAT.thinking_level_map,
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

MOONSHOT_COMPAT = ProviderCompat(
    system_role_policy="system",
    max_output_token_policy="send_when_explicit",
    token_limit_field="max_tokens",
    supports_long_cache_retention=False,
    send_session_affinity_headers=True,
    thinking_level_map={},
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

QWEN_CHAT_TEMPLATE_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map=QWEN_COMPAT.thinking_level_map,
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

STRING_THINKING_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map={
        "off": "none",
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

OPENCODE_GO_KIMI_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    reasoning_effort_level_map={
        "kimi-k2.6": {
            "off": {"type": "disabled"},
            "minimal": None,
            "low": None,
            "medium": None,
            "high": {"type": "enabled"},
            "xhigh": None,
        }
    },
    thinking_level_map={
        "off": {"type": "disabled"},
        "minimal": {"type": "enabled"},
        "low": {"type": "enabled"},
        "medium": {"type": "enabled"},
        "high": {"type": "enabled"},
        "xhigh": {"type": "enabled"},
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

OPENCODE_ZEN_GROK_BUILD_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    thinking_level_map={
        "off": None,
        "minimal": None,
        "low": None,
        "medium": None,
        "high": {"type": "enabled"},
        "xhigh": None,
    },
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

TOGETHER_OPENAI_REASONING_COMPAT = ProviderCompat(
    max_output_token_policy="send_when_explicit",
    token_limit_field="max_tokens",
    supports_long_cache_retention=False,
    send_session_affinity_headers=True,
    reasoning_effort_level_map={
        "openai/gpt-oss-20b": {
            "off": None,
            "minimal": None,
            "low": "low",
            "medium": "medium",
            "high": "high",
            "xhigh": "xhigh",
        },
        "openai/gpt-oss-120b": {
            "off": None,
            "minimal": None,
            "low": "low",
            "medium": "medium",
            "high": "high",
            "xhigh": "xhigh",
        },
    },
    thinking_level_map=OPENAI_COMPAT.thinking_level_map,
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)


def normalize_messages(
    messages: list[Message],
    compat: ProviderCompat,
    *,
    supports_developer_role: bool = False,
) -> list[Message]:
    """Normalize message roles for a provider.

    Some OpenAI-compatible routers reject the newer `developer` role. pig's
    public model currently only exposes `system`, but this helper also handles
    role values injected through metadata or future model expansion.
    """
    target_role = "developer" if compat.system_role_policy == "developer" else "system"
    if target_role == "developer" and not supports_developer_role:
        target_role = "system"

    normalized: list[Message] = []
    for message in messages:
        role = message.role
        metadata_role = (message.metadata or {}).get("role")
        if metadata_role == "developer" or role == "system":
            normalized.append(
                Message(role=target_role, content=message.content, metadata=message.metadata)
            )
        else:
            normalized.append(message)
    return normalized


def build_token_limit_param(
    max_tokens: int | None,
    *,
    param_name: str,
    compat: ProviderCompat,
    explicit: bool = True,
) -> dict[str, int]:
    """Return a token-limit parameter only when compatible.

    `explicit=False` represents model-derived defaults. Recent upstream changes
    avoid sending model-derived caps to OpenAI-compatible servers because some
    reserve the full output budget against the context window.
    """
    if max_tokens is None:
        return {}
    if compat.max_output_token_policy == "omit_default" and not explicit:
        return {}
    if param_name in compat.unsupported_params and not explicit:
        return {}
    return {param_name: max_tokens}


def apply_prompt_cache(
    kwargs: dict[str, Any],
    compat: ProviderCompat,
) -> dict[str, Any]:
    """Apply OpenAI-style prompt cache fields when supported."""
    next_kwargs = dict(kwargs)
    raw_cache_retention = next_kwargs.pop("cache_retention", None)
    if raw_cache_retention is None:
        raw_cache_retention = os.environ.get("PI_CACHE_RETENTION", "short")
    cache_retention = str(raw_cache_retention or "short").lower()
    session_id = next_kwargs.get("session_id")
    next_kwargs["_resolved_cache_retention"] = cache_retention

    if not session_id or cache_retention == "none":
        next_kwargs.pop("prompt_cache_key", None)
        next_kwargs.pop("prompt_cache_retention", None)
        return next_kwargs

    if cache_retention == "long" and compat.supports_long_cache_retention:
        next_kwargs["prompt_cache_key"] = str(session_id)[:64]
        next_kwargs["prompt_cache_retention"] = "24h"
        return next_kwargs

    if compat is OPENAI_COMPAT:
        next_kwargs["prompt_cache_key"] = str(session_id)[:64]
        next_kwargs.pop("prompt_cache_retention", None)
        return next_kwargs

    next_kwargs.pop("prompt_cache_key", None)
    next_kwargs.pop("prompt_cache_retention", None)
    return next_kwargs


def apply_thinking_level(kwargs: dict[str, Any], compat: ProviderCompat) -> dict[str, Any]:
    """Apply or strip thinking parameters according to compatibility metadata."""
    next_kwargs = dict(kwargs)
    level = next_kwargs.pop("thinking_level", None)
    model = str(next_kwargs.get("model") or "")
    model_key = model.lower()
    if level is None:
        return next_kwargs

    mapped = compat.thinking_level_map.get(str(level))
    if mapped is None:
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is OPENROUTER_COMPAT:
        model_map = compat.reasoning_effort_level_map.get(model_key)
        reasoning = model_map.get(str(level)) if model_map is not None else mapped
        if reasoning is None:
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            next_kwargs.pop("reasoning_effort", None)
            return next_kwargs
        next_kwargs["reasoning"] = reasoning
        next_kwargs.pop("thinking", None)
        return next_kwargs

    if compat is OPENAI_COMPAT or compat is AZURE_OPENAI_COMPAT or compat is GROQ_COMPAT:
        model_map = compat.reasoning_effort_level_map.get(model_key)
        reasoning_effort = model_map.get(str(level)) if model_map is not None else mapped
        if reasoning_effort is None:
            next_kwargs.pop("reasoning_effort", None)
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            return next_kwargs
        next_kwargs["reasoning_effort"] = reasoning_effort
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        return next_kwargs

    if compat is TOGETHER_COMPAT:
        next_kwargs["reasoning"] = mapped
        next_kwargs.pop("thinking", None)
        level_map = compat.reasoning_effort_level_map.get(model_key, {})
        if model_key in {
            "minimaxai/minimax-m2.5",
            "minimaxai/minimax-m2.7",
            "moonshotai/kimi-k2.5",
            "moonshotai/kimi-k2.6",
        }:
            reasoning = level_map.get(str(level))
            if reasoning is None:
                next_kwargs.pop("reasoning", None)
                next_kwargs.pop("reasoning_effort", None)
                return next_kwargs
            next_kwargs["reasoning"] = reasoning
        elif model_key in compat.reasoning_effort_models:
            reasoning_effort = level_map.get(str(level))
            if reasoning_effort is not None:
                next_kwargs["reasoning_effort"] = reasoning_effort
            else:
                next_kwargs.pop("reasoning_effort", None)
        if model_key not in compat.reasoning_effort_models and model_key not in {
            "minimaxai/minimax-m2.5",
            "minimaxai/minimax-m2.7",
            "moonshotai/kimi-k2.5",
            "moonshotai/kimi-k2.6",
        }:
            next_kwargs.pop("reasoning_effort", None)
        if next_kwargs.get("reasoning") is None:
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            next_kwargs.pop("reasoning_effort", None)
            return next_kwargs
        return next_kwargs

    if compat is TOGETHER_OPENAI_REASONING_COMPAT:
        model_map = compat.reasoning_effort_level_map.get(model_key)
        reasoning_effort = model_map.get(str(level)) if model_map is not None else None
        if reasoning_effort is None:
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            next_kwargs.pop("reasoning_effort", None)
            return next_kwargs
        next_kwargs["reasoning_effort"] = reasoning_effort
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        return next_kwargs

    if compat is QWEN_CHAT_TEMPLATE_COMPAT:
        next_kwargs["chat_template_kwargs"] = {
            "enable_thinking": mapped,
            "preserve_thinking": True,
        }
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is QWEN_COMPAT or compat is ZAI_COMPAT:
        next_kwargs["enable_thinking"] = mapped
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is STRING_THINKING_COMPAT:
        next_kwargs["thinking"] = mapped
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is OPENCODE_GO_KIMI_COMPAT:
        model_map = compat.reasoning_effort_level_map.get(model_key)
        thinking = model_map.get(str(level)) if model_map is not None else mapped
        if thinking is None:
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            next_kwargs.pop("reasoning_effort", None)
            return next_kwargs
        next_kwargs["thinking"] = thinking
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is OPENCODE_ZEN_GROK_BUILD_COMPAT:
        next_kwargs["thinking"] = mapped
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is DEEPSEEK_COMPAT:
        model_map = compat.reasoning_effort_level_map.get(model_key)
        reasoning_effort = model_map.get(str(level)) if model_map is not None else None
        if model_map is not None and reasoning_effort is None:
            next_kwargs.pop("thinking", None)
            next_kwargs.pop("reasoning", None)
            next_kwargs.pop("reasoning_effort", None)
            return next_kwargs
        next_kwargs["thinking"] = {"type": "disabled" if str(level) == "off" else "enabled"}
        if reasoning_effort is not None and str(level) != "off":
            next_kwargs["reasoning_effort"] = reasoning_effort
        else:
            next_kwargs.pop("reasoning_effort", None)
        next_kwargs.pop("reasoning", None)
        return next_kwargs

    next_kwargs["thinking"] = mapped
    return next_kwargs


def apply_request_headers(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Merge compat headers into OpenAI-compatible request kwargs.

    `session_id` is normalized to the proxy-safe `session-id` header while
    preserving any explicit custom headers provided by callers.
    """
    next_kwargs = dict(kwargs)
    headers = dict(next_kwargs.pop("headers", {}) or {})
    extra_headers = dict(next_kwargs.pop("extra_headers", {}) or {})
    session_id = next_kwargs.pop("session_id", None)

    merged_headers = {**extra_headers, **headers}
    if session_id:
        merged_headers.setdefault("session-id", session_id)

    if merged_headers:
        next_kwargs["extra_headers"] = merged_headers

    return next_kwargs


def apply_session_affinity_headers(
    kwargs: dict[str, Any],
    compat: ProviderCompat,
) -> dict[str, Any]:
    """Add provider-specific session-affinity headers when supported."""
    next_kwargs = dict(kwargs)
    session_id = next_kwargs.get("session_id")
    cache_retention = str(
        next_kwargs.pop("_resolved_cache_retention", next_kwargs.get("cache_retention", "short"))
        or "short"
    ).lower()

    if not session_id or cache_retention == "none" or not compat.send_session_affinity_headers:
        return next_kwargs

    headers = dict(next_kwargs.pop("headers", {}) or {})
    extra_headers = dict(next_kwargs.pop("extra_headers", {}) or {})
    merged_headers = {
        "session_id": str(session_id),
        "x-client-request-id": str(session_id),
        "x-session-affinity": str(session_id),
        **extra_headers,
        **headers,
    }
    next_kwargs["extra_headers"] = merged_headers
    return next_kwargs


def classify_provider_error(
    error: BaseException | str, compat: ProviderCompat
) -> RetryClassification:
    """Classify provider failures for retry and fallback behavior."""
    text = str(error)
    if any(pattern.search(text) for pattern in compat.context_overflow_patterns):
        return "context_overflow"
    if any(pattern.search(text) for pattern in compat.quota_or_billing_patterns):
        return "quota_or_billing"
    if re.search(r"\b(?:401|403)\b|unauthori[sz]ed|invalid api key|authentication", text, re.I):
        return "auth"
    if any(pattern.search(text) for pattern in compat.retryable_patterns):
        return "retryable"
    return "fatal"


def is_context_overflow(error: BaseException | str, compat: ProviderCompat | None = None) -> bool:
    """Return True if an error looks like a context-window overflow."""
    return classify_provider_error(error, compat or OPENAI_COMPAT) == "context_overflow"


def extract_openai_usage(response: Any) -> dict[str, int]:
    """Extract usage from OpenAI-compatible responses.

    Some compatible providers report usage on choice objects instead of the
    top-level response envelope.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        choices = getattr(response, "choices", None) or []
        if choices:
            usage = getattr(choices[0], "usage", None)

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
    }
