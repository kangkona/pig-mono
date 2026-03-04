"""Tests for tool audit logging."""

import json
import tempfile
from pathlib import Path

from pig_agent_core.tools.audit import ToolAuditEntry, ToolAuditLog


class TestToolAuditEntry:
    """Test ToolAuditEntry dataclass."""

    def test_audit_entry_creation(self):
        """Test creating audit entry with required fields."""
        entry = ToolAuditEntry(
            tool_name="search_web",
            timestamp=1234567890.0,
            user_id="user123",
        )

        assert entry.tool_name == "search_web"
        assert entry.timestamp == 1234567890.0
        assert entry.user_id == "user123"
        assert entry.args == {}
        assert entry.success is True
        assert entry.error is None
        assert entry.duration == 0.0
        assert entry.result_size == 0
        assert entry.metadata == {}

    def test_audit_entry_with_all_fields(self):
        """Test creating audit entry with all fields."""
        entry = ToolAuditEntry(
            tool_name="search_web",
            timestamp=1234567890.0,
            user_id="user123",
            args={"query": "test"},
            success=False,
            error="Connection timeout",
            duration=5.5,
            result_size=1024,
            metadata={"retry": 1},
        )

        assert entry.tool_name == "search_web"
        assert entry.args == {"query": "test"}
        assert entry.success is False
        assert entry.error == "Connection timeout"
        assert entry.duration == 5.5
        assert entry.result_size == 1024
        assert entry.metadata == {"retry": 1}

    def test_audit_entry_to_dict(self):
        """Test converting audit entry to dictionary."""
        entry = ToolAuditEntry(
            tool_name="search_web",
            timestamp=1234567890.0,
            user_id="user123",
            args={"query": "test"},
            success=True,
            duration=2.5,
            result_size=512,
        )

        result = entry.to_dict()

        assert result["tool_name"] == "search_web"
        assert result["timestamp"] == 1234567890.0
        assert result["user_id"] == "user123"
        assert result["args"] == {"query": "test"}
        assert result["success"] is True
        assert result["error"] is None
        assert result["duration"] == 2.5
        assert result["result_size"] == 512


