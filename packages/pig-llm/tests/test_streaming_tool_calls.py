"""Tests for streaming tool-call assembly (compat layer)."""

from types import SimpleNamespace

import pytest
from pig_llm.compat import _OpenAIToolCallAccumulator, astream_openai_tool_aware


def _delta_chunk(*, content=None, tool_calls=None, finish_reason=None):
    return SimpleNamespace(
        id="chunk-x",
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
            )
        ],
    )


def _tc_delta(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _AsyncStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


def test_accumulator_assembles_multi_chunk_tool_call():
    acc = _OpenAIToolCallAccumulator()
    # id+name arrive first, arguments stream in fragments
    acc.add(_delta_chunk(tool_calls=[_tc_delta(0, call_id="call_1", name="shell")]).choices[0])
    acc.add(_delta_chunk(tool_calls=[_tc_delta(0, arguments='{"cmd":')]).choices[0])
    acc.add(_delta_chunk(tool_calls=[_tc_delta(0, arguments='"ls"}')]).choices[0])

    result = acc.finish()
    assert result == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "shell", "arguments": '{"cmd":"ls"}'},
        }
    ]


def test_accumulator_handles_parallel_tool_calls_by_index():
    acc = _OpenAIToolCallAccumulator()
    acc.add(
        _delta_chunk(tool_calls=[_tc_delta(0, call_id="a", name="x", arguments="{}")]).choices[0]
    )
    acc.add(
        _delta_chunk(tool_calls=[_tc_delta(1, call_id="b", name="y", arguments="{}")]).choices[0]
    )

    result = acc.finish()
    assert [tc["id"] for tc in result] == ["a", "b"]
    assert [tc["function"]["name"] for tc in result] == ["x", "y"]


def test_accumulator_empty_returns_none():
    assert _OpenAIToolCallAccumulator().finish() is None


@pytest.mark.asyncio
async def test_astream_tool_aware_yields_text_then_tool_calls():
    stream = _AsyncStream(
        [
            _delta_chunk(content="thinking "),
            _delta_chunk(content="about it "),
            _delta_chunk(tool_calls=[_tc_delta(0, call_id="c1", name="shell", arguments="{}")]),
            _delta_chunk(finish_reason="tool_calls"),
        ]
    )

    chunks = [c async for c in astream_openai_tool_aware(stream)]

    text = [c for c in chunks if c.content]
    assert "".join(c.content for c in text) == "thinking about it "
    # Exactly one trailing chunk carries the assembled tool calls.
    tool_chunks = [c for c in chunks if c.tool_calls]
    assert len(tool_chunks) == 1
    assert tool_chunks[-1] is chunks[-1]
    assert tool_chunks[0].tool_calls == [
        {"id": "c1", "type": "function", "function": {"name": "shell", "arguments": "{}"}}
    ]


@pytest.mark.asyncio
async def test_astream_tool_aware_text_only_has_no_tool_calls():
    stream = _AsyncStream([_delta_chunk(content="hello"), _delta_chunk(content=" world")])

    chunks = [c async for c in astream_openai_tool_aware(stream)]

    assert "".join(c.content for c in chunks) == "hello world"
    assert all(c.tool_calls is None for c in chunks)


@pytest.mark.asyncio
async def test_astream_captures_trailing_usage_chunk():
    """A usage-only chunk after the terminal finish_reason is captured."""
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=45, total_tokens=165)
    stream = _AsyncStream(
        [
            _delta_chunk(content="hello "),
            _delta_chunk(content="world", finish_reason="stop"),
            SimpleNamespace(id="u", choices=[], usage=usage),
        ]
    )
    chunks = [c async for c in astream_openai_tool_aware(stream)]
    assert "".join(c.content for c in chunks if c.content) == "hello world"
    usages = [c.usage for c in chunks if c.usage]
    assert usages == [
        {"input_tokens": 120, "output_tokens": 45, "cached_tokens": 0, "total_tokens": 165}
    ]


@pytest.mark.asyncio
async def test_astream_captures_cached_prompt_tokens():
    """cached_tokens from prompt_tokens_details is carried in the usage chunk."""
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=20,
        total_tokens=1020,
        prompt_tokens_details=SimpleNamespace(cached_tokens=800),
    )
    stream = _AsyncStream(
        [
            _delta_chunk(content="hi", finish_reason="stop"),
            SimpleNamespace(id="u", choices=[], usage=usage),
        ]
    )
    chunks = [c async for c in astream_openai_tool_aware(stream)]
    u = [c.usage for c in chunks if c.usage][0]
    assert u["input_tokens"] == 1000
    assert u["cached_tokens"] == 800
