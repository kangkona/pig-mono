"""Regression tests for behavior absorbed from recent pi-mono agent changes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pig_agent_core.agent import Agent as CoreAgent
from pig_agent_core.session import Session, SessionTree, serialize_compaction_tool_result
from pig_agent_core.tools import ToolResult
from pig_llm import LLM, StreamChunk


class Agent(CoreAgent):
    """Test adapter that narrows fake LLMs at the production boundary."""

    def __init__(self, *args: Any, llm: object | None = None, **kwargs: Any) -> None:
        if llm is not None:
            kwargs["llm"] = cast(LLM, llm)
        super().__init__(*args, **kwargs)


def test_session_tree_loads_large_jsonl_incrementally(tmp_path: Any) -> None:
    path = tmp_path / "large.jsonl"
    entries: list[dict[str, Any]] = []
    for i in range(2000):
        entries.append(
            {
                "id": f"entry-{i}",
                "parent_id": f"entry-{i - 1}" if i else None,
                "timestamp": f"2026-06-01T00:00:{i % 60:02d}",
                "role": "user" if i % 2 else "assistant",
                "content": f"message {i}",
                "metadata": {},
            }
        )
    path.write_text("\n".join(json.dumps(entry) for entry in entries))

    tree = SessionTree.from_jsonl_iter(path.open())

    assert len(tree.entries) == 2000
    assert tree.root_id == "entry-0"
    assert tree.current_id == "entry-1999"


def test_session_load_streams_tree_lines_without_reading_full_tail(
    monkeypatch: Any, tmp_path: Any
) -> None:
    session = Session(name="streamed", workspace=str(tmp_path), auto_save=False)
    session.add_message("user", "hello")
    save_path = session.save()

    class GuardedFile:
        def __init__(self, wrapped: Any) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> Any:
            self._wrapped.__enter__()
            return self

        def __exit__(self, *args: Any) -> Any:
            return self._wrapped.__exit__(*args)

        def readline(self, *args: Any, **kwargs: Any) -> Any:
            return self._wrapped.readline(*args, **kwargs)

        def __iter__(self) -> Any:
            return iter(self._wrapped)

        def read(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Session.load should not materialize the whole JSONL tail")

    real_open = open

    def guarded_open(*args: Any, **kwargs: Any) -> Any:
        return GuardedFile(real_open(*args, **kwargs))

    monkeypatch.setattr("builtins.open", guarded_open)

    loaded = Session.load(save_path)

    assert loaded.name == "streamed"
    assert len(loaded.tree.entries) == 1


def test_session_save_keeps_header_small_and_excludes_duplicate_tree_payload(tmp_path: Any) -> None:
    session = Session(name="header-only", workspace=str(tmp_path), auto_save=False)
    for i in range(50):
        session.add_message("user", f"message {i}")
        session.add_message("assistant", "x" * 200)

    save_path = session.save()
    header = json.loads(save_path.read_text().splitlines()[0])

    assert "tree" not in header
    assert header["metadata"]["entries"] == len(session.tree.entries)
    assert len(json.dumps(header)) < 4096


def test_session_save_streams_tree_lines_without_materializing_full_jsonl(
    monkeypatch: Any, tmp_path: Any
) -> None:
    session = Session(name="stream-save", workspace=str(tmp_path), auto_save=False)
    for i in range(3):
        session.add_message("user", f"message {i}")

    def fail_to_jsonl() -> str:
        raise AssertionError("Session.save should stream tree lines directly")

    monkeypatch.setattr(session.tree, "to_jsonl", fail_to_jsonl)

    save_path = session.save()

    lines = save_path.read_text().splitlines()
    assert len(lines) == 4
    header = json.loads(lines[0])
    assert header["name"] == "stream-save"


def test_compaction_tool_result_serialization_is_bounded_and_structured() -> None:
    serialized = serialize_compaction_tool_result(
        ToolResult(ok=True, data={"content": "x" * 5000}),
        max_chars=500,
    )

    assert len(serialized) <= 500
    payload = json.loads(serialized)
    assert payload["ok"] is True


def test_session_compact_keeps_recent_messages_and_bounded_tool_summary() -> None:
    session = Session(name="compact", auto_save=False)
    for i in range(6):
        session.add_message("user", f"user {i}")
        session.add_message("tool", "x" * 2000, name="read_file")

    compacted = session.compact(max_tool_chars=200)

    assert len(compacted) == 6
    summary = compacted[0]
    assert summary.metadata["compacted"] is True
    assert len(summary.content) < 1000
    assert "Tool outputs:" in summary.content


def test_session_compact_updates_current_path_to_summary_plus_recent_tail() -> None:
    session = Session(name="compact-path", auto_save=False)
    for i in range(6):
        session.add_message("user", f"user {i}")
        session.add_message("tool", f"tool {i}", name="read_file")

    tail_before = session.get_current_conversation()[-5:]

    compacted = session.compact(max_tool_chars=200)
    current = session.get_current_conversation()

    assert compacted == current
    assert current[0].metadata["compacted"] is True
    assert [(entry.role, entry.content) for entry in current[1:]] == [
        (entry.role, entry.content) for entry in tail_before
    ]
    assert not ({entry.id for entry in current} & {entry.id for entry in tail_before})
    assert current[-1].role == tail_before[-1].role


def test_repeated_session_compact_keeps_single_summary_and_same_tail() -> None:
    session = Session(name="compact-repeat", auto_save=False)
    for i in range(6):
        session.add_message("user", f"user {i}")
        session.add_message("tool", f"tool {i}", name="read_file")

    first = session.compact(max_tool_chars=200)
    entry_count_after_first = len(session.tree.entries)

    second = session.compact(max_tool_chars=200)

    assert [entry.id for entry in second] == [entry.id for entry in first]
    assert sum(1 for entry in second if entry.metadata.get("compacted")) == 1
    assert len(session.tree.entries) == entry_count_after_first


def test_session_compact_save_load_preserves_recent_tail_after_reload(tmp_path: Any) -> None:
    session = Session(name="compact-reload", workspace=str(tmp_path), auto_save=False)
    for i in range(10):
        session.add_message("user", f"user {i}")
        session.add_message("assistant", f"assistant {i}")

    compacted_before_save = session.compact(max_tool_chars=200)
    save_path = session.save()
    reloaded = Session.load(save_path)

    assert [(entry.role, entry.content) for entry in reloaded.get_current_conversation()] == [
        (entry.role, entry.content) for entry in compacted_before_save
    ]


def test_session_compact_save_preserves_history_and_authoritative_current_root(
    tmp_path: Any,
) -> None:
    session = Session(name="compact-save", workspace=str(tmp_path), auto_save=False)
    for i in range(12):
        session.add_message("user", f"user {i}")

    compacted = session.compact(max_tool_chars=200)
    save_path = session.save()
    persisted_entries = [json.loads(line) for line in save_path.read_text().splitlines()[1:]]

    assert len(persisted_entries) == len(session.tree.entries)
    assert len(persisted_entries) > len(compacted)
    assert sum(1 for entry in persisted_entries if entry.get("parent_id") is None) == 2

    loaded = Session.load(save_path)
    assert loaded.tree.root_id == compacted[0].id
    assert [(entry.role, entry.content) for entry in loaded.get_current_conversation()] == [
        (entry.role, entry.content) for entry in compacted
    ]


def test_agent_before_tool_call_abort_skips_sibling_tools() -> None:
    executed: list[str] = []

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "first", "arguments": "{}"},
                        },
                        {
                            "id": "call-2",
                            "function": {"name": "second", "arguments": "{}"},
                        },
                    ],
                )
            return SimpleNamespace(content="done", tool_calls=None)

    def first() -> Any:
        executed.append("first")
        return "first"

    def second() -> Any:
        executed.append("second")
        return "second"

    def before_tool_call(name: Any, args: Any) -> Any:
        if name == "first":
            return ToolResult(ok=False, error="blocked", meta={"abort_batch": True})
        return None

    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        before_tool_call=before_tool_call,
        verbose=False,
    )
    agent.registry.register("first", first, {"type": "function", "function": {"name": "first"}})
    agent.registry.register("second", second, {"type": "function", "function": {"name": "second"}})

    response = agent.run("go")

    assert response.content == "done"
    assert executed == []
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert len(tool_messages) == 1
    assert "blocked" in tool_messages[0].content


def test_agent_after_tool_call_exception_becomes_error_tool_result() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "ok_tool", "arguments": "{}"},
                        }
                    ],
                )
            return SimpleNamespace(content="done", tool_calls=None)

    def ok_tool() -> Any:
        return "ok"

    def after_tool_call(name: Any, args: Any, result: Any) -> Any:
        raise RuntimeError("after failed")

    agent = Agent(llm=FakeLLM(), tools=[], after_tool_call=after_tool_call, verbose=False)
    agent.registry.register(
        "ok_tool", ok_tool, {"type": "function", "function": {"name": "ok_tool"}}
    )

    agent.run("go")

    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert "after failed" in tool_messages[0].content


@pytest.mark.asyncio
async def test_arun_before_tool_call_abort_skips_sibling_tools() -> None:
    executed: list[str] = []

    class FakeChunk:
        def __init__(self, *, content: str = "", tool_calls: Any = None) -> None:
            self.content = content
            self.tool_calls = tool_calls
            self.usage: dict[str, Any] = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        async def achat_stream(self, messages: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                yield FakeChunk(
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "first", "arguments": "{}"},
                        },
                        {
                            "id": "call-2",
                            "function": {"name": "second", "arguments": "{}"},
                        },
                    ]
                )
            else:
                yield FakeChunk(content="done")

    def first() -> Any:
        executed.append("first")
        return "first"

    def second() -> Any:
        executed.append("second")
        return "second"

    def before_tool_call(name: Any, args: Any) -> Any:
        if name == "first":
            return ToolResult(ok=False, error="blocked", meta={"abort_batch": True})
        return None

    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        before_tool_call=before_tool_call,
        verbose=False,
    )
    agent.registry.register("first", first, {"type": "function", "function": {"name": "first"}})
    agent.registry.register("second", second, {"type": "function", "function": {"name": "second"}})

    response = await agent.arun("go")

    assert response.content == "done"
    assert executed == []
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert len(tool_messages) == 1
    assert "blocked" in tool_messages[0].content


@pytest.mark.asyncio
async def test_arun_after_tool_call_exception_becomes_error_tool_result() -> None:
    class FakeChunk:
        def __init__(self, *, content: str = "", tool_calls: Any = None) -> None:
            self.content = content
            self.tool_calls = tool_calls
            self.usage: dict[str, Any] = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        async def achat_stream(self, messages: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                yield FakeChunk(
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "ok_tool", "arguments": "{}"},
                        }
                    ]
                )
            else:
                yield FakeChunk(content="done")

    def ok_tool() -> Any:
        return "ok"

    def after_tool_call(name: Any, args: Any, result: Any) -> Any:
        raise RuntimeError("after failed")

    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        after_tool_call=after_tool_call,
        verbose=False,
    )
    agent.registry.register(
        "ok_tool", ok_tool, {"type": "function", "function": {"name": "ok_tool"}}
    )

    await agent.arun("go")

    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert "after failed" in tool_messages[0].content


@pytest.mark.asyncio
async def test_arun_awaits_async_tool_handlers_from_registry() -> None:
    class FakeChunk:
        def __init__(self, *, content: str = "", tool_calls: Any = None) -> None:
            self.content = content
            self.tool_calls = tool_calls
            self.usage: dict[str, Any] = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        async def achat_stream(self, messages: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                yield FakeChunk(
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "async_tool", "arguments": "{}"},
                        }
                    ]
                )
            else:
                yield FakeChunk(content="done")

    async def async_tool(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        await asyncio.sleep(0)
        return ToolResult(ok=True, data="async-ok")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "async_tool",
        async_tool,
        {"type": "function", "function": {"name": "async_tool"}},
        validate=False,
    )

    response = await agent.arun("go")

    assert response.content == "done"
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert tool_messages[0].content == "async-ok"


@pytest.mark.asyncio
async def test_arun_executes_parallel_safe_async_tools_concurrently() -> None:
    started: list[str] = []

    class FakeChunk:
        def __init__(self, *, content: str = "", tool_calls: Any = None) -> None:
            self.content = content
            self.tool_calls = tool_calls
            self.usage: dict[str, Any] = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        async def achat_stream(self, messages: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                yield FakeChunk(
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "think", "arguments": "{}"},
                        },
                        {
                            "id": "call-2",
                            "function": {"name": "get_current_time", "arguments": "{}"},
                        },
                    ]
                )
            else:
                yield FakeChunk(content="done")

    async def think(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        started.append("think")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"think-parallel:{'get_current_time' in started}")

    async def get_current_time(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        started.append("get_current_time")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"time-parallel:{'think' in started}")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "think",
        think,
        {"type": "function", "function": {"name": "think"}},
        validate=False,
    )
    agent.registry.register(
        "get_current_time",
        get_current_time,
        {"type": "function", "function": {"name": "get_current_time"}},
        validate=False,
    )

    response = await agent.arun("go")

    assert response.content == "done"
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert tool_messages[0].content == "think-parallel:True"
    assert tool_messages[1].content == "time-parallel:True"


def test_agent_terminate_tool_result_skips_follow_up_llm_call() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def chat(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            return SimpleNamespace(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "function": {"name": "terminate", "arguments": "{}"},
                    }
                ],
            )

    def terminate() -> Any:
        return ToolResult(ok=True, data="finished", meta={"terminate": True})

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    response = agent.run("go")

    assert response.content == "finished"
    assert cast(Any, agent.llm).calls == 1


def test_terminate_tool_result_still_emits_agent_end_and_drains_followup() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0
            self.messages: list[str] = []

        def chat(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            latest = messages[-1].content
            self.messages.append(latest)
            if self.calls == 1:
                return SimpleNamespace(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "function": {"name": "terminate", "arguments": "{}"},
                        }
                    ],
                )
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent_ref: dict[str, Agent] = {}
    queued = {"done": False}

    def on_event(event: Any) -> Any:
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-after-terminate")

    def terminate() -> Any:
        return ToolResult(ok=True, data="finished", meta={"terminate": True})

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, event_callback=on_event)
    agent_ref["agent"] = agent
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    response = agent.run("go")

    assert response.content == "reply:follow-after-terminate"
    assert cast(Any, agent.llm).calls == 2
    assert cast(Any, agent.llm).messages == ["go", "follow-after-terminate"]


def test_agent_followup_queue_processes_all_messages_in_fifo_order() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.messages: list[str] = []

        def chat(self, messages: Any, tools: Any = None) -> Any:
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.message_queue.add_followup("follow-1")
    agent.message_queue.add_followup("follow-2")

    response = agent.run("start")

    assert response.content == "reply:follow-2"
    assert cast(Any, agent.llm).messages == ["start", "follow-1", "follow-2"]


def test_agent_followup_all_mode_processes_entire_batch() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.messages: list[str] = []

        def chat(self, messages: Any, tools: Any = None) -> Any:
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.message_queue.followup_mode = "all"
    agent.message_queue.add_followup("follow-1")
    agent.message_queue.add_followup("follow-2")

    response = agent.run("start")

    assert response.content == "reply:follow-2"
    assert cast(Any, agent.llm).messages == ["start", "follow-1", "follow-2"]


def test_agent_end_callback_can_queue_followup_before_run_returns() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.messages: list[str] = []

        def chat(self, messages: Any, tools: Any = None) -> Any:
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent_ref: dict[str, Agent] = {}

    queued = {"done": False}

    def on_event(event: Any) -> Any:
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-from-end")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, event_callback=on_event)
    agent_ref["agent"] = agent

    response = agent.run("start")

    assert response.content == "reply:follow-from-end"
    assert cast(Any, agent.llm).messages == ["start", "follow-from-end"]


def test_agent_llm_failure_emits_agent_end_failure_event() -> None:
    class FailingLLM:
        config = SimpleNamespace(model="fake")

        def chat(self, messages: Any, tools: Any = None) -> Any:
            raise RuntimeError("boom")

    events = []

    def on_event(event: Any) -> Any:
        if event.type.value == "agent_end":
            events.append(event)

    agent = Agent(llm=FailingLLM(), tools=[], verbose=False, event_callback=on_event)

    with pytest.raises(RuntimeError, match="boom"):
        agent.run("start")

    assert len(events) == 1
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "boom"


@pytest.mark.asyncio
async def test_respond_stream_emits_agent_end_success_event() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield StreamChunk(content="hello")
                yield StreamChunk(content=" world")

            return stream()

    events = []

    def on_event(event: Any) -> Any:
        if event.type.value == "agent_end":
            events.append(event)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, event_callback=on_event)

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["hello", " world"]
    assert len(events) == 1
    assert events[0].data["success"] is True


@pytest.mark.asyncio
async def test_respond_stream_success_drains_followup_queued_from_agent_end() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.messages: list[str] = []

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            latest = messages[-1].content
            self.messages.append(latest)

            async def stream() -> Any:
                yield StreamChunk(content=f"reply:{latest}")

            return stream()

    agent_ref: dict[str, Agent] = {}
    queued = {"done": False}

    def on_event(event: Any) -> Any:
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-from-stream-end")

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False, event_callback=on_event)
    agent_ref["agent"] = agent

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["reply:start", "reply:follow-from-stream-end"]
    assert llm.messages == ["start", "follow-from-stream-end"]


@pytest.mark.asyncio
async def test_respond_stream_cancellation_emits_agent_end_failure_event() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield StreamChunk(content="ignored")

            return stream()

    events = []

    def on_event(event: Any) -> Any:
        if event.type.value == "agent_end":
            events.append(event)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, event_callback=on_event)
    cancel = asyncio.Event()
    cancel.set()

    chunks = []
    async for chunk in agent.respond_stream("start", cancel=cancel):
        chunks.append(chunk)

    assert chunks == []  # aborted cleanly without injecting a fake message
    assert len(events) == 1
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "aborted"


@pytest.mark.asyncio
async def test_respond_stream_llm_failure_emits_agent_end_failure_event() -> None:
    class FailingLLM:
        config = SimpleNamespace(model="fake")

        async def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            if False:
                yield None
            raise RuntimeError("stream boom")

    events = []

    def on_event(event: Any) -> Any:
        if event.type.value == "agent_end":
            events.append(event)

    agent = Agent(llm=FailingLLM(), tools=[], verbose=False, event_callback=on_event)

    with pytest.raises(RuntimeError, match="stream boom"):
        chunks = []
        async for chunk in agent.respond_stream("start"):
            chunks.append(chunk)

    assert len(events) == 1
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "stream boom"


@pytest.mark.asyncio
async def test_respond_stream_terminate_tool_result_skips_followup_llm_call() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "terminate", "arguments": "{}"},
                            }
                        ],
                    )
                else:
                    yield StreamChunk(content="should not happen")

            return stream()

    def terminate() -> Any:
        return ToolResult(ok=True, data="finished", meta={"terminate": True})

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False)
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == []
    assert llm.calls == 1
    assert agent.history[-1].content == "finished"


@pytest.mark.asyncio
async def test_respond_stream_terminate_tool_result_drains_followup_queued_from_agent_end() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0
            self.messages: list[str] = []

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            latest = messages[-1].content
            self.messages.append(latest)

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "terminate", "arguments": "{}"},
                            }
                        ],
                    )
                else:
                    yield StreamChunk(content=f"reply:{latest}")

            return stream()

    agent_ref: dict[str, Agent] = {}
    queued = {"done": False}

    def on_event(event: Any) -> Any:
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-from-stream-end")

    def terminate() -> Any:
        return ToolResult(ok=True, data="finished", meta={"terminate": True})

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False, event_callback=on_event)
    agent_ref["agent"] = agent
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["reply:follow-from-stream-end"]
    assert llm.calls == 2
    assert llm.messages == ["start", "follow-from-stream-end"]


@pytest.mark.asyncio
async def test_respond_stream_terminate_ignores_stale_tool_outputs() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield StreamChunk(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-new",
                            "type": "function",
                            "function": {"name": "terminate", "arguments": "{}"},
                        }
                    ],
                )

            return stream()

    def terminate() -> Any:
        return ToolResult(ok=True, data="fresh-result", meta={"terminate": True})

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.history.append(
        cast(
            Any,
            SimpleNamespace(
                role="tool",
                content="stale-result",
                metadata={"tool_call_id": "call-old", "name": "read_file"},
            ),
        )
    )
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    async for _ in agent.respond_stream("start"):
        pass

    assert agent.history[-1].content == "fresh-result"
    assert "stale-result" not in agent.history[-1].content


def test_single_terminate_in_batch_stops_agent_any_semantics() -> None:
    """ANY semantics: one tool with terminate=True in a batch stops the agent.

    Previously the agent used AND semantics (all tools must terminate). This
    regression test ensures a mixed batch — one tool terminates, one doesn't —
    still stops the loop without a follow-up LLM call.
    """
    call_count = [0]

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def chat(self, messages: Any, tools: Any = None) -> Any:
            call_count[0] += 1
            return SimpleNamespace(
                content="",
                tool_calls=[
                    {"id": "c1", "function": {"name": "terminator", "arguments": "{}"}},
                    {"id": "c2", "function": {"name": "non_terminator", "arguments": "{}"}},
                ],
            )

    def terminator() -> Any:
        return ToolResult(ok=True, data="done", meta={"terminate": True})

    def non_terminator() -> Any:
        return ToolResult(ok=True, data="still going")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "terminator", terminator, {"type": "function", "function": {"name": "terminator"}}
    )
    agent.registry.register(
        "non_terminator",
        non_terminator,
        {"type": "function", "function": {"name": "non_terminator"}},
    )

    agent.run("go")

    # ANY semantics: loop stops after the first batch even though non_terminator
    # did not set terminate=True.
    assert call_count[0] == 1, "Agent should stop after one LLM call (ANY terminate semantics)"


@pytest.mark.asyncio
async def test_respond_stream_before_tool_call_abort_skips_sibling_tools() -> None:
    executed: list[str] = []

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "first", "arguments": "{}"},
                            },
                            {
                                "id": "call-2",
                                "type": "function",
                                "function": {"name": "second", "arguments": "{}"},
                            },
                        ],
                    )
                else:
                    yield StreamChunk(content="done")

            return stream()

    def first() -> Any:
        executed.append("first")
        return "first"

    def second() -> Any:
        executed.append("second")
        return "second"

    def before_tool_call(name: Any, args: Any) -> Any:
        if name == "first":
            return ToolResult(ok=False, error="blocked", meta={"abort_batch": True})
        return None

    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        before_tool_call=before_tool_call,
        verbose=False,
    )
    agent.registry.register("first", first, {"type": "function", "function": {"name": "first"}})
    agent.registry.register("second", second, {"type": "function", "function": {"name": "second"}})

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["done"]
    assert executed == []
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert len(tool_messages) == 1
    assert "blocked" in tool_messages[0].content


@pytest.mark.asyncio
async def test_respond_stream_after_tool_call_exception_becomes_error_tool_result() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "ok_tool", "arguments": "{}"},
                            }
                        ],
                    )
                else:
                    yield StreamChunk(content="done")

            return stream()

    def ok_tool() -> Any:
        return "ok"

    def after_tool_call(name: Any, args: Any, result: Any) -> Any:
        raise RuntimeError("after failed")

    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        after_tool_call=after_tool_call,
        verbose=False,
    )
    agent.registry.register(
        "ok_tool", ok_tool, {"type": "function", "function": {"name": "ok_tool"}}
    )

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["done"]
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert "after failed" in tool_messages[0].content


@pytest.mark.asyncio
async def test_respond_stream_awaits_async_tool_handlers_from_registry() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "async_tool", "arguments": "{}"},
                            }
                        ],
                    )
                else:
                    yield StreamChunk(content="done")

            return stream()

    async def async_tool(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        await asyncio.sleep(0)
        return ToolResult(ok=True, data="async-ok")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "async_tool",
        async_tool,
        {"type": "function", "function": {"name": "async_tool"}},
        validate=False,
    )

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["done"]
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert tool_messages[0].content == "async-ok"


@pytest.mark.asyncio
async def test_respond_stream_executes_parallel_safe_async_tools_concurrently() -> None:
    started: list[str] = []

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1

            async def stream() -> Any:
                if self.calls == 1:
                    yield StreamChunk(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "think", "arguments": "{}"},
                            },
                            {
                                "id": "call-2",
                                "type": "function",
                                "function": {"name": "get_current_time", "arguments": "{}"},
                            },
                        ],
                    )
                else:
                    yield StreamChunk(content="done")

            return stream()

    async def think(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        started.append("think")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"think-parallel:{'get_current_time' in started}")

    async def get_current_time(args: Any, user_id: Any, meta: Any, cancel: Any = None) -> Any:
        started.append("get_current_time")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"time-parallel:{'think' in started}")

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "think",
        think,
        {"type": "function", "function": {"name": "think"}},
        validate=False,
    )
    agent.registry.register(
        "get_current_time",
        get_current_time,
        {"type": "function", "function": {"name": "get_current_time"}},
        validate=False,
    )

    chunks = []
    async for chunk in agent.respond_stream("start"):
        chunks.append(chunk)

    assert chunks == ["done"]
    tool_messages = [message for message in agent.history if message.role == "tool"]
    assert tool_messages[0].content == "think-parallel:True"
    assert tool_messages[1].content == "time-parallel:True"


def _StreamChunk(*, content: str = "", tool_calls: Any = None) -> StreamChunk:
    """Build a StreamChunk fake (text and/or assembled tool calls)."""
    return StreamChunk(content=content, tool_calls=tool_calls)


def _ToolDelta(index: int, *, call_id: Any = None, name: Any = None, arguments: Any = "{}") -> dict:
    """Build a canonical tool-call dict (the shape providers assemble)."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


