"""Tests for enhanced profile manager with failure classification."""

import os
import time

from pig_agent_core.resilience.profile import (
    DEFAULT_COOLDOWNS,
    APIProfile,
    FailoverReason,
    ProfileManager,
    classify_failure,
)


class TestFailoverReason:
    """Test FailoverReason enum."""

    def test_failover_reason_values(self):
        """Test that all failover reasons have expected values."""
        assert FailoverReason.AUTH.value == "auth"
        assert FailoverReason.RATE_LIMIT.value == "rate_limit"
        assert FailoverReason.BILLING.value == "billing"
        assert FailoverReason.TIMEOUT.value == "timeout"
        assert FailoverReason.CONTEXT_OVERFLOW.value == "context_overflow"

    def test_default_cooldowns_exist(self):
        """Test that default cooldowns are defined for all reasons."""
        for reason in FailoverReason:
            assert reason in DEFAULT_COOLDOWNS
            assert DEFAULT_COOLDOWNS[reason] > 0


class TestClassifyFailure:
    """Test failure classification function."""

    def test_classify_auth_error_unauthorized(self):
        """Test classification of unauthorized error."""
        error = "Error: Unauthorized access"
        assert classify_failure(error) == FailoverReason.AUTH

    def test_classify_auth_error_invalid_key(self):
        """Test classification of invalid API key error."""
        error = "Invalid API key provided"
        assert classify_failure(error) == FailoverReason.AUTH

    def test_classify_auth_error_401(self):
        """Test classification of 401 error."""
        error = "HTTP 401: Authentication failed"
        assert classify_failure(error) == FailoverReason.AUTH

    def test_classify_auth_error_403(self):
        """Test classification of 403 error."""
        error = "HTTP 403: Forbidden"
        assert classify_failure(error) == FailoverReason.AUTH

    def test_classify_rate_limit_error(self):
        """Test classification of rate limit error."""
        error = "Rate limit exceeded"
        assert classify_failure(error) == FailoverReason.RATE_LIMIT

    def test_classify_rate_limit_429(self):
        """Test classification of 429 error."""
        error = "HTTP 429: Too many requests"
        assert classify_failure(error) == FailoverReason.RATE_LIMIT

    def test_classify_billing_error_quota(self):
        """Test classification of quota exceeded error."""
        error = "Quota exceeded for this API key"
        assert classify_failure(error) == FailoverReason.BILLING

    def test_classify_billing_error_payment(self):
        """Test classification of payment error."""
        error = "Payment required to continue"
        assert classify_failure(error) == FailoverReason.BILLING

    def test_classify_billing_error_402(self):
        """Test classification of 402 error."""
        error = "HTTP 402: Payment required"
        assert classify_failure(error) == FailoverReason.BILLING

    def test_classify_timeout_error(self):
        """Test classification of timeout error."""
        error = "Request timed out after 30 seconds"
        assert classify_failure(error) == FailoverReason.TIMEOUT

    def test_classify_timeout_deadline(self):
        """Test classification of deadline exceeded error."""
        error = "Deadline exceeded"
        assert classify_failure(error) == FailoverReason.TIMEOUT

    def test_classify_context_overflow_error(self):
        """Test classification of context overflow error."""
        error = "Context length exceeded maximum"
        assert classify_failure(error) == FailoverReason.CONTEXT_OVERFLOW

    def test_classify_context_token_limit(self):
        """Test classification of token limit error."""
        error = "Token limit reached"
        assert classify_failure(error) == FailoverReason.CONTEXT_OVERFLOW

    def test_classify_unknown_error_defaults_to_rate_limit(self):
        """Test that unknown errors default to rate limit."""
        error = "Some unknown error occurred"
        assert classify_failure(error) == FailoverReason.RATE_LIMIT

    def test_classify_exception_object(self):
        """Test classification with exception object."""
        error = ValueError("Unauthorized access")
        assert classify_failure(error) == FailoverReason.AUTH

    def test_classify_case_insensitive(self):
        """Test that classification is case-insensitive."""
        assert classify_failure("UNAUTHORIZED") == FailoverReason.AUTH
        assert classify_failure("Rate Limit") == FailoverReason.RATE_LIMIT
        assert classify_failure("TIMEOUT") == FailoverReason.TIMEOUT


