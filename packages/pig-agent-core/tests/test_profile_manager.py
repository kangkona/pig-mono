"""Tests for profile manager."""

import os
import time

from pig_agent_core.resilience.profile import APIProfile, ProfileManager


def test_api_profile_creation():
    """Test APIProfile creation."""
    profile = APIProfile(api_key="test-key", model="gpt-4")

    assert profile.api_key == "test-key"
    assert profile.model == "gpt-4"
    assert profile.cooldown_until == 0.0
    assert profile.metadata == {}


def test_api_profile_is_available():
    """Test profile availability check."""
    profile = APIProfile(api_key="test-key", model="gpt-4")

    # Initially available
    assert profile.is_available()

    # Set cooldown
    profile.set_cooldown(1.0)
    assert not profile.is_available()

    # Wait for cooldown
    time.sleep(1.1)
    assert profile.is_available()


def test_api_profile_set_cooldown():
    """Test setting cooldown."""
    profile = APIProfile(api_key="test-key", model="gpt-4")

    profile.set_cooldown(2.0)
    assert profile.cooldown_until > time.time()
    assert profile.cooldown_until <= time.time() + 2.0


def test_profile_manager_creation():
    """Test ProfileManager creation."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles, fallback_models=["gpt-3.5-turbo"])

    assert len(manager.profiles) == 2
    assert manager.fallback_models == ["gpt-3.5-turbo"]
    assert manager.default_cooldown == 60.0


def test_profile_manager_get_next_profile():
    """Test getting next available profile."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Should rotate through profiles
    p1 = manager.get_next_profile()
    assert p1.api_key == "key1"

    p2 = manager.get_next_profile()
    assert p2.api_key == "key2"

    p3 = manager.get_next_profile()
    assert p3.api_key == "key3"

    # Should wrap around
    p4 = manager.get_next_profile()
    assert p4.api_key == "key1"


def test_profile_manager_skip_cooldown():
    """Test skipping profiles in cooldown."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Get first profile and mark it as failed
    p1 = manager.get_next_profile()
    assert p1.api_key == "key1"
    manager.mark_profile_failed(p1, cooldown=10.0)

    # Should skip to next available
    p2 = manager.get_next_profile()
    assert p2.api_key == "key2"

    # Mark second as failed too
    manager.mark_profile_failed(p2, cooldown=10.0)

    # Should get third
    p3 = manager.get_next_profile()
    assert p3.api_key == "key3"


def test_profile_manager_all_in_cooldown():
    """Test when all profiles are in cooldown."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Mark all as failed
    for profile in profiles:
        manager.mark_profile_failed(profile, cooldown=10.0)

    # Should return None
    result = manager.get_next_profile()
    assert result is None


def test_profile_manager_empty():
    """Test manager with no profiles."""
    manager = ProfileManager(profiles=[])

    result = manager.get_next_profile()
    assert result is None


def test_profile_manager_from_env_single_key(monkeypatch):
    """Test loading from environment with single key."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    manager = ProfileManager.from_env(
        env_prefix="OPENAI_API_KEY",
        model="gpt-4",
    )

    assert len(manager.profiles) == 1
    assert manager.profiles[0].api_key == "test-key"
    assert manager.profiles[0].model == "gpt-4"


def test_profile_manager_from_env_multiple_keys(monkeypatch):
    """Test loading from environment with multiple keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "key0")
    monkeypatch.setenv("OPENAI_API_KEY_1", "key1")
    monkeypatch.setenv("OPENAI_API_KEY_2", "key2")
    monkeypatch.setenv("OPENAI_API_KEY_3", "key3")

    manager = ProfileManager.from_env(
        env_prefix="OPENAI_API_KEY",
        model="gpt-4",
    )

    # Should load base key + numbered keys
    assert len(manager.profiles) == 4
    assert manager.profiles[0].api_key == "key0"
    assert manager.profiles[1].api_key == "key1"
    assert manager.profiles[2].api_key == "key2"
    assert manager.profiles[3].api_key == "key3"


