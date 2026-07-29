"""Regression coverage for compaction, retry, and usage lifecycle semantics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pig_agent_core import Agent, CompactionReason, Session, UsageKind, UsageLedger
from pig_agent_core.models import ToolModelCapabilities
from pig_agent_core.observability.events import AgentEvent, AgentEventType
from pig_agent_core.resilience.profile import APIProfile, ProfileManager
from pig_agent_core.resilience.retry import (
    ResilienceExhaustedError,
    resilient_call,
    resilient_streaming_call,
)
from pig_agent_core.tools import ToolResult
from pig_llm import LLM, Message, ModelRuntime, ProviderRegistration, Response, StreamChunk


def test_usage_ledger_keeps_categories_separate() -> None:
    ledger = UsageLedger()

    ledger.record_llm(
        kind=UsageKind.ASSISTANT,
        model="test-model",
        input_tokens=100,
        output_tokens=20,
        cached_tokens=10,
    )
    ledger.record_tool("read")
    ledger.record_compaction(
        reason=CompactionReason.THRESHOLD,
        before_tokens=90,
        after_tokens=35,
    )
    ledger.record_llm(
        kind=UsageKind.BRANCH_SUMMARY,
        model="test-model",
        input_tokens=40,
        output_tokens=8,
    )

    snapshot = ledger.snapshot()
    assert snapshot["llm_calls"] == 2
    assert snapshot["tool_calls"] == 1
    assert snapshot["input_tokens"] == 140
    assert snapshot["output_tokens"] == 28
    assert snapshot["by_kind"]["assistant"]["input_tokens"] == 100
    assert snapshot["by_kind"]["branch_summary"]["input_tokens"] == 40
    assert snapshot["by_kind"]["compaction"]["tokens_reclaimed"] == 55
    assert snapshot["by_kind"]["tool"]["calls"] == 1


def test_session_compaction_persists_reason_checkpoint_and_usage(tmp_path) -> None:
    session = Session(name="checkpoint", workspace=str(tmp_path), auto_save=False)
    for index in range(12):
        session.add_message("user", f"message {index}")

    before_root = session.tree.root_id
    before_current = session.tree.current_id
    compacted = session.compact(
        reason=CompactionReason.THRESHOLD,
        usage={"before_tokens": 1200, "after_tokens": 420},
    )

    checkpoint = session.last_compaction_checkpoint
    assert checkpoint is not None
    assert checkpoint.reason is CompactionReason.THRESHOLD
    assert checkpoint.before_root_id == before_root
    assert checkpoint.before_current_id == before_current
    assert checkpoint.after_root_id == session.tree.root_id
    assert checkpoint.after_current_id == session.tree.current_id
    assert checkpoint.original_count == 7
    assert checkpoint.compacted_count == len(compacted)
    assert checkpoint.before_tokens == 1200
    assert checkpoint.after_tokens == 420
    assert checkpoint.tokens_reclaimed == 780

    root = session.tree.entries[session.tree.root_id]
    assert root.metadata["compaction_checkpoint"]["reason"] == "threshold"
    assert session.metadata["usage"]["by_kind"]["compaction"]["tokens_reclaimed"] == 780

    loaded = Session.load(session.save())
    loaded_checkpoint = loaded.last_compaction_checkpoint
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.id == checkpoint.id
    assert loaded.tree.current_id == checkpoint.after_current_id
    assert loaded.tree.root_id == checkpoint.after_root_id


def test_replacement_compaction_omits_only_the_leading_host_system_prompt() -> None:
    session = Session(name="replacement", auto_save=False)
    for index in range(12):
        session.add_message("user", f"original {index}")

    replacement = [
        Message(role="system", content="host base prompt"),
        Message(role="system", content="request-local instruction"),
        Message(
            role="system",
            content="compacted history",
            metadata={"compacted": True},
        ),
        Message(role="user", content="latest"),
    ]
    compacted = session.compact(
        reason=CompactionReason.OVERFLOW,
        replacement_messages=replacement,
    )

    assert [(entry.role, entry.content) for entry in compacted] == [
        ("system", "request-local instruction"),
        ("system", "compacted history"),
        ("user", "latest"),
    ]


def test_short_session_compaction_is_a_noop_without_checkpoint() -> None:
    session = Session(name="short", auto_save=False)
    session.add_message("user", "hello")

    before_metadata = dict(session.metadata)
    result = session.compact(reason=CompactionReason.MANUAL)

    assert len(result) == 1
    assert session.last_compaction_checkpoint is None
    assert session.metadata == before_metadata


def test_agent_maps_runtime_capabilities_and_anchors_added_tools() -> None:
    llm = Mock()
    llm.config.provider = "custom"
    llm.config.model = "model-a"
    llm.runtime.get_model.return_value.capabilities.strict_json = True
    llm.runtime.get_model.return_value.capabilities.grammar = True
    llm.runtime.get_model.return_value.capabilities.deferred_tools = True
    llm.runtime.get_model.return_value.capabilities.grammar_types = frozenset({"regex"})
    agent = Agent(llm=llm)
    agent.session = Session(name="tools", auto_save=False)
    agent.registry.register(
        "late_tool",
        lambda: ToolResult(ok=True, data="ok"),
        {
            "type": "function",
            "function": {
                "name": "late_tool",
                "description": "late",
                "parameters": {"type": "object", "properties": {}},
                "strict_json": "require",
            },
        },
        is_core=False,
    )

    capabilities = agent._resolve_tool_capabilities()
    assert capabilities == ToolModelCapabilities(
        supports_strict_tools=True,
        supported_grammar_tools={"regex"},
        supports_deferred_tools=True,
    )
    schemas = agent._get_tool_schemas()
    assert schemas[0]["function"]["strict"] is True
    assert schemas[0]["function"]["defer_loading"] is True

    agent._observe_tool_result(
        "discover_tools",
        ToolResult(ok=True, data="loaded", added_tool_names=["late_tool"]),
    )
    assert agent.session.available_tool_names_at() == {"late_tool"}
    assert agent.usage.snapshot()["by_kind"]["tool"]["calls"] == 1
    schemas = agent._get_tool_schemas()
    assert "defer_loading" not in schemas[0]["function"]


def test_agent_records_llm_usage_category_in_ledger_and_billing_metadata() -> None:
    hook = Mock()
    llm = Mock()
    llm.config.model = "model-a"
    agent = Agent(llm=llm, billing_hook=hook)

    agent._record_llm_usage(
        ["answer"],
        {"input_tokens": 12, "output_tokens": 3, "cached_tokens": 2},
        kind=UsageKind.BRANCH_SUMMARY,
    )

    assert agent.usage.snapshot()["by_kind"]["branch_summary"]["input_tokens"] == 12
    assert hook.on_llm_call.call_args.kwargs["metadata"]["usage_kind"] == "branch_summary"


def test_agent_filters_new_billing_fields_for_legacy_hooks() -> None:
    calls: list[tuple[str, int, int]] = []

    class LegacyHook:
        def on_llm_call(self, model: str, input_tokens: int, output_tokens: int) -> None:
            calls.append((model, input_tokens, output_tokens))

    llm = Mock()
    llm.config.model = "model-a"
    agent = Agent(llm=llm, billing_hook=LegacyHook())

    agent._record_llm_usage(["answer"], {"input_tokens": 12, "output_tokens": 3})

    assert calls == [("model-a", 12, 3)]


def test_agent_does_not_reinvoke_a_hook_that_raises_type_error() -> None:
    class RaisingHook:
        calls = 0

        def on_tool_call(self, tool_name: str) -> None:
            self.calls += 1
            raise TypeError(f"hook failure for {tool_name}")

    hook = RaisingHook()
    llm = Mock()
    llm.config.model = "model-a"
    agent = Agent(llm=llm, billing_hook=hook)

    agent._observe_tool_result("read_file", ToolResult(ok=True))

    assert hook.calls == 1


def test_session_save_flushes_current_usage_ledger(tmp_path) -> None:
    path = tmp_path / "usage.jsonl"
    session = Session(name="usage", auto_save=False)
    session.usage_ledger.record_tool("read_file")

    session.save(path)
    loaded = Session.load(path)

    assert loaded.usage_ledger.snapshot()["by_kind"]["tool"]["calls"] == 1


def test_agent_persists_overflow_checkpoint_only_after_retry_success() -> None:
    delivered: list[AgentEvent] = []
    llm = Mock()
    llm.config.model = "model-a"
    agent = Agent(llm=llm, event_callback=delivered.append)
    agent.session = Session(name="overflow", auto_save=False)
    agent.usage = agent.session.usage_ledger
    for index in range(12):
        agent.session.add_message("user", f"message {index}")

    compact = AgentEvent(
        type=AgentEventType.SPAN_START,
        data={
            "event_subtype": "resilience_compact",
            "retry_id": "retry-1",
            "checkpoint_id": "checkpoint-1",
            "reason": "overflow",
            "original_count": 12,
            "compressed_count": 5,
        },
    )
    agent._handle_resilience_event(compact)
    assert "last_overflow_checkpoint" not in agent.session.metadata

    agent._handle_resilience_event(
        AgentEvent(
            type=AgentEventType.SPAN_START,
            data={
                "event_subtype": "resilience_retry_succeeded",
                "phase": "succeeded",
                "retry_id": "retry-1",
                "compaction_checkpoint_id": "checkpoint-1",
            },
        )
    )

    checkpoint = agent.session.metadata["last_overflow_checkpoint"]
    assert checkpoint["id"] == "checkpoint-1"
    assert checkpoint["reason"] == "overflow"
    assert checkpoint["original_count"] == 7
    assert checkpoint["compacted_count"] == 6
    assert checkpoint["completed"] is True
    assert agent.usage.snapshot()["by_kind"]["compaction"]["calls"] == 1
    assert len(delivered) == 2
    assert delivered[0] is compact


@pytest.mark.asyncio
async def test_primary_stream_path_recovers_overflow_and_persists_checkpoint(tmp_path) -> None:
    events: list[AgentEvent] = []

    class OverflowLLM:
        def __init__(self) -> None:
            self.config = SimpleNamespace(model="test-model", max_retries=2)
            self.calls = 0

        async def achat_stream(self, *, messages, **kwargs):
            del messages, kwargs
            self.calls += 1
            if self.calls == 1:
                raise Exception("context length exceeded")
            yield StreamChunk(content="recovered")

    llm = OverflowLLM()
    agent = Agent(
        llm=llm,
        event_callback=events.append,
        compress_fn=lambda messages: messages[-3:],
    )
    agent.history = [Message(role="user", content=f"history {i}") for i in range(11)]
    agent.session = Session(name="overflow-primary", auto_save=False)
    agent.usage = agent.session.usage_ledger
    for index in range(12):
        agent.session.add_message("user", f"session {index}")

    received = [chunk async for chunk in agent.respond_stream("latest", max_iterations=1)]

    assert received == ["recovered"]
    assert llm.calls == 2
    assert len(agent.history) == 4  # three compressed inputs plus the assistant result
    compact_event = next(
        event for event in events if event.data.get("event_subtype") == "resilience_compact"
    )
    checkpoint = agent.session.last_compaction_checkpoint
    assert checkpoint is not None
    assert checkpoint.reason is CompactionReason.OVERFLOW
    assert checkpoint.id == compact_event.data["checkpoint_id"]
    assert (
        agent.session.metadata["last_overflow_checkpoint"]["retry_id"]
        == compact_event.data["retry_id"]
    )

    loaded = Session.load(agent.session.save(tmp_path / "overflow.jsonl"))
    assert loaded.last_compaction_checkpoint is not None
    assert loaded.last_compaction_checkpoint.id == checkpoint.id
    assert len(loaded.get_current_conversation()) < 12
    assert [(entry.role, entry.content) for entry in loaded.get_current_conversation()] == [
        (message.role, message.content) for message in agent.history[:-1]
    ]


@pytest.mark.asyncio
async def test_primary_stream_path_never_replays_partial_output() -> None:
    events: list[AgentEvent] = []

    class PartialLLM:
        def __init__(self) -> None:
            self.config = SimpleNamespace(model="test-model", max_retries=3)
            self.calls = 0

        async def achat_stream(self, *, messages, **kwargs):
            del messages, kwargs
            self.calls += 1
            yield StreamChunk(content="partial")
            raise Exception("temporary network error")

    llm = PartialLLM()
    agent = Agent(llm=llm, event_callback=events.append)
    received: list[str] = []

    with pytest.raises(Exception, match="temporary network error"):
        async for chunk in agent.respond_stream("hello", max_iterations=1):
            received.append(chunk)

    assert received == ["partial"]
    assert llm.calls == 1
    assert [message.content for message in agent.history].count("partial") == 1
    exhausted = [event for event in events if event.data.get("phase") == "exhausted"]
    assert len(exhausted) == 1
    assert exhausted[0].data["reason"] == "partial_output"


def test_primary_sync_path_uses_correlated_overflow_recovery() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    llm.config.model = "test-model"
    llm.config.max_retries = 2
    llm.chat.side_effect = [
        Exception("context length exceeded"),
        Response(content="recovered", model="test-model"),
    ]
    agent = Agent(
        llm=llm,
        event_callback=events.append,
        compress_fn=lambda messages: messages[-2:],
        max_iterations=1,
    )
    agent.history = [Message(role="user", content=f"history {i}") for i in range(6)]
    agent.session = Session(name="sync-overflow", auto_save=False)
    agent.usage = agent.session.usage_ledger
    for index in range(12):
        agent.session.add_message("user", f"session {index}")

    response = agent.run("latest")

    assert response.content == "recovered"
    assert llm.chat.call_count == 2
    assert len(agent.history) == 3
    compact = next(
        event for event in events if event.data.get("event_subtype") == "resilience_compact"
    )
    succeeded = next(event for event in events if event.data.get("phase") == "succeeded")
    assert compact.data["retry_id"] == succeeded.data["retry_id"]
    assert agent.session.last_compaction_checkpoint is not None
    assert agent.session.last_compaction_checkpoint.id == compact.data["checkpoint_id"]


def test_primary_sync_path_records_provider_usage() -> None:
    llm = Mock()
    llm.config.model = "test-model"
    llm.config.max_retries = 1
    llm.chat.return_value = Response(
        content="done",
        model="test-model",
        usage={"input_tokens": 11, "output_tokens": 4, "cached_tokens": 2},
    )
    agent = Agent(llm=llm, max_iterations=1)

    response = agent.run("hello")

    assert response.content == "done"
    assert agent.last_llm_usage == {
        "input_tokens": 11,
        "output_tokens": 4,
        "cached_tokens": 2,
    }
    assistant = agent.usage.snapshot()["by_kind"]["assistant"]
    assert assistant == {
        "calls": 1,
        "input_tokens": 11,
        "output_tokens": 4,
        "cached_tokens": 2,
    }


@pytest.mark.asyncio
async def test_profile_rotation_rebuilds_client_before_emitting_strategy() -> None:
    events: list[AgentEvent] = []
    used_profiles: list[tuple[str, str | None]] = []

    class RotatableLLM:
        def __init__(self, api_key: str, model: str = "initial-model") -> None:
            self.api_key = api_key
            self.config = SimpleNamespace(model=model)

        def with_profile(self, *, api_key: str, model: str):
            return RotatableLLM(api_key, model)

        async def achat(self, *, messages, **kwargs):
            del messages
            used_profiles.append((self.api_key, kwargs.get("model")))
            if self.api_key == "key-one":
                raise Exception("rate limit exceeded")
            return Response(content="ok", model=self.config.model)

    profiles = ProfileManager(
        profiles=[
            APIProfile(api_key="key-one", model="initial-model"),
            APIProfile(api_key="key-two", model="rotated-model"),
        ]
    )
    result = await resilient_call(
        RotatableLLM("key-one"),
        messages=[],
        profile_manager=profiles,
        max_retries=2,
        event_callback=events.append,
        model="initial-model",
    )

    assert result == "ok"
    assert used_profiles == [
        ("key-one", "initial-model"),
        ("key-two", "rotated-model"),
    ]
    rotation = next(
        event
        for event in events
        if event.data.get("event_subtype") == "resilience_profile_rotation"
    )
    assert rotation.data["from_profile"].startswith("sha256:")
    assert rotation.data["to_profile"].startswith("sha256:")
    assert "key-one" not in str(rotation.data)
    assert "key-two" not in str(rotation.data)


@pytest.mark.asyncio
async def test_real_pig_llm_client_rotates_profile_through_local_runtime() -> None:
    created_profiles: list[tuple[str | None, str | None]] = []

    class ProfileAwareProvider:
        def __init__(self, config) -> None:
            self.config = config
            created_profiles.append((config.api_key, config.model))

        async def acomplete(self, *, messages, model, **kwargs):
            del messages, kwargs
            if self.config.api_key == "key-one":
                raise Exception("rate limit exceeded")
            return Response(content="rotated", model=model)

    runtime = ModelRuntime(environment={})
    runtime.register_provider(
        ProviderRegistration(
            "integration",
            ProfileAwareProvider,
            requires_api_key=True,
        )
    )
    llm = LLM(
        provider="integration",
        api_key="key-one",
        model="model-one",
        runtime=runtime,
    )
    profiles = ProfileManager(
        profiles=[
            APIProfile(api_key="key-one", model="model-one", provider="integration"),
            APIProfile(api_key="key-two", model="model-two", provider="integration"),
        ]
    )

    result = await resilient_call(
        llm,
        messages=[Message(role="user", content="hello")],
        profile_manager=profiles,
        max_retries=2,
        model="model-one",
    )

    assert result == "rotated"
    assert created_profiles == [
        ("key-one", "model-one"),
        ("key-two", "model-two"),
    ]


@pytest.mark.asyncio
async def test_streaming_rotation_uses_public_api_with_new_key_and_model() -> None:
    used_profiles: list[tuple[str, str | None]] = []

    class RotatableStreamingLLM:
        def __init__(self, api_key: str, model: str = "initial-model") -> None:
            self.api_key = api_key
            self.config = SimpleNamespace(model=model)

        def with_profile(self, *, api_key: str, model: str):
            return RotatableStreamingLLM(api_key, model)

        async def achat_stream(self, *, messages, **kwargs):
            del messages
            used_profiles.append((self.api_key, kwargs.get("model")))
            if self.api_key == "key-one":
                raise Exception("rate limit exceeded")
            yield StreamChunk(content="ok")

    profiles = ProfileManager(
        profiles=[
            APIProfile(api_key="key-one", model="initial-model"),
            APIProfile(api_key="key-two", model="rotated-model"),
        ]
    )
    received = [
        chunk.content
        async for chunk in resilient_streaming_call(
            RotatableStreamingLLM("key-one"),
            messages=[],
            profile_manager=profiles,
            max_retries=2,
            model="initial-model",
        )
    ]

    assert received == ["ok"]
    assert used_profiles == [
        ("key-one", "initial-model"),
        ("key-two", "rotated-model"),
    ]


@pytest.mark.asyncio
async def test_retry_lifecycle_has_stable_id_and_terminal_success() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    response = Mock(content="ok")
    llm.achat = AsyncMock(side_effect=[Exception("temporary network error"), response])
    llm.config.model = "test-model"

    assert (
        await resilient_call(
            llm,
            messages=[],
            max_retries=2,
            event_callback=events.append,
        )
        == "ok"
    )

    lifecycle = [event for event in events if event.data.get("retry_id")]
    assert {event.data["phase"] for event in lifecycle} == {"failed", "succeeded"}
    assert len({event.data["retry_id"] for event in lifecycle}) == 1
    assert lifecycle[-1].data["attempt"] == 2
    assert lifecycle[-1].data["reason"] == "retry_succeeded"


@pytest.mark.asyncio
async def test_overflow_compaction_event_is_correlated_to_successful_retry() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    response = Mock(content="ok")
    llm.achat = AsyncMock(side_effect=[Exception("context length exceeded"), response])
    llm.config.model = "test-model"

    result = await resilient_call(
        llm,
        messages=[Mock(), Mock(), Mock()],
        compress_fn=lambda messages: messages[:1],
        max_retries=2,
        event_callback=events.append,
    )

    assert result == "ok"
    compact = next(
        event for event in events if event.data.get("event_subtype") == "resilience_compact"
    )
    succeeded = next(event for event in events if event.data.get("phase") == "succeeded")
    assert compact.data["reason"] == "overflow"
    assert compact.data["checkpoint_id"]
    assert compact.data["retry_id"] == succeeded.data["retry_id"]
    assert succeeded.data["compaction_checkpoint_id"] == compact.data["checkpoint_id"]


@pytest.mark.asyncio
async def test_streaming_does_not_retry_after_partial_output() -> None:
    attempts = 0

    async def partial_stream(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        yield Mock(content="partial")
        raise Exception("temporary network error")

    llm = Mock()
    llm.achat_stream = partial_stream
    llm.config.model = "test-model"

    received = []
    with pytest.raises(ResilienceExhaustedError) as exc_info:
        async for chunk in resilient_streaming_call(llm, messages=[], max_retries=3):
            received.append(chunk.content)

    assert received == ["partial"]
    assert attempts == 1
    assert exc_info.value.attempts == 1
    assert "partial_stream_no_retry" in exc_info.value.strategies_tried


@pytest.mark.asyncio
async def test_exhausted_retry_emits_a_terminal_lifecycle_event() -> None:
    events: list[AgentEvent] = []
    llm = Mock()
    llm.achat = AsyncMock(side_effect=Exception("persistent provider error"))
    llm.config.model = "test-model"

    with pytest.raises(ResilienceExhaustedError):
        await resilient_call(
            llm,
            messages=[],
            max_retries=2,
            event_callback=events.append,
        )

    terminal = [event for event in events if event.data.get("phase") == "exhausted"]
    assert len(terminal) == 1
    assert terminal[0].data["attempt"] == 3
    assert terminal[0].data["reason"] == "retries_exhausted"


@pytest.mark.asyncio
async def test_last_attempt_strategy_still_emits_terminal_exhaustion() -> None:
    events: list[AgentEvent] = []

    class AlwaysLimitedLLM:
        def __init__(self, api_key: str, model: str) -> None:
            self.api_key = api_key
            self.config = SimpleNamespace(model=model)

        def with_profile(self, *, api_key: str, model: str):
            return AlwaysLimitedLLM(api_key, model)

        async def achat(self, *, messages, **kwargs):
            del messages, kwargs
            raise Exception("rate limit exceeded")

    profiles = ProfileManager(
        profiles=[
            APIProfile(api_key="key-one", model="model-one"),
            APIProfile(api_key="key-two", model="model-two"),
        ]
    )

    with pytest.raises(ResilienceExhaustedError):
        await resilient_call(
            AlwaysLimitedLLM("key-one", "model-one"),
            messages=[],
            profile_manager=profiles,
            max_retries=1,
            event_callback=events.append,
        )

    terminal = [event for event in events if event.data.get("phase") == "exhausted"]
    assert len(terminal) == 1
    assert terminal[0].data["attempt"] == 2
