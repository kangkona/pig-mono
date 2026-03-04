"""Tests for tool schemas."""

from pig_agent_core.tools.schemas import (
    CORE_TOOL_NAMES,
    TOOL_BUDGETS,
    TOOL_PERMISSIONS,
    TOOL_SCHEMAS,
    get_all_schemas,
    get_core_schemas,
    strip_internal_fields,
)


def test_core_tool_names():
    """Test core tool names are defined."""
    assert "think" in CORE_TOOL_NAMES
    assert "plan" in CORE_TOOL_NAMES
    assert "discover_tools" in CORE_TOOL_NAMES
    assert len(CORE_TOOL_NAMES) == 3


def test_tool_schemas_structure():
    """Test tool schemas have correct structure."""
    for schema in TOOL_SCHEMAS:
        assert "type" in schema
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
        assert "_permission" in schema  # Internal field


def test_tool_schemas_openai_format():
    """Test schemas validate against OpenAI function calling format."""
    for schema in TOOL_SCHEMAS:
        func = schema["function"]

        # Check required fields
        assert isinstance(func["name"], str)
        assert isinstance(func["description"], str)
        assert isinstance(func["parameters"], dict)

        # Check parameters structure
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_think_tool_schema():
    """Test think tool schema."""
    think_schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "think")

    assert think_schema["_permission"] == "none"
    assert "thought" in think_schema["function"]["parameters"]["properties"]
    assert "thought" in think_schema["function"]["parameters"]["required"]


def test_plan_tool_schema():
    """Test plan tool schema."""
    plan_schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "plan")

    assert plan_schema["_permission"] == "none"

    props = plan_schema["function"]["parameters"]["properties"]
    assert "goal" in props
    assert "steps" in props
    assert props["steps"]["type"] == "array"

    required = plan_schema["function"]["parameters"]["required"]
    assert "goal" in required
    assert "steps" in required


def test_discover_tools_schema():
    """Test discover_tools schema."""
    discover_schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "discover_tools")

    assert discover_schema["_permission"] == "none"
    assert "query" in discover_schema["function"]["parameters"]["properties"]
    assert "query" in discover_schema["function"]["parameters"]["required"]


def test_tool_permissions():
    """Test tool permissions mapping."""
    assert TOOL_PERMISSIONS["think"] == "none"
    assert TOOL_PERMISSIONS["plan"] == "none"
    assert TOOL_PERMISSIONS["discover_tools"] == "none"

    # All tools should have permissions
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        assert name in TOOL_PERMISSIONS


def test_tool_budgets():
    """Test tool budgets configuration."""
    assert "think" in TOOL_BUDGETS
    assert "plan" in TOOL_BUDGETS
    assert "discover_tools" in TOOL_BUDGETS

    # Check budget structure
    for _tool_name, budget in TOOL_BUDGETS.items():
        assert "timeout" in budget
        assert "max_retries" in budget
        assert isinstance(budget["timeout"], int)
        assert isinstance(budget["max_retries"], int)


def test_strip_internal_fields():
    """Test stripping internal fields from schemas."""
    test_schemas = [
        {
            "type": "function",
            "_permission": "none",
            "_internal": "data",
            "function": {"name": "test"},
        }
    ]

    stripped = strip_internal_fields(test_schemas)

    assert len(stripped) == 1
    assert "_permission" not in stripped[0]
    assert "_internal" not in stripped[0]
    assert "type" in stripped[0]
    assert "function" in stripped[0]


def test_get_core_schemas():
    """Test getting core tool schemas."""
    core_schemas = get_core_schemas()

    # Should have exactly 3 core tools
    assert len(core_schemas) == 3

    # Check names
    names = {s["function"]["name"] for s in core_schemas}
    assert names == {"think", "plan", "discover_tools"}

    # Should not have internal fields
    for schema in core_schemas:
        assert "_permission" not in schema


def test_get_all_schemas():
    """Test getting all schemas as mapping."""
    all_schemas = get_all_schemas()

    # Should be a dict
    assert isinstance(all_schemas, dict)

    # Should have all tools
    assert "think" in all_schemas
    assert "plan" in all_schemas
    assert "discover_tools" in all_schemas

    # Should not have internal fields
    for name, schema in all_schemas.items():
        assert "_permission" not in schema
        assert schema["function"]["name"] == name


def test_schema_permissions_valid():
    """Test all schemas have valid permissions."""
    valid_permissions = {"none", "read", "storage", "write"}

    for schema in TOOL_SCHEMAS:
        permission = schema["_permission"]
        assert permission in valid_permissions


def test_schema_consistency():
    """Test consistency between schemas, permissions, and budgets."""
    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    permission_names = set(TOOL_PERMISSIONS.keys())
    budget_names = set(TOOL_BUDGETS.keys())

    # All schemas should have permissions
    assert schema_names == permission_names

    # All schemas should have budgets
    assert schema_names == budget_names
