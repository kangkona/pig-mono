"""Tests for enhanced tool registry features."""

import asyncio
from unittest.mock import Mock

import pytest
from pig_agent_core.tools.base import ToolResult
from pig_agent_core.tools.registry import RegistrationError, ToolRegistry


class TestRegistrationValidation:
    """Test tool registration validation."""

    def test_register_with_validation_success(self):
        """Test successful registration with validation."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="test")

        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "Test", "parameters": {}},
        }

        # Should not raise
        registry.register("test_tool", handler, schema, validate=True)
        assert "test_tool" in registry

    def test_register_non_callable_handler(self):
        """Test registration fails with non-callable handler."""
        registry = ToolRegistry()
        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "Test", "parameters": {}},
        }

        with pytest.raises(RegistrationError, match="must be callable"):
            registry.register("test_tool", "not_callable", schema, validate=True)

    def test_register_invalid_schema_structure(self):
        """Test registration fails with invalid schema."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        with pytest.raises(RegistrationError, match="must be a dict"):
            registry.register("test_tool", handler, "not_a_dict", validate=True)

    def test_register_missing_function_key(self):
        """Test registration fails when schema missing 'function' key."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {"type": "function"}

        with pytest.raises(RegistrationError, match="missing 'function' key"):
            registry.register("test_tool", handler, schema, validate=True)

    def test_register_missing_name_in_function(self):
        """Test registration fails when function schema missing 'name'."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {"type": "function", "function": {"description": "Test"}}

        with pytest.raises(RegistrationError, match="missing 'function.name'"):
            registry.register("test_tool", handler, schema, validate=True)

    def test_register_name_mismatch(self):
        """Test registration fails when schema name doesn't match tool name."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {
            "type": "function",
            "function": {"name": "wrong_name", "description": "Test", "parameters": {}},
        }

        with pytest.raises(RegistrationError, match="does not match tool name"):
            registry.register("test_tool", handler, schema, validate=True)

    def test_register_negative_timeout(self):
        """Test registration fails with negative timeout."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "Test", "parameters": {}},
        }

        with pytest.raises(RegistrationError, match="must be positive"):
            registry.register("test_tool", handler, schema, timeout=-1, validate=True)

    def test_register_negative_retries(self):
        """Test registration fails with negative retries."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "Test", "parameters": {}},
        }

        with pytest.raises(RegistrationError, match="must be non-negative"):
            registry.register("test_tool", handler, schema, max_retries=-1, validate=True)

    def test_register_without_validation(self):
        """Test registration without validation allows invalid data."""
        registry = ToolRegistry()

        # This would fail validation but should succeed without it
        registry.register("test_tool", "not_callable", {"invalid": "schema"}, validate=False)
        assert "test_tool" in registry


class TestFallbackMapping:
    """Test tool fallback functionality."""

    @pytest.mark.asyncio
    async def test_set_and_get_fallback_tools(self):
        """Test setting and getting fallback tools."""
        registry = ToolRegistry()
        registry.set_fallback_tools("primary_tool", ["fallback1", "fallback2"])

        fallbacks = registry.get_fallback_tools("primary_tool")
        assert fallbacks == ["fallback1", "fallback2"]

    @pytest.mark.asyncio
    async def test_get_fallback_tools_empty(self):
        """Test getting fallback tools when none configured."""
        registry = ToolRegistry()
        fallbacks = registry.get_fallback_tools("nonexistent_tool")
        assert fallbacks == []

    @pytest.mark.asyncio
    async def test_set_empty_fallback_removes_entry(self):
        """Test setting empty fallback list removes the entry."""
        registry = ToolRegistry()
        registry.set_fallback_tools("tool", ["fallback1"])
        registry.set_fallback_tools("tool", [])

        fallbacks = registry.get_fallback_tools("tool")
        assert fallbacks == []

    @pytest.mark.asyncio
    async def test_register_with_fallback_tools(self):
        """Test registering tool with fallback tools."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True)

        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "Test", "parameters": {}},
        }

        registry.register(
            "test_tool", handler, schema, fallback_tools=["fallback1", "fallback2"], validate=False
        )

        fallbacks = registry.get_fallback_tools("test_tool")
        assert fallbacks == ["fallback1", "fallback2"]

    @pytest.mark.asyncio
    async def test_execute_with_fallback_on_failure(self):
        """Test execution falls back to alternative tool on failure."""
        registry = ToolRegistry()

        # Primary tool that fails
        async def primary_handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=False, error="Primary failed")

        # Fallback tool that succeeds
        async def fallback_handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="Fallback succeeded")

        primary_schema = {
            "type": "function",
            "function": {"name": "primary_tool", "description": "Primary", "parameters": {}},
        }
        fallback_schema = {
            "type": "function",
            "function": {"name": "fallback_tool", "description": "Fallback", "parameters": {}},
        }

        registry.register(
            "primary_tool",
            primary_handler,
            primary_schema,
            fallback_tools=["fallback_tool"],
            validate=False,
        )
        registry.register("fallback_tool", fallback_handler, fallback_schema, validate=False)

        # Create mock tool call
        tool_call = Mock()
        tool_call.function.name = "primary_tool"
        tool_call.function.arguments = "{}"

        result = await registry.execute(tool_call, "user123", {})

        assert result.ok is True
        assert result.data == "Fallback succeeded"
        assert result.meta.get("fallback_from") == "primary_tool"
        assert result.meta.get("fallback_to") == "fallback_tool"

    @pytest.mark.asyncio
    async def test_execute_no_fallback_when_primary_succeeds(self):
        """Test fallback not used when primary tool succeeds."""
        registry = ToolRegistry()

        async def primary_handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="Primary succeeded")

        async def fallback_handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="Fallback succeeded")

        primary_schema = {
            "type": "function",
            "function": {"name": "primary_tool", "description": "Primary", "parameters": {}},
        }
        fallback_schema = {
            "type": "function",
            "function": {"name": "fallback_tool", "description": "Fallback", "parameters": {}},
        }

        registry.register(
            "primary_tool",
            primary_handler,
            primary_schema,
            fallback_tools=["fallback_tool"],
            validate=False,
        )
        registry.register("fallback_tool", fallback_handler, fallback_schema, validate=False)

        tool_call = Mock()
        tool_call.function.name = "primary_tool"
        tool_call.function.arguments = "{}"

        result = await registry.execute(tool_call, "user123", {})

        assert result.ok is True
        assert result.data == "Primary succeeded"
        assert "fallback_from" not in result.meta


