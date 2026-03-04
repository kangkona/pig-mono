"""Profile manager for API key rotation and fallback models.

Extracted from sophia-pro LiteAgent's resilience system.
"""

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailoverReason(Enum):
    """Reason for profile failover with associated cooldown periods.

    Each failure type has a recommended cooldown period:
    - AUTH: 300s (5 min) - Invalid API key, likely needs manual fix
    - RATE_LIMIT: 60s (1 min) - Temporary rate limit, retry soon
    - BILLING: 3600s (1 hour) - Billing issue, needs time to resolve
    - TIMEOUT: 30s - Network timeout, retry quickly
    - CONTEXT_OVERFLOW: 10s - Context too large, retry with compression
    """

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    BILLING = "billing"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"


# Default cooldown periods per failure type (in seconds)
DEFAULT_COOLDOWNS: dict[FailoverReason, float] = {
    FailoverReason.AUTH: 300.0,  # 5 minutes
    FailoverReason.RATE_LIMIT: 60.0,  # 1 minute
    FailoverReason.BILLING: 3600.0,  # 1 hour
    FailoverReason.TIMEOUT: 30.0,  # 30 seconds
    FailoverReason.CONTEXT_OVERFLOW: 10.0,  # 10 seconds
}


def classify_failure(error: Exception | str) -> FailoverReason:
    """Classify failure type from error message or exception.

    Args:
        error: Exception or error message string

    Returns:
        FailoverReason enum value
    """
    error_str = str(error).lower()

    # Check for authentication errors
    if any(
        keyword in error_str
        for keyword in ["unauthorized", "invalid api key", "authentication", "401", "403"]
    ):
        return FailoverReason.AUTH

    # Check for rate limit errors
    if any(keyword in error_str for keyword in ["rate limit", "429", "too many requests"]):
        return FailoverReason.RATE_LIMIT

    # Check for billing errors
    if any(
        keyword in error_str for keyword in ["billing", "quota", "insufficient", "payment", "402"]
    ):
        return FailoverReason.BILLING

    # Check for timeout errors
    if any(keyword in error_str for keyword in ["timeout", "timed out", "deadline"]):
        return FailoverReason.TIMEOUT

    # Check for context overflow
    if any(
        keyword in error_str
        for keyword in ["context", "token limit", "maximum context", "too long"]
    ):
        return FailoverReason.CONTEXT_OVERFLOW

    # Default to rate limit for unknown errors
    return FailoverReason.RATE_LIMIT


@dataclass
class APIProfile:
    """API profile with key and cooldown tracking.

    Attributes:
        api_key: API key for the provider
        model: Model name (e.g., "gpt-4", "claude-3-5-sonnet-20241022")
        cooldown_until: Timestamp when this profile can be used again
        metadata: Additional profile metadata
    """

    api_key: str
    model: str
    cooldown_until: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_available(self) -> bool:
        """Check if profile is available (not in cooldown).

        Returns:
            True if profile can be used now
        """
        return time.time() >= self.cooldown_until

    def set_cooldown(self, seconds: float) -> None:
        """Set cooldown period for this profile.

        Args:
            seconds: Cooldown duration in seconds
        """
        self.cooldown_until = time.time() + seconds


