"""Tests for tool base types."""

import json

import pytest
from pig_agent_core.tools import CancelledError, ToolResult


def test_tool_result_success():
    """Test successful tool result."""
    result = ToolResult(ok=True, data={"message": "success"})
    assert result.ok is True
    assert result.data == {"message": "success"}
    assert result.error is None


def test_tool_result_error():
    """Test error tool result."""
    result = ToolResult(ok=False, error="Something went wrong")
    assert result.ok is False
    assert result.data is None
    assert result.error == "Something went wrong"


def test_tool_result_with_meta():
    """Test tool result with metadata."""
    result = ToolResult(ok=True, data="test", meta={"duration_ms": 100})
    assert result.meta == {"duration_ms": 100}


def test_tool_result_serialize_simple():
    """Test serialization of simple result."""
    result = ToolResult(ok=True, data="Hello world")
    serialized = result.serialize()
    parsed = json.loads(serialized)
    assert parsed == {"ok": True, "data": "Hello world"}


def test_tool_result_serialize_error():
    """Test serialization of error result."""
    result = ToolResult(ok=False, error="Failed")
    serialized = result.serialize()
    parsed = json.loads(serialized)
    assert parsed == {"ok": False, "error": "Failed"}


def test_tool_result_serialize_truncation():
    """Test serialization with truncation."""
    # Create a large data payload
    large_data = "x" * 5000
    result = ToolResult(ok=True, data=large_data)

    # Serialize with small limit
    serialized = result.serialize(max_chars=100)
    assert len(serialized) <= 100

    # Should have truncation marker
    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    assert "truncated" in parsed or "data_preview" in parsed


def test_tool_result_serialize_list():
    """Test serialization of list data."""
    data = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}, {"id": 3, "name": "Item 3"}]
    result = ToolResult(ok=True, data=data)

    serialized = result.serialize()
    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    assert parsed["data"] == data


def test_tool_result_serialize_list_truncation():
    """Test serialization of list with truncation."""
    # Create list with many items
    data = [{"id": i, "text": "x" * 100} for i in range(100)]
    result = ToolResult(ok=True, data=data)

    # Serialize with limit
    serialized = result.serialize(max_chars=500)
    assert len(serialized) <= 500

    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    # Should have fewer items or truncated text
    if "data" in parsed:
        assert len(parsed["data"]) < len(data)


def test_tool_result_serialize_dict_with_text_fields():
    """Test serialization of dict with text fields."""
    data = [
        {"id": 1, "content": "x" * 500, "title": "Item 1"},
        {"id": 2, "content": "y" * 500, "title": "Item 2"},
    ]
    result = ToolResult(ok=True, data=data)

    serialized = result.serialize(max_chars=600)
    assert len(serialized) <= 600

    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    # Content fields should be truncated
    if "data" in parsed and isinstance(parsed["data"], list):
        for item in parsed["data"]:
            if "content" in item:
                assert len(item["content"]) <= 201  # 200 + ellipsis


def test_tool_result_serialize_nested_structure():
    """Test serialization of nested structure."""
    data = {
        "posts": [
            {"id": 1, "text": "Post 1", "comments": [{"id": 1, "body": "Comment 1"}]},
            {"id": 2, "text": "Post 2", "comments": [{"id": 2, "body": "Comment 2"}]},
        ]
    }
    result = ToolResult(ok=True, data=data)

    serialized = result.serialize()
    parsed = json.loads(serialized)
    assert parsed["ok"] is True
    assert "data" in parsed


def test_cancelled_error():
    """Test CancelledError exception."""
    with pytest.raises(CancelledError):
        raise CancelledError("Operation cancelled")


def test_tool_result_serialize_preserves_structure():
    """Test that serialization preserves structure when possible."""
    data = {"count": 5, "items": ["a", "b", "c"]}
    result = ToolResult(ok=True, data=data)

    serialized = result.serialize(max_chars=1000)
    parsed = json.loads(serialized)

    assert parsed["ok"] is True
    assert parsed["data"]["count"] == 5
    assert parsed["data"]["items"] == ["a", "b", "c"]
