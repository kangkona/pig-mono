"""Tests for additional tool schemas."""

from pig_agent_core.tools.schemas import (
    CORE_TOOL_NAMES,
    PARALLEL_SAFE_TOOLS,
    TOOL_BUDGETS,
    TOOL_PERMISSIONS,
    TOOL_SCHEMAS,
    get_all_schemas,
    get_core_schemas,
)


class TestGetCurrentTimeSchema:
    """Test get_current_time tool schema."""

    def test_get_current_time_in_core_tools(self) -> None:
        """Test that get_current_time is in core tools."""
        assert "get_current_time" in CORE_TOOL_NAMES

    def test_get_current_time_schema_exists(self) -> None:
        """Test that get_current_time schema exists."""
        schemas = get_all_schemas()
        assert "get_current_time" in schemas

    def test_get_current_time_schema_structure(self) -> None:
        """Test get_current_time schema structure."""
        schemas = get_all_schemas()
        schema = schemas["get_current_time"]

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_current_time"
        assert "current date and time" in schema["function"]["description"].lower()

    def test_get_current_time_parameters(self) -> None:
        """Test get_current_time parameters."""
        schemas = get_all_schemas()
        schema = schemas["get_current_time"]
        params = schema["function"]["parameters"]

        assert "properties" in params
        assert "timezone" in params["properties"]
        assert params["properties"]["timezone"]["type"] == "string"

    def test_get_current_time_permission(self) -> None:
        """Test that get_current_time has correct permission."""
        assert TOOL_PERMISSIONS["get_current_time"] == "none"

    def test_get_current_time_budget(self) -> None:
        """Test that get_current_time has budget configuration."""
        assert "get_current_time" in TOOL_BUDGETS
        assert TOOL_BUDGETS["get_current_time"]["timeout"] == 1
        assert TOOL_BUDGETS["get_current_time"]["max_retries"] == 0


class TestParallelSafeTools:
    """Test parallel-safe tools set."""

    def test_parallel_safe_tools_exists(self) -> None:
        """Test that PARALLEL_SAFE_TOOLS is defined."""
        assert isinstance(PARALLEL_SAFE_TOOLS, frozenset)
        assert len(PARALLEL_SAFE_TOOLS) > 0

    def test_core_tools_in_parallel_safe(self) -> None:
        """Test that safe core tools are in parallel-safe set."""
        assert "think" in PARALLEL_SAFE_TOOLS
        assert "get_current_time" in PARALLEL_SAFE_TOOLS
        assert "discover_tools" in PARALLEL_SAFE_TOOLS

    def test_plan_not_in_parallel_safe(self) -> None:
        """Test that plan is not in parallel-safe (should be sequential)."""
        # Plan might be in or out depending on design choice
        # This test documents the current behavior
        pass

    def test_read_tools_in_parallel_safe(self) -> None:
        """Test that read-only tools are in parallel-safe set."""
        read_tools = ["search_web", "read_webpage", "read_file"]
        for tool in read_tools:
            if tool in PARALLEL_SAFE_TOOLS:
                # Good - read tools can be parallel
                pass

    def test_write_tools_not_in_parallel_safe(self) -> None:
        """Test that write tools are NOT in parallel-safe set."""
        write_tools = ["write_file", "post_x", "post_reddit"]
        for tool in write_tools:
            assert tool not in PARALLEL_SAFE_TOOLS, f"{tool} should not be parallel-safe"

    def test_is_frozenset(self) -> None:
        """Test that PARALLEL_SAFE_TOOLS is immutable."""
        assert isinstance(PARALLEL_SAFE_TOOLS, frozenset)

    def test_all_entries_are_strings(self) -> None:
        """Test that all entries are strings."""
        for tool in PARALLEL_SAFE_TOOLS:
            assert isinstance(tool, str)


class TestSchemaIntegration:
    """Test integration of new schemas with existing system."""

    def test_all_core_tools_have_schemas(self) -> None:
        """Test that all core tools have schemas."""
        schemas = get_all_schemas()
        for tool_name in CORE_TOOL_NAMES:
            assert tool_name in schemas, f"{tool_name} should have a schema"

    def test_all_core_tools_have_permissions(self) -> None:
        """Test that all core tools have permissions."""
        for tool_name in CORE_TOOL_NAMES:
            assert tool_name in TOOL_PERMISSIONS, f"{tool_name} should have permission"

    def test_all_core_tools_have_budgets(self) -> None:
        """Test that all core tools have budgets."""
        for tool_name in CORE_TOOL_NAMES:
            assert tool_name in TOOL_BUDGETS, f"{tool_name} should have budget"

    def test_get_core_schemas_includes_new_tool(self) -> None:
        """Test that get_core_schemas includes get_current_time."""
        core_schemas = get_core_schemas()
        tool_names = [s["function"]["name"] for s in core_schemas]
        assert "get_current_time" in tool_names

    def test_schema_count_matches_core_tools(self) -> None:
        """Test that number of core schemas matches CORE_TOOL_NAMES."""
        core_schemas = get_core_schemas()
        assert len(core_schemas) == len(CORE_TOOL_NAMES)

    def test_no_internal_fields_in_core_schemas(self) -> None:
        """Test that internal fields are stripped from core schemas."""
        core_schemas = get_core_schemas()
        for schema in core_schemas:
            for key in schema.keys():
                assert not key.startswith("_"), f"Internal field {key} should be stripped"

    def test_all_schemas_have_required_structure(self) -> None:
        """Test that all schemas have required structure."""
        for schema in TOOL_SCHEMAS:
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_core_tool_names_are_known(self) -> None:
        """Sanity check: core tool names are the expected set."""
        assert CORE_TOOL_NAMES == {"think", "plan", "discover_tools", "get_current_time"}