class ProfileManager:
    """Manages API profiles with rotation and fallback.

    Supports multiple API keys with cooldown tracking and fallback models.
    Includes per-failure-type cooldown periods for intelligent retry behavior.
    """

    def __init__(
        self,
        profiles: list[APIProfile] | None = None,
        fallback_models: list[str] | None = None,
        default_cooldown: float = 60.0,
        cooldown_overrides: dict[FailoverReason, float] | None = None,
    ):
        """Initialize profile manager.

        Args:
            profiles: List of API profiles
            fallback_models: List of fallback model names
            default_cooldown: Default cooldown duration in seconds
            cooldown_overrides: Custom cooldown periods per failure type
        """
        self.profiles = profiles or []
        self.fallback_models = fallback_models or []
        self.default_cooldown = default_cooldown
        self._current_index = 0

        # Merge default cooldowns with overrides
        self.cooldowns = DEFAULT_COOLDOWNS.copy()
        if cooldown_overrides:
            self.cooldowns.update(cooldown_overrides)

    @classmethod
    def from_env(
        cls,
        env_prefix: str = "OPENAI_API_KEY",
        model: str = "gpt-4",
        fallback_models: list[str] | None = None,
    ) -> "ProfileManager":
        """Create profile manager from environment variables.

        Looks for API keys in environment variables:
        - {env_prefix} (single key)
        - {env_prefix}_1, {env_prefix}_2, ... (multiple keys)

        Also supports PIG_AGENT_* aliases with LITE_AGENT_* backward compatibility:
        - PIG_AGENT_API_KEY or LITE_AGENT_API_KEY
        - PIG_AGENT_API_KEY_1 or LITE_AGENT_API_KEY_1

        Args:
            env_prefix: Environment variable prefix
            model: Default model name
            fallback_models: List of fallback model names

        Returns:
            ProfileManager with loaded profiles
        """
        profiles = []

        # Try PIG_AGENT_* and LITE_AGENT_* aliases first
        for alias_prefix in ["PIG_AGENT_API_KEY", "LITE_AGENT_API_KEY"]:
            single_key = os.getenv(alias_prefix)
            if single_key:
                profiles.append(APIProfile(api_key=single_key, model=model))
                break  # Use first found

        # Try single key with custom prefix
        if not profiles:
            single_key = os.getenv(env_prefix)
            if single_key:
                profiles.append(APIProfile(api_key=single_key, model=model))

        # Try numbered keys with all prefixes
        index = 1
        while True:
            key = None
            # Try PIG_AGENT_* first, then LITE_AGENT_*, then custom prefix
            for prefix in ["PIG_AGENT_API_KEY", "LITE_AGENT_API_KEY", env_prefix]:
                key = os.getenv(f"{prefix}_{index}")
                if key:
                    break

            if not key:
                break

            profiles.append(APIProfile(api_key=key, model=model))
            index += 1

        return cls(profiles=profiles, fallback_models=fallback_models)

    def get_next_profile(self) -> APIProfile | None:
        """Get next available profile with rotation.

        Returns:
            Next available profile, or None if all are in cooldown
        """
        if not self.profiles:
            return None

        # Try to find an available profile
        attempts = 0
        while attempts < len(self.profiles):
            profile = self.profiles[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.profiles)

            if profile.is_available():
                return profile

            attempts += 1

        # All profiles are in cooldown
        return None

    def mark_profile_failed(
        self,
        profile: APIProfile,
        cooldown: float | None = None,
        reason: FailoverReason | None = None,
    ) -> None:
        """Mark profile as failed and set cooldown based on failure type.

        Args:
            profile: Profile that failed
            cooldown: Explicit cooldown duration (overrides reason-based cooldown)
            reason: Failure reason for automatic cooldown selection
        """
        if cooldown is not None:
            # Explicit cooldown provided
            cooldown_duration = cooldown
        elif reason is not None:
            # Use reason-based cooldown
            cooldown_duration = self.cooldowns.get(reason, self.default_cooldown)
        else:
            # Use default cooldown
            cooldown_duration = self.default_cooldown

        profile.set_cooldown(cooldown_duration)

    def mark_profile_failed_with_error(
        self,
        profile: APIProfile,
        error: Exception | str,
    ) -> FailoverReason:
        """Mark profile as failed and classify error for appropriate cooldown.

        Args:
            profile: Profile that failed
            error: Exception or error message

        Returns:
            Classified failure reason
        """
        reason = classify_failure(error)
        self.mark_profile_failed(profile, reason=reason)
        return reason

    def get_fallback_model(self, current_model: str) -> str | None:
        """Get fallback model for the current model.

        Args:
            current_model: Current model name

        Returns:
            Fallback model name, or None if no fallback available
        """
        if not self.fallback_models:
            return None

        # If current model is in fallback list, try next one
        try:
            current_index = self.fallback_models.index(current_model)
            if current_index + 1 < len(self.fallback_models):
                return self.fallback_models[current_index + 1]
        except ValueError:
            # Current model not in fallback list, return first fallback
            return self.fallback_models[0]

        return None

    def add_profile(self, profile: APIProfile) -> None:
        """Add a new profile to the manager.

        Args:
            profile: Profile to add
        """
        self.profiles.append(profile)

    def remove_profile(self, api_key: str) -> bool:
        """Remove profile by API key.

        Args:
            api_key: API key of profile to remove

        Returns:
            True if profile was removed
        """
        for i, profile in enumerate(self.profiles):
            if profile.api_key == api_key:
                self.profiles.pop(i)
                # Adjust current index if needed
                if self._current_index >= len(self.profiles):
                    self._current_index = 0
                return True
        return False

    def get_all_profiles(self) -> list[APIProfile]:
        """Get all profiles.

        Returns:
            List of all profiles
        """
        return self.profiles.copy()

    def get_available_profiles(self) -> list[APIProfile]:
        """Get all available profiles (not in cooldown).

        Returns:
            List of available profiles
        """
        return [p for p in self.profiles if p.is_available()]
