"""Regression tests for batch exception and cancellation semantics."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pig_agent_core.tools import ToolResult
from pig_agent_core.tools.registry import ToolRegistry


def _tool_call(name: str) -> Any:
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments="{}"))


@pytest.mark.asyncio
async def test_parallel_batch_propagates_asyncio_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation must retain task-cancellation semantics."""
    registry = ToolRegistry()

    async def cancelled_execute(*args: Any, **kwargs: Any) -> ToolResult:
        raise asyncio.CancelledError

    monkeypatch.setattr(registry, "execute", cancelled_execute)

    with pytest.raises(asyncio.CancelledError):
        await registry.execute_batch([_tool_call("read_file")], "user", {})


@pytest.mark.asyncio
async def test_parallel_batch_converts_regular_exception_to_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordinary failures remain structured per-tool results."""
    registry = ToolRegistry()

    async def failed_execute(*args: Any, **kwargs: Any) -> ToolResult:
        raise RuntimeError("handler failed")

    monkeypatch.setattr(registry, "execute", failed_execute)

    results = await registry.execute_batch([_tool_call("read_file")], "user", {})

    assert results == [ToolResult(ok=False, error="handler failed")]
