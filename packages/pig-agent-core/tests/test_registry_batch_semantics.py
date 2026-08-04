"""Regression tests for batch exception and cancellation semantics."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pig_agent_core.tools import ToolResult
from pig_agent_core.tools.registry import ToolRegistry


def _tool_call(name: str) -> Any:
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments="{}"))


def _schema(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": name, "parameters": {}},
    }


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


@pytest.mark.asyncio
async def test_preflight_failure_cannot_fall_back_to_an_unguarded_tool() -> None:
    """A policy decision is final and cannot be bypassed through fallbacks."""
    registry = ToolRegistry()
    calls: list[str] = []

    async def primary(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("primary")
        return ToolResult(ok=True)

    async def fallback(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("fallback")
        return ToolResult(ok=True)

    registry.register(
        "primary",
        primary,
        _schema("primary"),
        fallback_tools=["fallback"],
        preflight=lambda args: ToolResult(ok=False, error="denied"),
        validate=False,
    )
    registry.register("fallback", fallback, _schema("fallback"), validate=False)

    result = await registry.execute(_tool_call("primary"), "user", {})

    assert result == ToolResult(ok=False, error="denied")
    assert calls == []


@pytest.mark.asyncio
async def test_fallback_tool_cannot_bypass_its_own_preflight() -> None:
    """A failed primary must not jump directly into a protected fallback."""
    registry = ToolRegistry()
    calls: list[str] = []

    async def primary(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("primary")
        return ToolResult(ok=False, error="primary failed")

    async def fallback(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("fallback")
        return ToolResult(ok=True)

    registry.register(
        "primary",
        primary,
        _schema("primary"),
        fallback_tools=["fallback"],
        validate=False,
    )
    registry.register(
        "fallback",
        fallback,
        _schema("fallback"),
        preflight=lambda args: ToolResult(ok=False, error="fallback denied"),
        validate=False,
    )

    result = await registry.execute(_tool_call("primary"), "user", {})

    assert result == ToolResult(ok=False, error="fallback denied")
    assert calls == ["primary"]


@pytest.mark.asyncio
async def test_abort_batch_skips_later_sequential_tools() -> None:
    """A terminating policy result prevents later side effects in the batch."""
    registry = ToolRegistry()
    calls: list[str] = []

    async def first(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("first")
        return ToolResult(ok=False, error="denied", meta={"abort_batch": True})

    async def second(*args: Any, **kwargs: Any) -> ToolResult:
        calls.append("second")
        return ToolResult(ok=True)

    registry.register("first", first, _schema("first"), validate=False)
    registry.register("second", second, _schema("second"), validate=False)

    results = await registry.execute_batch([_tool_call("first"), _tool_call("second")], "user", {})

    assert calls == ["first"]
    assert results[0].error == "denied"
    assert results[1].error == "Skipped after an earlier tool stopped the batch"