class TestConfirmationGate:
    """Test write-tool confirmation gate."""

    def test_confirm_tool(self):
        """Test confirming a tool."""
        registry = ToolRegistry()
        registry.confirm_tool("write_tool")

        assert registry.is_tool_confirmed("write_tool")

    def test_requires_confirmation_for_write_tool(self):
        """Test write tools require confirmation."""
        registry = ToolRegistry()

        # Mock TOOL_PERMISSIONS to include a write tool
        from pig_agent_core.tools import schemas

        original_perms = schemas.TOOL_PERMISSIONS.copy()
        schemas.TOOL_PERMISSIONS["write_tool"] = "write"

        try:
            assert registry.requires_confirmation("write_tool") is True
        finally:
            schemas.TOOL_PERMISSIONS.clear()
            schemas.TOOL_PERMISSIONS.update(original_perms)

    def test_no_confirmation_for_read_tool(self):
        """Test read tools don't require confirmation."""
        registry = ToolRegistry()

        from pig_agent_core.tools import schemas

        original_perms = schemas.TOOL_PERMISSIONS.copy()
        schemas.TOOL_PERMISSIONS["read_tool"] = "read"

        try:
            assert registry.requires_confirmation("read_tool") is False
            assert registry.is_tool_confirmed("read_tool") is True
        finally:
            schemas.TOOL_PERMISSIONS.clear()
            schemas.TOOL_PERMISSIONS.update(original_perms)

    @pytest.mark.asyncio
    async def test_execute_blocks_unconfirmed_write_tool(self):
        """Test execution blocks unconfirmed write tools."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="Should not execute")

        schema = {
            "type": "function",
            "function": {"name": "write_tool", "description": "Write", "parameters": {}},
        }

        registry.register("write_tool", handler, schema, validate=False)

        from pig_agent_core.tools import schemas

        original_perms = schemas.TOOL_PERMISSIONS.copy()
        schemas.TOOL_PERMISSIONS["write_tool"] = "write"

        try:
            tool_call = Mock()
            tool_call.function.name = "write_tool"
            tool_call.function.arguments = "{}"

            result = await registry.execute(tool_call, "user123", {})

            assert result.ok is False
            assert "requires confirmation" in result.error
            assert result.meta.get("requires_confirmation") is True
        finally:
            schemas.TOOL_PERMISSIONS.clear()
            schemas.TOOL_PERMISSIONS.update(original_perms)

    @pytest.mark.asyncio
    async def test_execute_allows_confirmed_write_tool(self):
        """Test execution allows confirmed write tools."""
        registry = ToolRegistry()

        async def handler(args, user_id, meta, cancel=None):
            return ToolResult(ok=True, data="Executed")

        schema = {
            "type": "function",
            "function": {"name": "write_tool", "description": "Write", "parameters": {}},
        }

        registry.register("write_tool", handler, schema, validate=False)
        registry.confirm_tool("write_tool")

        from pig_agent_core.tools import schemas

        original_perms = schemas.TOOL_PERMISSIONS.copy()
        schemas.TOOL_PERMISSIONS["write_tool"] = "write"

        try:
            tool_call = Mock()
            tool_call.function.name = "write_tool"
            tool_call.function.arguments = "{}"

            result = await registry.execute(tool_call, "user123", {})

            assert result.ok is True
            assert result.data == "Executed"
        finally:
            schemas.TOOL_PERMISSIONS.clear()
            schemas.TOOL_PERMISSIONS.update(original_perms)


class TestParallelExecution:
    """Test parallel/sequential execution strategies."""

    def test_is_parallel_safe(self):
        """Test checking if tool is parallel-safe."""
        registry = ToolRegistry()

        # think is in PARALLEL_SAFE_TOOLS
        assert registry.is_parallel_safe("think") is True

        # write_file is not in PARALLEL_SAFE_TOOLS
        assert registry.is_parallel_safe("write_file") is False

    @pytest.mark.asyncio
    async def test_execute_batch_parallel_tools(self):
        """Test batch execution runs parallel-safe tools concurrently."""
        registry = ToolRegistry()

        execution_order = []

        async def handler1(args, user_id, meta, cancel=None):
            execution_order.append("tool1_start")
            await asyncio.sleep(0.1)
            execution_order.append("tool1_end")
            return ToolResult(ok=True, data="tool1")

        async def handler2(args, user_id, meta, cancel=None):
            execution_order.append("tool2_start")
            await asyncio.sleep(0.1)
            execution_order.append("tool2_end")
            return ToolResult(ok=True, data="tool2")

        schema1 = {
            "type": "function",
            "function": {"name": "think", "description": "Think", "parameters": {}},
        }
        schema2 = {
            "type": "function",
            "function": {"name": "get_current_time", "description": "Time", "parameters": {}},
        }

        registry.register("think", handler1, schema1, validate=False)
        registry.register("get_current_time", handler2, schema2, validate=False)

        tool_call1 = Mock()
        tool_call1.function.name = "think"
        tool_call1.function.arguments = "{}"

        tool_call2 = Mock()
        tool_call2.function.name = "get_current_time"
        tool_call2.function.arguments = "{}"

        results = await registry.execute_batch([tool_call1, tool_call2], "user123", {})

        assert len(results) == 2
        assert results[0].ok is True
        assert results[1].ok is True

        # Both should start before either ends (parallel execution)
        tool1_start_idx = execution_order.index("tool1_start")
        tool2_start_idx = execution_order.index("tool2_start")
        tool1_end_idx = execution_order.index("tool1_end")

        assert tool2_start_idx < tool1_end_idx

    @pytest.mark.asyncio
    async def test_execute_batch_sequential_tools(self):
        """Test batch execution runs write tools sequentially."""
        registry = ToolRegistry()

        execution_order = []

        async def handler1(args, user_id, meta, cancel=None):
            execution_order.append("write1_start")
            await asyncio.sleep(0.05)
            execution_order.append("write1_end")
            return ToolResult(ok=True, data="write1")

        async def handler2(args, user_id, meta, cancel=None):
            execution_order.append("write2_start")
            await asyncio.sleep(0.05)
            execution_order.append("write2_end")
            return ToolResult(ok=True, data="write2")

        schema1 = {
            "type": "function",
            "function": {"name": "write_file", "description": "Write", "parameters": {}},
        }
        schema2 = {
            "type": "function",
            "function": {"name": "post_x", "description": "Post", "parameters": {}},
        }

        registry.register("write_file", handler1, schema1, validate=False)
        registry.register("post_x", handler2, schema2, validate=False)

        tool_call1 = Mock()
        tool_call1.function.name = "write_file"
        tool_call1.function.arguments = "{}"

        tool_call2 = Mock()
        tool_call2.function.name = "post_x"
        tool_call2.function.arguments = "{}"

        results = await registry.execute_batch([tool_call1, tool_call2], "user123", {})

        assert len(results) == 2
        assert results[0].ok is True
        assert results[1].ok is True

        # First tool should complete before second starts (sequential)
        assert execution_order == [
            "write1_start",
            "write1_end",
            "write2_start",
            "write2_end",
        ]

    @pytest.mark.asyncio
    async def test_execute_batch_mixed_tools(self):
        """Test batch execution with mix of parallel and sequential tools."""
        registry = ToolRegistry()

        async def read_handler(args, user_id, meta, cancel=None):
            await asyncio.sleep(0.05)
            return ToolResult(ok=True, data="read")

        async def write_handler(args, user_id, meta, cancel=None):
            await asyncio.sleep(0.05)
            return ToolResult(ok=True, data="write")

        read_schema = {
            "type": "function",
            "function": {"name": "think", "description": "Think", "parameters": {}},
        }
        write_schema = {
            "type": "function",
            "function": {"name": "write_file", "description": "Write", "parameters": {}},
        }

        registry.register("think", read_handler, read_schema, validate=False)
        registry.register("write_file", write_handler, write_schema, validate=False)

        tool_call1 = Mock()
        tool_call1.function.name = "think"
        tool_call1.function.arguments = "{}"

        tool_call2 = Mock()
        tool_call2.function.name = "write_file"
        tool_call2.function.arguments = "{}"

        results = await registry.execute_batch([tool_call1, tool_call2], "user123", {})

        assert len(results) == 2
        assert all(r.ok for r in results)

    @pytest.mark.asyncio
    async def test_execute_batch_empty_list(self):
        """Test batch execution with empty list."""
        registry = ToolRegistry()
        results = await registry.execute_batch([], "user123", {})
        assert results == []


class TestUnregisterEnhanced:
    """Test unregister cleans up all enhanced features."""

    def test_unregister_removes_fallbacks(self):
        """Test unregister removes fallback mappings."""
        registry = ToolRegistry()
        registry.set_fallback_tools("tool", ["fallback1"])
        registry.unregister("tool")

        fallbacks = registry.get_fallback_tools("tool")
        assert fallbacks == []

    def test_unregister_removes_confirmation(self):
        """Test unregister removes confirmation status."""
        registry = ToolRegistry()
        registry.confirm_tool("tool")
        registry.unregister("tool")

        # After unregister, tool should not be in confirmed set
        # (though requires_confirmation will return False for unknown tools)
        assert "tool" not in registry._confirmed_tools