class TestToolAuditLog:
    """Test ToolAuditLog class."""

    def test_audit_log_creation(self):
        """Test creating audit log."""
        log = ToolAuditLog()
        assert len(log) == 0
        assert log.max_entries == 10000

    def test_audit_log_with_custom_max_entries(self):
        """Test creating audit log with custom max entries."""
        log = ToolAuditLog(max_entries=100)
        assert log.max_entries == 100

    def test_log_tool_execution(self):
        """Test logging a tool execution."""
        log = ToolAuditLog()
        log.log(
            tool_name="search_web",
            user_id="user123",
            args={"query": "test"},
            success=True,
            duration=2.5,
            result_size=512,
        )

        assert len(log) == 1
        entries = log.get_entries()
        assert len(entries) == 1
        assert entries[0].tool_name == "search_web"
        assert entries[0].user_id == "user123"

    def test_log_failed_execution(self):
        """Test logging a failed execution."""
        log = ToolAuditLog()
        log.log(
            tool_name="search_web",
            user_id="user123",
            success=False,
            error="Connection timeout",
        )

        entries = log.get_entries()
        assert entries[0].success is False
        assert entries[0].error == "Connection timeout"

    def test_log_with_metadata(self):
        """Test logging with metadata."""
        log = ToolAuditLog()
        log.log(
            tool_name="search_web",
            user_id="user123",
            metadata={"retry": 1, "source": "api"},
        )

        entries = log.get_entries()
        assert entries[0].metadata == {"retry": 1, "source": "api"}

    def test_get_entries_no_filter(self):
        """Test getting all entries."""
        log = ToolAuditLog()
        log.log("tool1", "user1")
        log.log("tool2", "user2")
        log.log("tool3", "user1")

        entries = log.get_entries()
        assert len(entries) == 3

    def test_get_entries_filter_by_tool_name(self):
        """Test filtering entries by tool name."""
        log = ToolAuditLog()
        log.log("search_web", "user1")
        log.log("read_file", "user1")
        log.log("search_web", "user2")

        entries = log.get_entries(tool_name="search_web")
        assert len(entries) == 2
        assert all(e.tool_name == "search_web" for e in entries)

    def test_get_entries_filter_by_user_id(self):
        """Test filtering entries by user ID."""
        log = ToolAuditLog()
        log.log("tool1", "user1")
        log.log("tool2", "user2")
        log.log("tool3", "user1")

        entries = log.get_entries(user_id="user1")
        assert len(entries) == 2
        assert all(e.user_id == "user1" for e in entries)

    def test_get_entries_filter_by_success(self):
        """Test filtering entries by success status."""
        log = ToolAuditLog()
        log.log("tool1", "user1", success=True)
        log.log("tool2", "user1", success=False, error="Error")
        log.log("tool3", "user1", success=True)

        entries = log.get_entries(success=False)
        assert len(entries) == 1
        assert entries[0].success is False

    def test_get_entries_multiple_filters(self):
        """Test filtering with multiple criteria."""
        log = ToolAuditLog()
        log.log("search_web", "user1", success=True)
        log.log("search_web", "user2", success=False, error="Error")
        log.log("read_file", "user1", success=True)

        entries = log.get_entries(tool_name="search_web", user_id="user1")
        assert len(entries) == 1
        assert entries[0].tool_name == "search_web"
        assert entries[0].user_id == "user1"

    def test_get_entries_with_limit(self):
        """Test limiting number of entries returned."""
        log = ToolAuditLog()
        for i in range(10):
            log.log(f"tool{i}", "user1")

        entries = log.get_entries(limit=5)
        assert len(entries) == 5

    def test_get_entries_sorted_by_timestamp(self):
        """Test entries are sorted by timestamp descending."""
        log = ToolAuditLog()
        log.log("tool1", "user1")
        log.log("tool2", "user1")
        log.log("tool3", "user1")

        entries = log.get_entries()
        # Most recent first
        assert entries[0].tool_name == "tool3"
        assert entries[1].tool_name == "tool2"
        assert entries[2].tool_name == "tool1"

    def test_get_failed_entries(self):
        """Test getting only failed entries."""
        log = ToolAuditLog()
        log.log("tool1", "user1", success=True)
        log.log("tool2", "user1", success=False, error="Error 1")
        log.log("tool3", "user1", success=False, error="Error 2")
        log.log("tool4", "user1", success=True)

        failed = log.get_failed_entries()
        assert len(failed) == 2
        assert all(not e.success for e in failed)

    def test_get_failed_entries_with_limit(self):
        """Test getting failed entries with limit."""
        log = ToolAuditLog()
        for i in range(5):
            log.log(f"tool{i}", "user1", success=False, error=f"Error {i}")

        failed = log.get_failed_entries(limit=3)
        assert len(failed) == 3

    def test_max_entries_trimming(self):
        """Test that old entries are trimmed when max is exceeded."""
        log = ToolAuditLog(max_entries=5)
        for i in range(10):
            log.log(f"tool{i}", "user1")

        assert len(log) == 5
        entries = log.get_entries()
        # Should keep most recent 5
        assert entries[0].tool_name == "tool9"
        assert entries[4].tool_name == "tool5"

    def test_export_json(self):
        """Test exporting audit log to JSON."""
        log = ToolAuditLog()
        log.log("tool1", "user1", args={"key": "value"}, success=True, duration=1.5)
        log.log("tool2", "user2", success=False, error="Error")

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            filepath = f.name

        try:
            log.export_json(filepath)

            # Read and verify
            with open(filepath) as f:
                data = json.load(f)

            assert len(data) == 2
            assert data[0]["tool_name"] == "tool1"
            assert data[0]["user_id"] == "user1"
            assert data[0]["args"] == {"key": "value"}
            assert data[1]["tool_name"] == "tool2"
            assert data[1]["success"] is False
        finally:
            Path(filepath).unlink()

    def test_clear(self):
        """Test clearing all entries."""
        log = ToolAuditLog()
        log.log("tool1", "user1")
        log.log("tool2", "user2")

        assert len(log) == 2

        log.clear()
        assert len(log) == 0

    def test_empty_log_operations(self):
        """Test operations on empty log."""
        log = ToolAuditLog()

        assert len(log) == 0
        assert log.get_entries() == []
        assert log.get_failed_entries() == []
        assert log.get_entries(tool_name="nonexistent") == []
