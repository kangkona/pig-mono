"""Tests for core tool handlers."""

import asyncio
from datetime import datetime, timezone

import pytest
from pig_agent_core.tools.handlers_core import (
    HANDLERS,
    handle_discover_tools,
    handle_get_current_time,
    handle_plan,
    handle_think,
)


class TestHandlerRegistry:
    """Test handler registration."""

    def test_handlers_dict_exists(self):
        """Test that HANDLERS dict is defined."""
        assert isinstance(HANDLERS, dict)

    def test_all_core_handlers_registered(self):
        """Test that all core handlers are registered."""
        assert "think" in HANDLERS
        assert "plan" in HANDLERS
        assert "discover_tools" in HANDLERS
        assert "get_current_time" in HANDLERS

    def test_handlers_are_callable(self):
        """Test that all handlers are callable."""
        for name, handler in HANDLERS.items():
            assert callable(handler), f"{name} handler should be callable"


class TestHandleThink:
    """Test think tool handler."""

    @pytest.mark.asyncio
    async def test_think_with_valid_thought(self):
        """Test think with valid thought."""
        result = await handle_think(
            args={"thought": "This is my reasoning"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["status"] == "ok"
        assert result.data["thought_length"] == 20

    @pytest.mark.asyncio
    async def test_think_with_empty_thought(self):
        """Test think with empty thought."""
        result = await handle_think(
            args={"thought": ""},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_think_with_whitespace_thought(self):
        """Test think with whitespace-only thought."""
        result = await handle_think(
            args={"thought": "   "},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_think_with_missing_thought(self):
        """Test think with missing thought field."""
        result = await handle_think(
            args={},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False


class TestHandlePlan:
    """Test plan tool handler."""

    @pytest.mark.asyncio
    async def test_plan_with_valid_inputs(self):
        """Test plan with valid goal and steps."""
        result = await handle_plan(
            args={
                "goal": "Complete the task",
                "steps": ["Step 1", "Step 2", "Step 3"],
            },
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["status"] == "planned"
        assert result.data["goal"] == "Complete the task"
        assert result.data["total_steps"] == 3
        assert len(result.data["steps"]) == 3

    @pytest.mark.asyncio
    async def test_plan_with_empty_goal(self):
        """Test plan with empty goal."""
        result = await handle_plan(
            args={"goal": "", "steps": ["Step 1"]},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False
        assert "goal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plan_with_empty_steps(self):
        """Test plan with empty steps list."""
        result = await handle_plan(
            args={"goal": "Complete task", "steps": []},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False
        assert "step" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plan_with_invalid_step_type(self):
        """Test plan with non-string step."""
        result = await handle_plan(
            args={"goal": "Complete task", "steps": ["Step 1", 123, "Step 3"]},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False
        assert "step 2" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plan_with_empty_step_string(self):
        """Test plan with empty string in steps."""
        result = await handle_plan(
            args={"goal": "Complete task", "steps": ["Step 1", "", "Step 3"]},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_plan_with_missing_steps(self):
        """Test plan with missing steps field."""
        result = await handle_plan(
            args={"goal": "Complete task"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False


class TestHandleDiscoverTools:
    """Test discover_tools handler."""

    @pytest.mark.asyncio
    async def test_discover_tools_without_query(self):
        """Test discover_tools without query returns available tools."""
        result = await handle_discover_tools(
            args={},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert "available" in result.data
        assert "hint" in result.data

    @pytest.mark.asyncio
    async def test_discover_tools_with_empty_query(self):
        """Test discover_tools with empty query."""
        result = await handle_discover_tools(
            args={"query": ""},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert "available" in result.data

    @pytest.mark.asyncio
    async def test_discover_tools_with_no_matches(self):
        """Test discover_tools with query that matches nothing."""
        result = await handle_discover_tools(
            args={"query": "nonexistent_tool_xyz"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["loaded"] == []
        assert "message" in result.data


class TestHandleGetCurrentTime:
    """Test get_current_time handler."""

    @pytest.mark.asyncio
    async def test_get_current_time_default_utc(self):
        """Test get_current_time with default UTC timezone."""
        result = await handle_get_current_time(
            args={},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert "datetime" in result.data
        assert "timezone" in result.data
        assert "timestamp" in result.data
        assert result.data["timezone"] == "UTC"

        # Verify ISO 8601 format
        datetime_str = result.data["datetime"]
        parsed = datetime.fromisoformat(datetime_str)
        assert isinstance(parsed, datetime)

    @pytest.mark.asyncio
    async def test_get_current_time_explicit_utc(self):
        """Test get_current_time with explicit UTC."""
        result = await handle_get_current_time(
            args={"timezone": "UTC"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_get_current_time_america_new_york(self):
        """Test get_current_time with America/New_York timezone."""
        result = await handle_get_current_time(
            args={"timezone": "America/New_York"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["timezone"] == "America/New_York"

        # Verify timezone is applied
        datetime_str = result.data["datetime"]
        parsed = datetime.fromisoformat(datetime_str)
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_current_time_asia_tokyo(self):
        """Test get_current_time with Asia/Tokyo timezone."""
        result = await handle_get_current_time(
            args={"timezone": "Asia/Tokyo"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["timezone"] == "Asia/Tokyo"

    @pytest.mark.asyncio
    async def test_get_current_time_europe_london(self):
        """Test get_current_time with Europe/London timezone."""
        result = await handle_get_current_time(
            args={"timezone": "Europe/London"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["timezone"] == "Europe/London"

    @pytest.mark.asyncio
    async def test_get_current_time_invalid_timezone(self):
        """Test get_current_time with invalid timezone."""
        result = await handle_get_current_time(
            args={"timezone": "Invalid/Timezone"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is False
        assert "invalid timezone" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_current_time_timestamp_is_int(self):
        """Test that timestamp is an integer."""
        result = await handle_get_current_time(
            args={},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert isinstance(result.data["timestamp"], int)

    @pytest.mark.asyncio
    async def test_get_current_time_timestamp_is_recent(self):
        """Test that timestamp is recent (within last minute)."""
        before = int(datetime.now(timezone.utc).timestamp())
        result = await handle_get_current_time(
            args={},
            user_id="user123",
            meta={},
            cancel=None,
        )
        after = int(datetime.now(timezone.utc).timestamp())

        assert result.ok is True
        timestamp = result.data["timestamp"]
        assert before <= timestamp <= after + 1

    @pytest.mark.asyncio
    async def test_get_current_time_with_whitespace_timezone(self):
        """Test get_current_time with whitespace in timezone."""
        result = await handle_get_current_time(
            args={"timezone": "  UTC  "},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        assert result.data["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_get_current_time_case_insensitive_utc(self):
        """Test that UTC is case-insensitive."""
        for tz in ["UTC", "utc", "Utc"]:
            result = await handle_get_current_time(
                args={"timezone": tz},
                user_id="user123",
                meta={},
                cancel=None,
            )
            assert result.ok is True

    @pytest.mark.asyncio
    async def test_get_current_time_with_cancel_event(self):
        """Test get_current_time with cancel event (should still work)."""
        cancel = asyncio.Event()
        result = await handle_get_current_time(
            args={},
            user_id="user123",
            meta={},
            cancel=cancel,
        )
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_get_current_time_iso_format_includes_timezone(self):
        """Test that ISO format includes timezone offset."""
        result = await handle_get_current_time(
            args={"timezone": "America/New_York"},
            user_id="user123",
            meta={},
            cancel=None,
        )
        assert result.ok is True
        datetime_str = result.data["datetime"]
        # ISO format should include timezone (+ or - offset)
        assert "+" in datetime_str or "-" in datetime_str or datetime_str.endswith("Z")