@pytest.mark.asyncio
async def test_master_loop_unbounded_runs_past_default_cap() -> None:
    """max_iterations<=0 loops until natural completion, never emitting the cap message."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            calls = self.calls

            async def stream() -> Any:
                # 25 tool-calling rounds (well past the default 10) then a final answer.
                if calls <= 25:
                    yield _StreamChunk(
                        tool_calls=[_ToolDelta(0, call_id=f"c{calls}", name="noop", arguments="{}")]
                    )
                else:
                    yield _StreamChunk(content="done")

            return stream()

    def noop() -> Any:
        return "ok"

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False, max_rounds=0)  # 0 = unbounded
    assert agent.max_iterations == 0
    agent.registry.register("noop", noop, {"type": "function", "function": {"name": "noop"}})

    chunks = []
    async for chunk in agent.respond_stream("go"):
        chunks.append(chunk)

    assert "".join(chunks) == "done"
    assert "Maximum iterations reached without completion." not in chunks
    assert llm.calls == 26


@pytest.mark.asyncio
async def test_master_loop_default_cap_still_enforced() -> None:
    """A model that never stops still hits the default 10-round cap when bounded."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield _StreamChunk(
                    tool_calls=[_ToolDelta(0, call_id="c", name="noop", arguments="{}")]
                )

            return stream()

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)  # default cap = 10
    agent.registry.register(
        "noop", lambda: "ok", {"type": "function", "function": {"name": "noop"}}
    )

    chunks = []
    async for chunk in agent.respond_stream("go"):
        chunks.append(chunk)

    assert chunks == ["Maximum iterations reached without completion."]


