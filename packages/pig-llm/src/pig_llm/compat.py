"""Provider compatibility helpers absorbed from recent pi-mono behavior.

The helpers are intentionally provider-agnostic so model quirks do not spread
across every provider implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from .models import Message

SystemRolePolicy = Literal["system", "developer"]
MaxOutputTokenPolicy = Literal["omit_default", "send_when_explicit", "required"]
RetryClassification = Literal["retryable", "quota_or_billing", "auth", "context_overflow", "fatal"]


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
    thinking_level_map: dict[str, Any | None] = field(default_factory=dict)
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
    max_output_token_policy="send_when_explicit",
    unsupported_params=frozenset({"max_tokens"}),
    context_overflow_patterns=COMMON_CONTEXT_OVERFLOW_PATTERNS,
    quota_or_billing_patterns=COMMON_QUOTA_OR_BILLING_PATTERNS,
    retryable_patterns=COMMON_RETRYABLE_PATTERNS,
)

OPENROUTER_COMPAT = ProviderCompat(
    system_role_policy="system",
    max_output_token_policy="send_when_explicit",
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


def apply_thinking_level(kwargs: dict[str, Any], compat: ProviderCompat) -> dict[str, Any]:
    """Apply or strip thinking parameters according to compatibility metadata."""
    next_kwargs = dict(kwargs)
    level = next_kwargs.pop("thinking_level", None)
    if level is None:
        return next_kwargs

    mapped = compat.thinking_level_map.get(str(level))
    if mapped is None:
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
        return next_kwargs

    if compat is OPENROUTER_COMPAT:
        next_kwargs["reasoning"] = mapped
        next_kwargs.pop("thinking", None)
        return next_kwargs

    if compat is TOGETHER_COMPAT:
        next_kwargs["reasoning"] = mapped
        next_kwargs.pop("thinking", None)
        return next_kwargs

    if compat is QWEN_COMPAT or compat is ZAI_COMPAT:
        next_kwargs["enable_thinking"] = mapped
        next_kwargs.pop("thinking", None)
        next_kwargs.pop("reasoning", None)
        next_kwargs.pop("reasoning_effort", None)
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
        merged_headers["session-id"] = session_id

    if merged_headers:
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