class TestProfileManagerEnhanced:
    """Test enhanced profile manager features."""

    def test_init_with_cooldown_overrides(self):
        """Test initialization with custom cooldown overrides."""
        overrides = {
            FailoverReason.AUTH: 600.0,
            FailoverReason.RATE_LIMIT: 120.0,
        }
        manager = ProfileManager(cooldown_overrides=overrides)

        assert manager.cooldowns[FailoverReason.AUTH] == 600.0
        assert manager.cooldowns[FailoverReason.RATE_LIMIT] == 120.0
        # Other cooldowns should use defaults
        assert (
            manager.cooldowns[FailoverReason.BILLING] == DEFAULT_COOLDOWNS[FailoverReason.BILLING]
        )

    def test_mark_profile_failed_with_reason(self):
        """Test marking profile failed with failure reason."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile])

        manager.mark_profile_failed(profile, reason=FailoverReason.AUTH)

        # Profile should be in cooldown
        assert not profile.is_available()
        # Cooldown should be AUTH cooldown (300s)
        expected_cooldown = DEFAULT_COOLDOWNS[FailoverReason.AUTH]
        assert profile.cooldown_until > time.time() + expected_cooldown - 1

    def test_mark_profile_failed_with_explicit_cooldown(self):
        """Test that explicit cooldown overrides reason-based cooldown."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile])

        # Explicit cooldown should override reason
        manager.mark_profile_failed(profile, cooldown=10.0, reason=FailoverReason.AUTH)

        # Should use explicit cooldown (10s), not AUTH cooldown (300s)
        assert profile.cooldown_until < time.time() + 15

    def test_mark_profile_failed_with_error_string(self):
        """Test marking profile failed with error string."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile])

        reason = manager.mark_profile_failed_with_error(profile, "Rate limit exceeded")

        assert reason == FailoverReason.RATE_LIMIT
        assert not profile.is_available()

    def test_mark_profile_failed_with_error_exception(self):
        """Test marking profile failed with exception object."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile])

        error = Exception("Unauthorized access")
        reason = manager.mark_profile_failed_with_error(profile, error)

        assert reason == FailoverReason.AUTH
        assert not profile.is_available()

    def test_different_cooldowns_per_failure_type(self):
        """Test that different failure types get different cooldowns."""
        manager = ProfileManager()

        auth_profile = APIProfile(api_key="auth-key", model="gpt-4")
        rate_profile = APIProfile(api_key="rate-key", model="gpt-4")
        timeout_profile = APIProfile(api_key="timeout-key", model="gpt-4")

        manager.mark_profile_failed(auth_profile, reason=FailoverReason.AUTH)
        manager.mark_profile_failed(rate_profile, reason=FailoverReason.RATE_LIMIT)
        manager.mark_profile_failed(timeout_profile, reason=FailoverReason.TIMEOUT)

        # AUTH has longest cooldown (300s)
        # RATE_LIMIT has medium cooldown (60s)
        # TIMEOUT has shortest cooldown (30s)
        assert auth_profile.cooldown_until > rate_profile.cooldown_until
        assert rate_profile.cooldown_until > timeout_profile.cooldown_until