@pytest.mark.asyncio
async def test_master_loop_cancel_before_round_aborts_cleanly() -> None:
    """A cancel set before a round yields nothing and emits an 'aborted' agent_end."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield _StreamChunk(content="should not be reached")

            return stream()

    events = []
    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        verbose=False,
        event_callback=lambda e: events.append(e) if e.type.value == "agent_end" else None,
    )
    cancel = asyncio.Event()
    cancel.set()

    chunks = []
    async for chunk in agent.respond_stream("go", cancel=cancel):
        chunks.append(chunk)

    assert chunks == []  # no fake "Request was cancelled." message
    assert len(events) == 1
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "aborted"


@pytest.mark.asyncio
async def test_master_loop_cancel_mid_stream_preserves_partial() -> None:
    """Cancel during the LLM stream preserves partial text and aborts before tools."""

    cancel = asyncio.Event()

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield _StreamChunk(content="partial answer ")
                cancel.set()  # user hits Esc mid-stream
                yield _StreamChunk(content="this should be dropped")

            return stream()

    events = []
    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        verbose=False,
        event_callback=lambda e: events.append(e) if e.type.value == "agent_end" else None,
    )

    chunks = []
    async for chunk in agent.respond_stream("go", cancel=cancel):
        chunks.append(chunk)

    assert chunks == ["partial answer "]
    assert agent.history[-1].role == "assistant"
    assert agent.history[-1].content == "partial answer "
    assert events[0].data["error"] == "aborted"


@pytest.mark.asyncio
async def test_master_loop_injects_steering_between_rounds() -> None:
    """Steering queued during a streaming turn is injected before the next LLM call."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0
            self.seen_messages: list[list[str]] = []

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            self.seen_messages.append([m.content for m in messages])
            calls = self.calls

            async def stream() -> Any:
                if calls == 1:
                    yield _StreamChunk(
                        tool_calls=[_ToolDelta(0, call_id="c1", name="noop", arguments="{}")]
                    )
                else:
                    yield _StreamChunk(content="done")

            return stream()

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False)

    def noop() -> Any:
        # Simulate the user typing while the tool ran: queue a steering message.
        agent.message_queue.add_steering("actually do X instead")
        return "ok"

    agent.registry.register("noop", noop, {"type": "function", "function": {"name": "noop"}})

    chunks = []
    async for chunk in agent.respond_stream("go"):
        chunks.append(chunk)

    assert "".join(chunks) == "done"
    # The second LLM call must have seen the injected steering message.
    assert any("actually do X instead" in m for m in llm.seen_messages[1])


