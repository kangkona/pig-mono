"""Regression tests for retry budgets and persistent profile failover."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from pig_agent_core import Agent
from pig_agent_core.observability.events import AgentEvent
from pig_agent_core.resilience.profile import APIProfile, ProfileManager
from pig_agent_core.resilience.retry import (
    ResilienceExhaustedError,
    resilient_streaming_call,
    resilient_sync_call,
)
from pig_agent_core.resilience.retry import (
    resilient_call as _resilient_call,
)
from pig_llm import LLM, Message, Response


async def resilient_call(llm: object, messages: object, *args: Any, **kwargs: Any) -> Any:
    return await _resilient_call(cast(LLM, llm), cast(list[Message], messages), *args, **kwargs)


class ProfiledLLM:
    def __init__(self, key: str, calls: dict[str, int]) -> None:
        self.key = key
        self.calls = calls
        self.config = SimpleNamespace(model="model", provider="openai", api_key=key, max_retries=1)

    @classmethod
    def with_profile(cls, llm: Any, *, api_key: str, model: str) -> Any:
        del model
        return cls(api_key, llm.calls)

    async def achat(self, *, messages: Any, **kwargs: Any) -> Any:
        del messages, kwargs
        self.calls[self.key] = self.calls.get(self.key, 0) + 1
        if self.key == "bad":
            raise Exception("invalid api key")
        return Response(content="ok", model="model")


@pytest.mark.asyncio
async def test_failed_active_identity_recovers_after_cooldown() -> None:
    calls: dict[str, int] = {}
    failures = {"bad": True, "good": False}

    class RecoveringLLM(ProfiledLLM):
        failures: dict[str, bool]

        @classmethod
        def with_profile(cls, llm: Any, *, api_key: str, model: str) -> Any:
            del model
            instance = cls(api_key, llm.calls)
            instance.failures = llm.failures
            return instance

        async def achat(self, *, messages: Any, **kwargs: Any) -> Any:
            del messages, kwargs
            self.calls[self.key] = self.calls.get(self.key, 0) + 1
            if self.failures[self.key]:
                raise Exception("invalid api key")
            return Response(content="ok", model="model")

    bad = APIProfile(api_key="bad", model="model", provider="openai")
    good = APIProfile(api_key="good", model="model", provider="openai")
    manager = ProfileManager([bad, good])
    llm = RecoveringLLM("bad", calls)
    llm.failures = failures

    assert await resilient_call(llm, [], profile_manager=manager, max_retries=1) == "ok"
    failures["good"] = True
    with pytest.raises(ResilienceExhaustedError):
        await resilient_call(llm, [], profile_manager=manager, max_retries=0)
    assert manager.active_profile is good
    assert manager.active_client is None

    failures["good"] = False
    good.cooldown_until = 0
    assert await resilient_call(llm, [], profile_manager=manager, max_retries=0) == "ok"
    assert calls == {"bad": 1, "good": 3}
    assert manager.active_profile is good
    assert manager.active_client is not None


@pytest.mark.asyncio
async def test_active_profile_is_not_reused_for_a_different_provider_llm() -> None:
    constructed: list[tuple[str, str, str]] = []

    class ProviderLLM:
        def __init__(self, provider: str, api_key: str, model: str) -> None:
            self.config = SimpleNamespace(
                provider=provider,
                api_key=api_key,
                model=model,
                max_retries=0,
            )

        @classmethod
        def with_profile(cls, llm: Any, *, api_key: str, model: str) -> Any:
            constructed.append((llm.config.provider, api_key, model))
            return cls(llm.config.provider, api_key, model)

        async def achat(self, *, messages: Any, **kwargs: Any) -> Any:
            del messages, kwargs
            if self.config.api_key == "untracked-anthropic-key":
                raise Exception("invalid api key")
            return Response(content=self.config.provider, model=self.config.model)

    openai = APIProfile(api_key="openai-key", model="gpt-4", provider="openai")
    anthropic = APIProfile(api_key="anthropic-key", model="claude", provider="anthropic")
    manager = ProfileManager(
        [openai, anthropic],
        provider_fallback_models={
            "openai": ["gpt-4", "gpt-3.5"],
            "anthropic": ["claude", "haiku"],
        },
    )

    assert (
        await resilient_call(
            ProviderLLM("openai", "openai-key", "gpt-4"),
            [],
            profile_manager=manager,
            max_retries=0,
        )
        == "openai"
    )
    with pytest.raises(ResilienceExhaustedError):
        await resilient_call(
            ProviderLLM("anthropic", "untracked-anthropic-key", "claude"),
            [],
            profile_manager=manager,
            max_retries=1,
        )
    assert constructed == []
    assert manager.active_profile is openai
    assert (
        await resilient_call(
            ProviderLLM("anthropic", "anthropic-key", "claude"),
            [],
            profile_manager=manager,
            max_retries=0,
        )
        == "anthropic"
    )

    assert constructed == []
    assert manager.active_profile is anthropic


@pytest.mark.asyncio
async def test_legacy_unscoped_profile_is_bound_to_its_first_real_provider() -> None:
    executed: list[str] = []
    rotated: list[tuple[str, str]] = []

    class ProviderLLM:
        def __init__(self, provider: str, api_key: str) -> None:
            self.config = SimpleNamespace(
                provider=provider,
                api_key=api_key,
                model="model",
            )

        @classmethod
        def with_profile(cls, llm: Any, *, api_key: str, model: str) -> Any:
            del model
            rotated.append((llm.config.provider, api_key))
            return cls(llm.config.provider, api_key)

        async def achat(self, *, messages: Any, **kwargs: Any) -> Any:
            del messages, kwargs
            executed.append(self.config.provider)
            return Response(content=self.config.provider, model="model")

    legacy = APIProfile(api_key="legacy-key", model="model")
    manager = ProfileManager([legacy])

    assert (
        await resilient_call(
            ProviderLLM("openai", "legacy-key"),
            [],
            profile_manager=manager,
            max_retries=0,
        )
        == "openai"
    )
    assert legacy.provider == "openai"
    assert (
        await resilient_call(
            ProviderLLM("anthropic", "anthropic-key"),
            [],
            profile_manager=manager,
            max_retries=0,
        )
        == "anthropic"
    )

    assert executed == ["openai", "anthropic"]
    assert rotated == []


@pytest.mark.asyncio
async def test_mixed_legacy_profiles_never_rotate_across_an_explicit_provider() -> None:
    rotated: list[tuple[str, str, str]] = []

    class FailingOpenAI:
        def __init__(self) -> None:
            self.config = SimpleNamespace(
                provider="openai",
                api_key="openai-key",
                model="gpt-4",
            )

        @classmethod
        def with_profile(cls, llm: Any, *, api_key: str, model: str) -> Any:
            rotated.append((llm.config.provider, api_key, model))
            return cls()

        async def achat(self, *, messages: Any, **kwargs: Any) -> Any:
            del messages, kwargs
            raise Exception("invalid api key")

    openai = APIProfile(api_key="openai-key", model="gpt-4")
    anthropic = APIProfile(api_key="anthropic-secret", model="claude")
    manager = ProfileManager([openai, anthropic])

    with pytest.raises(ResilienceExhaustedError):
        await resilient_call(
            FailingOpenAI(),
            [],
            profile_manager=manager,
            max_retries=1,
        )

    assert openai.provider == "openai"
    assert anthropic.provider is None
    assert rotated == []


@pytest.mark.asyncio
async def test_active_profile_and_client_persist_across_resilient_calls() -> None:
    calls: dict[str, int] = {}
    bad = APIProfile(api_key="bad", model="model", provider="openai")
    good = APIProfile(api_key="good", model="model", provider="openai")
    manager = ProfileManager([bad, good])
    llm = ProfiledLLM("bad", calls)

    assert await resilient_call(llm, [], profile_manager=manager, max_retries=1) == "ok"
    assert await resilient_call(llm, [], profile_manager=manager, max_retries=1) == "ok"

    assert calls == {"bad": 1, "good": 2}
    assert manager.active_profile is good
    assert manager.active_client is not llm
    assert bad.cooldown_until > 0
    assert good.cooldown_until == 0


@pytest.mark.asyncio
async def test_async_zero_retry_budget_still_attempts_once_and_exhausts_once() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    llm.config.model = "model"
    llm.achat.side_effect = Exception("context length exceeded")

    with pytest.raises(ResilienceExhaustedError) as error:
        await resilient_call(
            llm,
            [],
            max_retries=0,
            compress_fn=lambda messages: messages,
            event_callback=events.append,
        )

    assert llm.achat.call_count == 1
    assert error.value.attempts == 1
    assert len([event for event in events if event.data.get("phase") == "exhausted"]) == 1
    assert not [event for event in events if event.data.get("phase") == "strategy"]


@pytest.mark.asyncio
async def test_stream_zero_retry_budget_still_attempts_once() -> None:
    calls = 0
    events: list[AgentEvent] = []

    async def fail_stream(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise Exception("provider failed")
        yield

    llm = Mock()
    llm.config.model = "model"
    llm.achat_stream = fail_stream

    with pytest.raises(ResilienceExhaustedError) as error:
        async for _ in resilient_streaming_call(
            llm, [], max_retries=0, event_callback=events.append
        ):
            pass

    assert calls == 1
    assert error.value.attempts == 1
    assert len([event for event in events if event.data.get("phase") == "exhausted"]) == 1


def test_sync_zero_retry_budget_still_attempts_once() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    llm.config.model = "model"
    llm.chat.side_effect = Exception("provider failed")

    with pytest.raises(ResilienceExhaustedError) as error:
        resilient_sync_call(llm, [], max_retries=0, event_callback=events.append)

    assert llm.chat.call_count == 1
    assert error.value.attempts == 1
    assert len([event for event in events if event.data.get("phase") == "exhausted"]) == 1


@pytest.mark.asyncio
async def test_agent_arun_passes_configured_additional_retry_budget() -> None:
    calls = 0

    async def fail_stream(*, messages: Any, **kwargs: Any) -> Any:
        nonlocal calls
        del messages, kwargs
        calls += 1
        raise Exception("provider failed")
        yield

    llm = Mock()
    llm.config = SimpleNamespace(model="model", max_retries=0)
    llm.achat_stream = fail_stream
    agent = Agent(llm=llm, max_iterations=1)

    with pytest.raises(ResilienceExhaustedError):
        await agent.arun("hello")

    assert calls == 1
