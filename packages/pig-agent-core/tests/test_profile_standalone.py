#!/usr/bin/env python3
"""Standalone test for ProfileManager."""

import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import directly from resilience module
from pig_agent_core.resilience.profile import APIProfile, ProfileManager


def test_api_profile_creation():
    """Test APIProfile creation."""
    profile = APIProfile(api_key="test-key", model="gpt-4")
    assert profile.api_key == "test-key"
    assert profile.model == "gpt-4"
    assert profile.cooldown_until == 0.0
    print("✓ test_api_profile_creation passed")


def test_api_profile_is_available():
    """Test profile availability check."""
    profile = APIProfile(api_key="test-key", model="gpt-4")
    assert profile.is_available()

    profile.set_cooldown(0.5)
    assert not profile.is_available()

    time.sleep(0.6)
    assert profile.is_available()
    print("✓ test_api_profile_is_available passed")


def test_profile_manager_creation():
    """Test ProfileManager creation."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles, fallback_models=["gpt-3.5-turbo"])

    assert len(manager.profiles) == 2
    assert manager.fallback_models == ["gpt-3.5-turbo"]
    print("✓ test_profile_manager_creation passed")


def test_profile_manager_rotation():
    """Test profile rotation."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    p1 = manager.get_next_profile()
    assert p1.api_key == "key1"

    p2 = manager.get_next_profile()
    assert p2.api_key == "key2"

    p3 = manager.get_next_profile()
    assert p3.api_key == "key3"

    # Wrap around
    p4 = manager.get_next_profile()
    assert p4.api_key == "key1"
    print("✓ test_profile_manager_rotation passed")


def test_profile_manager_skip_cooldown():
    """Test skipping profiles in cooldown."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
        APIProfile(api_key="key3", model="gpt-4"),
    ]
    manager = ProfileManager(profiles=profiles)

    p1 = manager.get_next_profile()
    assert p1.api_key == "key1"
    manager.mark_profile_failed(p1, cooldown=10.0)

    p2 = manager.get_next_profile()
    assert p2.api_key == "key2"
    print("✓ test_profile_manager_skip_cooldown passed")


def test_profile_manager_fallback():
    """Test fallback model selection."""
    manager = ProfileManager(
        profiles=[],
        fallback_models=["gpt-4", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"],
    )

    fallback = manager.get_fallback_model("gpt-4")
    assert fallback == "gpt-3.5-turbo"

    fallback = manager.get_fallback_model("gpt-3.5-turbo")
    assert fallback == "gpt-3.5-turbo-16k"

    fallback = manager.get_fallback_model("gpt-3.5-turbo-16k")
    assert fallback is None
    print("✓ test_profile_manager_fallback passed")


def main():
    """Run all tests."""
    print("Running ProfileManager tests...")
    print()

    test_api_profile_creation()
    test_api_profile_is_available()
    test_profile_manager_creation()
    test_profile_manager_rotation()
    test_profile_manager_skip_cooldown()
    test_profile_manager_fallback()

    print()
    print("All tests passed! ✓")


if __name__ == "__main__":
    main()
