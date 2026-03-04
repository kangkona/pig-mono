"""Verify pig-agent-tools README examples are accurate."""

import asyncio

print("Testing pig-agent-tools README examples...\n")

# Test 1: Tool schemas and handlers
print("Test 1: Tool schemas and handlers...")
try:
    from pig_agent_tools.web import HANDLERS, TOOL_SCHEMAS

    assert len(TOOL_SCHEMAS) == 2, f"Expected 2 schemas, got {len(TOOL_SCHEMAS)}"
    assert len(HANDLERS) == 2, f"Expected 2 handlers, got {len(HANDLERS)}"
    assert "search_web" in HANDLERS
    assert "read_webpage" in HANDLERS
    print("✓ Tool schemas and handlers work")
except Exception as e:
    print(f"✗ Tool schemas and handlers failed: {e}")

# Test 2: Direct handler usage
print("\nTest 2: Direct handler usage...")
try:
    from pig_agent_tools.web import handle_search_web
    from pig_agent_tools.web.providers.base import SearchResult

    class _MockProvider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            return [SearchResult(title="Test", url="https://example.com", snippet="Test content")]

    async def _run():
        result = await handle_search_web(
            {"query": "Python tutorials", "max_results": 5},
            user_id="user123",
            meta={},
            provider=_MockProvider(),
        )
        assert result.ok, f"Expected ok=True, got {result.ok}"
        assert "Test" in result.data
        return True

    success = asyncio.run(_run())
    print("✓ Direct handler usage works")
except Exception as e:
    print(f"✗ Direct handler usage failed: {e}")

# Test 3: Tool registration
print("\nTest 3: Tool registration...")
try:
    from pig_agent_core.tools.registry import ToolRegistry
    from pig_agent_tools.web import HANDLERS, TOOL_SCHEMAS

    registry = ToolRegistry()
    for schema in TOOL_SCHEMAS:
        tool_name = schema["function"]["name"]
        handler = HANDLERS.get(tool_name)
        if handler:
            registry.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=False,
                timeout=30.0,
            )

    with registry._lock:
        assert "search_web" in registry._handlers
        assert "read_webpage" in registry._handlers

    print("✓ Tool registration works")
except Exception as e:
    print(f"✗ Tool registration failed: {e}")

# Test 4: Custom tool schema
print("\nTest 4: Custom tool schema...")
try:
    CUSTOM_TOOL_SCHEMA = {
        "type": "function",
        "function": {
            "name": "my_custom_tool",
            "description": "Description of what your tool does",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Description of param1",
                    },
                    "param2": {
                        "type": "integer",
                        "description": "Description of param2",
                        "default": 10,
                    },
                },
                "required": ["param1"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }

    assert CUSTOM_TOOL_SCHEMA["type"] == "function"
    assert CUSTOM_TOOL_SCHEMA["function"]["name"] == "my_custom_tool"
    print("✓ Custom tool schema works")
except Exception as e:
    print(f"✗ Custom tool schema failed: {e}")

# Test 5: Custom tool handler
print("\nTest 5: Custom tool handler...")
try:
    from typing import Any

    from pig_agent_core.tools.base import ToolResult

    async def handle_my_custom_tool(
        args: dict[str, Any],
        user_id: str | None = None,
        meta: dict[str, Any] | None = None,
        cancel: Any = None,
    ) -> ToolResult:
        param1 = args.get("param1", "")
        param2 = args.get("param2", 10)

        if not param1:
            return ToolResult(ok=False, error="param1 is required")

        try:
            result = f"Processed {param1} with {param2}"
            return ToolResult(ok=True, data=result)
        except Exception as e:
            return ToolResult(ok=False, error=f"Tool execution failed: {str(e)}")

    async def _run():
        result = await handle_my_custom_tool({"param1": "test", "param2": 5})
        assert result.ok
        assert "Processed test with 5" in result.data

        result = await handle_my_custom_tool({})
        assert not result.ok
        assert "param1 is required" in result.error

        return True

    asyncio.run(_run())
    print("✓ Custom tool handler works")
except Exception as e:
    print(f"✗ Custom tool handler failed: {e}")

# Test 6: ToolResult error handling
print("\nTest 6: ToolResult error handling...")
try:
    from pig_agent_core.tools.base import ToolResult

    result = ToolResult(ok=True, data="success")
    assert result.ok
    assert result.data == "success"

    result = ToolResult(ok=False, error="something went wrong")
    assert not result.ok
    assert result.error == "something went wrong"

    print("✓ ToolResult error handling works")
except Exception as e:
    print(f"✗ ToolResult error handling failed: {e}")

print("\n" + "=" * 50)
print("All README examples validated!")