@pytest.mark.asyncio
async def test_master_loop_streams_tokens_then_executes_tool_call() -> None:
    """respond_stream yields text tokens live, runs a streamed tool call, continues."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            calls = self.calls

            async def stream() -> Any:
                if calls == 1:
                    # text streamed live, then a chunk carrying the assembled tool call
                    yield _StreamChunk(content="let me ")
                    yield _StreamChunk(content="check ")
                    yield _StreamChunk(
                        tool_calls=[_ToolDelta(0, call_id="c1", name="look", arguments="{}")]
                    )
                else:
                    yield _StreamChunk(content="the answer ")
                    yield _StreamChunk(content="is 42")

            return stream()

    seen_args = []

    def look() -> Any:
        seen_args.append("look")
        return "found"

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False)
    agent.registry.register("look", look, {"type": "function", "function": {"name": "look"}})

    chunks = []
    async for chunk in agent.respond_stream("go"):
        chunks.append(chunk)

    assert llm.calls == 2
    assert seen_args == ["look"]  # the streamed tool call executed
    # Tokens from both rounds streamed live, in order.
    assert "".join(chunks) == "let me check the answer is 42"
    # The tool result is in history.
    tool_messages = [m for m in agent.history if m.role == "tool"]
    assert tool_messages[0].content == "found"


@pytest.mark.asyncio
async def test_arun_cancel_mid_stream_aborts_and_preserves_partial() -> None:
    """arun(cancel) stops mid-stream, records partial text, and emits 'aborted'."""
    cancel = asyncio.Event()

    class FakeChunk:
        def __init__(self, *, content: Any = "", tool_calls: Any = None) -> None:
            self.content = content
            self.tool_calls = tool_calls
            self.usage: dict[str, Any] = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        async def achat_stream(self, messages: Any, **kwargs: Any) -> Any:
            yield FakeChunk(content="partial ")
            cancel.set()
            yield FakeChunk(content="dropped")

    events = []
    agent = Agent(
        llm=FakeLLM(),
        tools=[],
        verbose=False,
        event_callback=lambda e: events.append(e) if e.type.value == "agent_end" else None,
    )

    response = await agent.arun("go", cancel=cancel)

    assert response.content == "partial "
    assert agent.history[-1].role == "assistant"
    assert agent.history[-1].content == "partial "
    assert events[0].data["error"] == "aborted"


@pytest.mark.asyncio
async def test_master_loop_steering_during_final_answer_is_consumed() -> None:
    """Steering queued while the agent gives a no-tool answer drives another round."""

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self) -> None:
            self.calls = 0
            self.seen: list[list[str]] = []

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.calls += 1
            self.seen.append([m.content for m in messages])
            calls = self.calls

            async def stream() -> Any:
                yield _StreamChunk(content=f"answer-{calls}")

            return stream()

    llm = FakeLLM()
    agent = Agent(llm=llm, tools=[], verbose=False)
    # Queue a steering message before the run; the first (no-tool) round should
    # consume it and loop again instead of returning.
    agent.message_queue.add_steering("actually do X")

    chunks = []
    async for chunk in agent.respond_stream("go"):
        chunks.append(chunk)

    assert llm.calls == 2  # looped for the steering instead of ending after round 1
    assert any("actually do X" in m for m in llm.seen[1])
    assert "".join(chunks) == "answer-1answer-2"


@pytest.mark.asyncio
async def test_master_loop_records_billing_for_llm_and_tool_calls() -> None:
    """The streaming path reports LLM rounds + tool calls to the billing hook."""

    class Hook:
        def __init__(self) -> None:
            self.llm: list[tuple[Any, Any, Any]] = []
            self.tools: list[Any] = []

        def on_llm_call(self, model: Any, input_tokens: Any, output_tokens: Any) -> Any:
            self.llm.append((model, input_tokens, output_tokens))

        def on_tool_call(self, tool_name: Any) -> Any:
            self.tools.append(tool_name)

    class FakeLLM:
        config = SimpleNamespace(model="gpt-4o-mini")

        def __init__(self) -> None:
            self.n = 0

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            self.n += 1
            n = self.n

            async def stream() -> Any:
                if n == 1:
                    yield _StreamChunk(content="checking")
                    yield _StreamChunk(
                        tool_calls=[_ToolDelta(0, call_id="c1", name="shell", arguments="{}")]
                    )
                else:
                    yield _StreamChunk(content="done with a longer answer")

            return stream()

    hook = Hook()
    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, billing_hook=hook)
    agent.registry.register(
        "shell", lambda: "ran", {"type": "function", "function": {"name": "shell"}}
    )

    async for _ in agent.respond_stream("go"):
        pass

    assert len(hook.llm) == 2  # two LLM rounds recorded
    assert hook.tools == ["shell"]  # the tool call recorded
    assert all(inp > 0 for _, inp, _ in hook.llm)  # token estimates are non-zero


@pytest.mark.asyncio
async def test_master_loop_uses_real_provider_usage_when_present() -> None:
    """Billing uses real provider usage from the stream, not the local estimate."""

    class Hook:
        def __init__(self) -> None:
            self.llm: list[tuple[Any, Any]] = []

        def on_llm_call(self, model: Any, input_tokens: Any, output_tokens: Any) -> Any:
            self.llm.append((input_tokens, output_tokens))

        def on_tool_call(self, tool_name: Any) -> Any:
            pass

    class FakeLLM:
        config = SimpleNamespace(model="gpt-4o-mini")

        def achat_stream(self, messages: Any, tools: Any = None) -> Any:
            async def stream() -> Any:
                yield _StreamChunk(content="hi")
                yield StreamChunk(
                    content="",
                    usage={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
                )

            return stream()

    hook = Hook()
    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, billing_hook=hook)
    async for _ in agent.respond_stream("go"):
        pass

    assert hook.llm == [(200, 30)]
