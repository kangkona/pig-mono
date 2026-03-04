"""Resilience support for coding agent."""

import os
from typing import Any

from pig_agent_core.resilience.profile import APIProfile, ProfileManager


def create_profile_manager_from_env() -> ProfileManager | None:
    """Create ProfileManager from environment variables.

    Looks for API keys in environment:
    - OPENAI_API_KEY, OPENAI_API_KEY_2, OPENAI_API_KEY_3, ...
    - ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_2, ...
    - GOOGLE_API_KEY, GOOGLE_API_KEY_2, ...

    Returns:
        ProfileManager with discovered profiles, or None if no keys found
    """
    profiles = []

    # Provider configurations
    providers = {
        "openai": {"env_prefix": "OPENAI_API_KEY", "model": "gpt-4"},
        "anthropic": {"env_prefix": "ANTHROPIC_API_KEY", "model": "claude-3-5-sonnet-20241022"},
        "google": {"env_prefix": "GOOGLE_API_KEY", "model": "gemini-pro"},
    }

    for provider_name, config in providers.items():
        env_prefix = config["env_prefix"]
        model = config["model"]

        # Check primary key
        primary_key = os.getenv(env_prefix)
        if primary_key:
            profiles.append(
                APIProfile(
                    api_key=primary_key,
                    model=model,
                    metadata={"provider": provider_name, "key_index": 0},
                )
            )

        # Check numbered keys (_2, _3, etc.)
        for i in range(2, 10):  # Support up to 9 keys per provider
            key = os.getenv(f"{env_prefix}_{i}")
            if key:
                profiles.append(
                    APIProfile(
                        api_key=key,
                        model=model,
                        metadata={"provider": provider_name, "key_index": i},
                    )
                )

    if not profiles:
        return None

    # Create manager with fallback models
    return ProfileManager(
        profiles=profiles,
        fallback_models=[
            "gpt-4",
            "gpt-3.5-turbo",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ],
    )


def get_profile_status(manager: ProfileManager) -> dict[str, Any]:
    """Get status of all profiles in manager.

    Args:
        manager: ProfileManager instance

    Returns:
        Status dictionary with profile information
    """
    status = {
        "total_profiles": len(manager.profiles),
        "available_profiles": 0,
        "cooldown_profiles": 0,
        "profiles": [],
    }

    for profile in manager.profiles:
        is_available = profile.is_available()

        if is_available:
            status["available_profiles"] += 1
        else:
            status["cooldown_profiles"] += 1

        profile_info = {
            "model": profile.model,
            "provider": profile.metadata.get("provider", "unknown"),
            "key_index": profile.metadata.get("key_index", 0),
            "available": is_available,
            "cooldown_until": profile.cooldown_until if not is_available else None,
        }
        status["profiles"].append(profile_info)

    return status