def test_profile_manager_from_env_no_keys(monkeypatch):
    """Test loading from environment with no keys."""
    # Clear any existing keys
    for key in list(os.environ.keys()):
        if key.startswith("OPENAI_API_KEY"):
            monkeypatch.delenv(key, raising=False)

    manager = ProfileManager.from_env(
        env_prefix="OPENAI_API_KEY",
        model="gpt-4",
    )

    assert len(manager.profiles) == 0


def test_profile_manager_get_fallback_model():
    """Test getting fallback model."""
    manager = ProfileManager(
        profiles=[],
        fallback_models=["gpt-4", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"],
    )

    # Get fallback for gpt-4
    fallback = manager.get_fallback_model("gpt-4")
    assert fallback == "gpt-3.5-turbo"

    # Get fallback for gpt-3.5-turbo
    fallback = manager.get_fallback_model("gpt-3.5-turbo")
    assert fallback == "gpt-3.5-turbo-16k"

    # Get fallback for last model (no fallback)
    fallback = manager.get_fallback_model("gpt-3.5-turbo-16k")
    assert fallback is None

    # Get fallback for unknown model (returns first)
    fallback = manager.get_fallback_model("unknown-model")
    assert fallback == "gpt-4"


def test_profile_manager_no_fallback():
    """Test manager with no fallback models."""
    manager = ProfileManager(profiles=[], fallback_models=[])

    fallback = manager.get_fallback_model("gpt-4")
    assert fallback is None


def test_profile_manager_add_profile():
    """Test adding profile."""
    manager = ProfileManager(profiles=[])

    profile = APIProfile(api_key="new-key", model="gpt-4")
    manager.add_profile(profile)

    assert len(manager.profiles) == 1
    assert manager.profiles[0].api_key == "new-key"


def test_profile_manager_remove_profile():
    """Test removing profile."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Remove middle profile
    removed = manager.remove_profile("key2")
    assert removed is True
    assert len(manager.profiles) == 2
    assert manager.profiles[0].api_key == "key1"
    assert manager.profiles[1].api_key == "key3"

    # Try to remove non-existent profile
    removed = manager.remove_profile("key-not-exist")
    assert removed is False
    assert len(manager.profiles) == 2


def test_profile_manager_get_all_profiles():
    """Test getting all profiles."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    all_profiles = manager.get_all_profiles()
    assert len(all_profiles) == 2
    assert all_profiles[0].api_key == "key1"
    assert all_profiles[1].api_key == "key2"

    # Should return a copy
    all_profiles.append(APIProfile(api_key="key3", model="gpt-4"))
    assert len(manager.profiles) == 2


def test_profile_manager_get_available_profiles():
    """Test getting available profiles."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Initially all available
    available = manager.get_available_profiles()
    assert len(available) == 3

    # Mark one as failed
    manager.mark_profile_failed(profiles[1], cooldown=10.0)

    # Should have 2 available
    available = manager.get_available_profiles()
    assert len(available) == 2
    assert available[0].api_key == "key1"
    assert available[1].api_key == "key3"


def test_profile_manager_mark_profile_failed_default_cooldown():
    """Test marking profile as failed with default cooldown."""
    profile = APIProfile(api_key="key1", model="gpt-4")
    manager = ProfileManager(profiles=[profile], default_cooldown=30.0)

    manager.mark_profile_failed(profile)

    assert not profile.is_available()
    assert profile.cooldown_until > time.time() + 29.0
    assert profile.cooldown_until <= time.time() + 30.0


def test_profile_manager_mark_profile_failed_custom_cooldown():
    """Test marking profile as failed with custom cooldown."""
    profile = APIProfile(api_key="key1", model="gpt-4")
    manager = ProfileManager(profiles=[profile])

    manager.mark_profile_failed(profile, cooldown=5.0)

    assert not profile.is_available()
    assert profile.cooldown_until > time.time() + 4.0
    assert profile.cooldown_until <= time.time() + 5.0


def test_profile_manager_rotation_after_remove():
    """Test rotation continues correctly after removing profile."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    # Get first two profiles
    manager.get_next_profile()  # key1
    manager.get_next_profile()  # key2

    # Remove key2
    manager.remove_profile("key2")

    # Next should be key3
    p = manager.get_next_profile()
    assert p.api_key == "key3"

    # Then wrap to key1
    p = manager.get_next_profile()
    assert p.api_key == "key1"