class TestEnvVarAliases:
    """Test PIG_AGENT_* and LITE_AGENT_* environment variable aliases."""

    def test_from_env_with_pig_agent_key(self, monkeypatch):
        """Test loading from PIG_AGENT_API_KEY."""
        monkeypatch.setenv("PIG_AGENT_API_KEY", "pig-key-123")

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "pig-key-123"

    def test_from_env_with_lite_agent_key(self, monkeypatch):
        """Test loading from LITE_AGENT_API_KEY (backward compat)."""
        monkeypatch.setenv("LITE_AGENT_API_KEY", "lite-key-456")

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "lite-key-456"

    def test_from_env_pig_agent_takes_precedence(self, monkeypatch):
        """Test that PIG_AGENT_* takes precedence over LITE_AGENT_*."""
        monkeypatch.setenv("PIG_AGENT_API_KEY", "pig-key")
        monkeypatch.setenv("LITE_AGENT_API_KEY", "lite-key")

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "pig-key"

    def test_from_env_with_numbered_pig_agent_keys(self, monkeypatch):
        """Test loading numbered PIG_AGENT_API_KEY_* variables."""
        monkeypatch.setenv("PIG_AGENT_API_KEY", "pig-key-0")
        monkeypatch.setenv("PIG_AGENT_API_KEY_1", "pig-key-1")
        monkeypatch.setenv("PIG_AGENT_API_KEY_2", "pig-key-2")

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 3
        assert manager.profiles[0].api_key == "pig-key-0"
        assert manager.profiles[1].api_key == "pig-key-1"
        assert manager.profiles[2].api_key == "pig-key-2"

    def test_from_env_with_numbered_lite_agent_keys(self, monkeypatch):
        """Test loading numbered LITE_AGENT_API_KEY_* variables."""
        monkeypatch.setenv("LITE_AGENT_API_KEY", "lite-key-0")
        monkeypatch.setenv("LITE_AGENT_API_KEY_1", "lite-key-1")

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 2
        assert manager.profiles[0].api_key == "lite-key-0"
        assert manager.profiles[1].api_key == "lite-key-1"

    def test_from_env_custom_prefix_still_works(self, monkeypatch):
        """Test that custom prefix still works."""
        monkeypatch.setenv("CUSTOM_KEY", "custom-123")

        manager = ProfileManager.from_env(env_prefix="CUSTOM_KEY")

        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "custom-123"

    def test_from_env_mixed_sources(self, monkeypatch):
        """Test loading from mixed PIG_AGENT and LITE_AGENT sources."""
        monkeypatch.setenv("PIG_AGENT_API_KEY", "pig-key-0")
        monkeypatch.setenv("LITE_AGENT_API_KEY_1", "lite-key-1")
        monkeypatch.setenv("PIG_AGENT_API_KEY_2", "pig-key-2")

        manager = ProfileManager.from_env()

        # Should load all keys
        assert len(manager.profiles) == 3

    def test_from_env_no_keys_returns_empty(self, monkeypatch):
        """Test that no keys returns empty profile list."""
        # Clear any existing keys
        for key in list(os.environ.keys()):
            if "API_KEY" in key:
                monkeypatch.delenv(key, raising=False)

        manager = ProfileManager.from_env()

        assert len(manager.profiles) == 0


class TestBackwardCompatibility:
    """Test that enhanced features maintain backward compatibility."""

    def test_mark_profile_failed_without_reason_still_works(self):
        """Test that old mark_profile_failed API still works."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile])

        # Old API: just cooldown parameter
        manager.mark_profile_failed(profile, cooldown=30.0)

        assert not profile.is_available()

    def test_mark_profile_failed_no_params_uses_default(self):
        """Test that mark_profile_failed with no params uses default cooldown."""
        profile = APIProfile(api_key="test-key", model="gpt-4")
        manager = ProfileManager(profiles=[profile], default_cooldown=45.0)

        manager.mark_profile_failed(profile)

        # Should use default cooldown
        assert profile.cooldown_until > time.time() + 40

    def test_from_env_without_aliases_still_works(self, monkeypatch):
        """Test that from_env without aliases still works."""
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

        manager = ProfileManager.from_env(env_prefix="OPENAI_API_KEY")

        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "openai-key"
