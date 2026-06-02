"""Regression tests for behavior absorbed from recent pi-mono agent changes."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pig_agent_core.agent import Agent
from pig_agent_core.session import Session, SessionTree, serialize_compaction_tool_result
from pig_agent_core.tools import ToolResult


def test_session_tree_loads_large_jsonl_incrementally(tmp_path) -> None:
    path = tmp_path / "large.jsonl"
    entries = []
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


def test_session_load_streams_tree_lines_without_reading_full_tail(monkeypatch, tmp_path) -> None:
    session = Session(name="streamed", workspace=str(tmp_path), auto_save=False)
    session.add_message("user", "hello")
    save_path = session.save()

    class GuardedFile:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __enter__(self):
            self._wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self._wrapped.__exit__(*args)

        def readline(self, *args, **kwargs):
            return self._wrapped.readline(*args, **kwargs)

        def __iter__(self):
            return iter(self._wrapped)

        def read(self, *args, **kwargs):
            raise AssertionError("Session.load should not materialize the whole JSONL tail")

    real_open = open

    def guarded_open(*args, **kwargs):
        return GuardedFile(real_open(*args, **kwargs))

    monkeypatch.setattr("builtins.open", guarded_open)

    loaded = Session.load(save_path)

    assert loaded.name == "streamed"
    assert len(loaded.tree.entries) == 1


def test_session_save_keeps_header_small_and_excludes_duplicate_tree_payload(tmp_path) -> None:
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
    monkeypatch, tmp_path
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
    assert [entry.id for entry in current[1:]] == [entry.id for entry in tail_before]
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


def test_agent_before_tool_call_abort_skips_sibling_tools() -> None:
    executed: list[str] = []

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None):
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

    def first():
        executed.append("first")
        return "first"

    def second():
        executed.append("second")
        return "second"

    def before_tool_call(name, args):
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

        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None):
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

    def ok_tool():
        return "ok"

    def after_tool_call(name, args, result):
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
        def __init__(self, *, content: str = "", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
            self.usage = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        async def astream(self, messages, **kwargs):
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

    def first():
        executed.append("first")
        return "first"

    def second():
        executed.append("second")
        return "second"

    def before_tool_call(name, args):
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
        def __init__(self, *, content: str = "", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
            self.usage = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        async def astream(self, messages, **kwargs):
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

    def ok_tool():
        return "ok"

    def after_tool_call(name, args, result):
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
        def __init__(self, *, content: str = "", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
            self.usage = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        async def astream(self, messages, **kwargs):
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

    async def async_tool(args, user_id, meta, cancel=None):
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
        def __init__(self, *, content: str = "", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
            self.usage = {}

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        async def astream(self, messages, **kwargs):
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

    async def think(args, user_id, meta, cancel=None):
        started.append("think")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"think-parallel:{'get_current_time' in started}")

    async def get_current_time(args, user_id, meta, cancel=None):
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

        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None):
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

    def terminate():
        return ToolResult(ok=True, data="finished", meta={"terminate": True})

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.registry.register(
        "terminate",
        terminate,
        {"type": "function", "function": {"name": "terminate"}},
    )

    response = agent.run("go")

    assert response.content == "finished"
    assert agent.llm.calls == 1


def test_terminate_tool_result_still_emits_agent_end_and_drains_followup() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0
            self.messages: list[str] = []

        def chat(self, messages, tools=None):
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

    def on_event(event):
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-after-terminate")

    def terminate():
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
    assert agent.llm.calls == 2
    assert agent.llm.messages == ["go", "follow-after-terminate"]


def test_agent_followup_queue_processes_all_messages_in_fifo_order() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.messages: list[str] = []

        def chat(self, messages, tools=None):
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.message_queue.add_followup("follow-1")
    agent.message_queue.add_followup("follow-2")

    response = agent.run("start")

    assert response.content == "reply:follow-2"
    assert agent.llm.messages == ["start", "follow-1", "follow-2"]


def test_agent_followup_all_mode_processes_entire_batch() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.messages: list[str] = []

        def chat(self, messages, tools=None):
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False)
    agent.message_queue.followup_mode = "all"
    agent.message_queue.add_followup("follow-1")
    agent.message_queue.add_followup("follow-2")

    response = agent.run("start")

    assert response.content == "reply:follow-2"
    assert agent.llm.messages == ["start", "follow-1", "follow-2"]


def test_agent_end_callback_can_queue_followup_before_run_returns() -> None:
    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.messages: list[str] = []

        def chat(self, messages, tools=None):
            latest = messages[-1].content
            self.messages.append(latest)
            return SimpleNamespace(content=f"reply:{latest}", tool_calls=None)

    agent_ref: dict[str, Agent] = {}

    queued = {"done": False}

    def on_event(event):
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
    assert agent.llm.messages == ["start", "follow-from-end"]


def test_agent_llm_failure_emits_agent_end_failure_event() -> None:
    class FailingLLM:
        config = SimpleNamespace(model="fake")

        def chat(self, messages, tools=None):
            raise RuntimeError("boom")

    events = []

    def on_event(event):
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
    class FakeChunk:
        def __init__(self, content: str):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content, tool_calls=None),
                    finish_reason=None,
                )
            ]

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def achat_stream(self, messages, tools=None):
            async def stream():
                yield FakeChunk("hello")
                yield FakeChunk(" world")

            return stream()

    events = []

    def on_event(event):
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
    class FakeChunk:
        def __init__(self, content: str):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content, tool_calls=None),
                    finish_reason=None,
                )
            ]

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.messages: list[str] = []

        def achat_stream(self, messages, tools=None):
            latest = messages[-1].content
            self.messages.append(latest)

            async def stream():
                yield FakeChunk(f"reply:{latest}")

            return stream()

    agent_ref: dict[str, Agent] = {}
    queued = {"done": False}

    def on_event(event):
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

        def achat_stream(self, messages, tools=None):
            async def stream():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="ignored", tool_calls=None),
                            finish_reason=None,
                        )
                    ]
                )

            return stream()

    events = []

    def on_event(event):
        if event.type.value == "agent_end":
            events.append(event)

    agent = Agent(llm=FakeLLM(), tools=[], verbose=False, event_callback=on_event)
    cancel = asyncio.Event()
    cancel.set()

    chunks = []
    async for chunk in agent.respond_stream("start", cancel=cancel):
        chunks.append(chunk)

    assert chunks == ["Request was cancelled."]
    assert len(events) == 1
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "Request was cancelled."


@pytest.mark.asyncio
async def test_respond_stream_llm_failure_emits_agent_end_failure_event() -> None:
    class FailingLLM:
        config = SimpleNamespace(model="fake")

        async def achat_stream(self, messages, tools=None):
            raise RuntimeError("stream boom")

    events = []

    def on_event(event):
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
    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def achat_stream(self, messages, tools=None):
            self.calls += 1

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="terminate", arguments="{}")
                        ]
                    )
                else:
                    yield ToolCallChunk(content="should not happen")

            return stream()

    def terminate():
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
    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0
            self.messages: list[str] = []

        def achat_stream(self, messages, tools=None):
            self.calls += 1
            latest = messages[-1].content
            self.messages.append(latest)

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="terminate", arguments="{}")
                        ]
                    )
                else:
                    yield ToolCallChunk(content=f"reply:{latest}")

            return stream()

    agent_ref: dict[str, Agent] = {}
    queued = {"done": False}

    def on_event(event):
        if (
            event.type.value == "agent_end"
            and event.data.get("success") is True
            and not queued["done"]
        ):
            queued["done"] = True
            agent_ref["agent"].message_queue.add_followup("follow-from-stream-end")

    def terminate():
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
async def test_respond_stream_before_tool_call_abort_skips_sibling_tools() -> None:
    executed: list[str] = []

    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def achat_stream(self, messages, tools=None):
            self.calls += 1

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="first", arguments="{}"),
                            ToolCallDelta(1, call_id="call-2", name="second", arguments="{}"),
                        ]
                    )
                else:
                    yield ToolCallChunk(content="done")

            return stream()

    def first():
        executed.append("first")
        return "first"

    def second():
        executed.append("second")
        return "second"

    def before_tool_call(name, args):
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
    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def achat_stream(self, messages, tools=None):
            self.calls += 1

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="ok_tool", arguments="{}")
                        ]
                    )
                else:
                    yield ToolCallChunk(content="done")

            return stream()

    def ok_tool():
        return "ok"

    def after_tool_call(name, args, result):
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
    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def achat_stream(self, messages, tools=None):
            self.calls += 1

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="async_tool", arguments="{}")
                        ]
                    )
                else:
                    yield ToolCallChunk(content="done")

            return stream()

    async def async_tool(args, user_id, meta, cancel=None):
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

    class ToolCallChunk:
        def __init__(self, *, content: str = "", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                    finish_reason=None,
                )
            ]

    class ToolCallDelta:
        def __init__(self, index: int, *, call_id=None, name=None, arguments=None):
            self.index = index
            self.id = call_id
            self.function = SimpleNamespace(name=name, arguments=arguments)

    class FakeLLM:
        config = SimpleNamespace(model="fake")

        def __init__(self):
            self.calls = 0

        def achat_stream(self, messages, tools=None):
            self.calls += 1

            async def stream():
                if self.calls == 1:
                    yield ToolCallChunk(
                        tool_calls=[
                            ToolCallDelta(0, call_id="call-1", name="think", arguments="{}"),
                            ToolCallDelta(
                                1, call_id="call-2", name="get_current_time", arguments="{}"
                            ),
                        ]
                    )
                else:
                    yield ToolCallChunk(content="done")

            return stream()

    async def think(args, user_id, meta, cancel=None):
        started.append("think")
        await asyncio.sleep(0.01)
        return ToolResult(ok=True, data=f"think-parallel:{'get_current_time' in started}")

    async def get_current_time(args, user_id, meta, cancel=None):
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
