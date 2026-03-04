"""Tests for tool metrics collection."""

import pytest
from pig_agent_core.tools.metrics import ToolMetrics, ToolMetricsCollector


class TestToolMetrics:
    """Test ToolMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics with default values."""
        metrics = ToolMetrics(tool_name="search_web")

        assert metrics.tool_name == "search_web"
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.total_duration == 0.0
        assert metrics.avg_duration == 0.0
        assert metrics.min_duration == float("inf")
        assert metrics.max_duration == 0.0
        assert metrics.total_result_size == 0
        assert metrics.avg_result_size == 0.0

    def test_metrics_with_values(self):
        """Test creating metrics with custom values."""
        metrics = ToolMetrics(
            tool_name="search_web",
            total_calls=10,
            successful_calls=8,
            failed_calls=2,
            total_duration=25.5,
            avg_duration=2.55,
            min_duration=1.0,
            max_duration=5.0,
            total_result_size=10240,
            avg_result_size=1024.0,
        )

        assert metrics.total_calls == 10
        assert metrics.successful_calls == 8
        assert metrics.failed_calls == 2

    def test_success_rate_calculation(self):
        """Test success rate property."""
        metrics = ToolMetrics(
            tool_name="search_web",
            total_calls=10,
            successful_calls=8,
            failed_calls=2,
        )

        assert metrics.success_rate == 80.0

    def test_success_rate_zero_calls(self):
        """Test success rate with zero calls."""
        metrics = ToolMetrics(tool_name="search_web")
        assert metrics.success_rate == 0.0

    def test_success_rate_all_successful(self):
        """Test success rate with all successful calls."""
        metrics = ToolMetrics(
            tool_name="search_web",
            total_calls=5,
            successful_calls=5,
        )

        assert metrics.success_rate == 100.0

    def test_success_rate_all_failed(self):
        """Test success rate with all failed calls."""
        metrics = ToolMetrics(
            tool_name="search_web",
            total_calls=5,
            failed_calls=5,
        )

        assert metrics.success_rate == 0.0

    def test_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = ToolMetrics(
            tool_name="search_web",
            total_calls=10,
            successful_calls=8,
            failed_calls=2,
            total_duration=25.5,
            avg_duration=2.55,
            min_duration=1.0,
            max_duration=5.0,
            total_result_size=10240,
            avg_result_size=1024.0,
        )

        result = metrics.to_dict()

        assert result["tool_name"] == "search_web"
        assert result["total_calls"] == 10
        assert result["successful_calls"] == 8
        assert result["failed_calls"] == 2
        assert result["success_rate"] == 80.0
        assert result["total_duration"] == 25.5
        assert result["avg_duration"] == 2.55
        assert result["min_duration"] == 1.0
        assert result["max_duration"] == 5.0
        assert result["total_result_size"] == 10240
        assert result["avg_result_size"] == 1024.0

    def test_to_dict_with_inf_min_duration(self):
        """Test to_dict converts inf min_duration to 0.0."""
        metrics = ToolMetrics(tool_name="search_web")
        result = metrics.to_dict()

        assert result["min_duration"] == 0.0


class TestToolMetricsCollector:
    """Test ToolMetricsCollector class."""

    def test_collector_creation(self):
        """Test creating metrics collector."""
        collector = ToolMetricsCollector()
        assert len(collector) == 0

    def test_record_successful_call(self):
        """Test recording a successful call."""
        collector = ToolMetricsCollector()
        collector.record("search_web", success=True, duration=2.5, result_size=512)

        metrics = collector.get_metrics("search_web")
        assert metrics is not None
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0
        assert metrics.total_duration == 2.5
        assert metrics.avg_duration == 2.5
        assert metrics.min_duration == 2.5
        assert metrics.max_duration == 2.5
        assert metrics.total_result_size == 512
        assert metrics.avg_result_size == 512.0

    def test_record_failed_call(self):
        """Test recording a failed call."""
        collector = ToolMetricsCollector()
        collector.record("search_web", success=False, duration=1.0)

        metrics = collector.get_metrics("search_web")
        assert metrics.total_calls == 1
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 1

    def test_record_multiple_calls(self):
        """Test recording multiple calls."""
        collector = ToolMetricsCollector()
        collector.record("search_web", success=True, duration=2.0, result_size=500)
        collector.record("search_web", success=True, duration=3.0, result_size=600)
        collector.record("search_web", success=False, duration=1.0, result_size=0)

        metrics = collector.get_metrics("search_web")
        assert metrics.total_calls == 3
        assert metrics.successful_calls == 2
        assert metrics.failed_calls == 1
        assert metrics.total_duration == 6.0
        assert metrics.avg_duration == 2.0
        assert metrics.min_duration == 1.0
        assert metrics.max_duration == 3.0
        assert metrics.total_result_size == 1100
        assert metrics.avg_result_size == pytest.approx(366.67, rel=0.01)

    def test_record_multiple_tools(self):
        """Test recording calls for multiple tools."""
        collector = ToolMetricsCollector()
        collector.record("search_web", success=True, duration=2.0)
        collector.record("read_file", success=True, duration=1.0)
        collector.record("search_web", success=True, duration=3.0)

        assert len(collector) == 2
        assert collector.get_metrics("search_web").total_calls == 2
        assert collector.get_metrics("read_file").total_calls == 1

    def test_record_with_user_id(self):
        """Test recording with user ID for per-user metrics."""
        collector = ToolMetricsCollector()
        collector.record("search_web", success=True, duration=2.0, user_id="user1")
        collector.record("search_web", success=True, duration=3.0, user_id="user2")
        collector.record("search_web", success=True, duration=1.0, user_id="user1")

        # Global metrics
        global_metrics = collector.get_metrics("search_web")
        assert global_metrics.total_calls == 3

        # Per-user metrics
        user1_metrics = collector.get_user_metrics("user1", "search_web")
        assert len(user1_metrics) == 1
        assert user1_metrics["search_web"].total_calls == 2

        user2_metrics = collector.get_user_metrics("user2", "search_web")
        assert user2_metrics["search_web"].total_calls == 1

    def test_get_metrics_nonexistent_tool(self):
        """Test getting metrics for nonexistent tool."""
        collector = ToolMetricsCollector()
        assert collector.get_metrics("nonexistent") is None

    def test_get_all_metrics(self):
        """Test getting all metrics."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=1.0)
        collector.record("tool2", success=True, duration=2.0)
        collector.record("tool3", success=True, duration=3.0)

        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 3
        assert "tool1" in all_metrics
        assert "tool2" in all_metrics
        assert "tool3" in all_metrics

    def test_get_user_metrics_all_tools(self):
        """Test getting all tools for a user."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=1.0, user_id="user1")
        collector.record("tool2", success=True, duration=2.0, user_id="user1")
        collector.record("tool3", success=True, duration=3.0, user_id="user2")

        user1_metrics = collector.get_user_metrics("user1")
        assert len(user1_metrics) == 2
        assert "tool1" in user1_metrics
        assert "tool2" in user1_metrics

    def test_get_user_metrics_nonexistent_user(self):
        """Test getting metrics for nonexistent user."""
        collector = ToolMetricsCollector()
        assert collector.get_user_metrics("nonexistent") == {}

    def test_get_top_tools_by_calls(self):
        """Test getting top tools by call count."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=1.0)
        collector.record("tool2", success=True, duration=1.0)
        collector.record("tool2", success=True, duration=1.0)
        collector.record("tool3", success=True, duration=1.0)
        collector.record("tool3", success=True, duration=1.0)
        collector.record("tool3", success=True, duration=1.0)

        top_tools = collector.get_top_tools(limit=2, by="calls")
        assert len(top_tools) == 2
        assert top_tools[0].tool_name == "tool3"
        assert top_tools[0].total_calls == 3
        assert top_tools[1].tool_name == "tool2"
        assert top_tools[1].total_calls == 2

    def test_get_top_tools_by_duration(self):
        """Test getting top tools by total duration."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=5.0)
        collector.record("tool2", success=True, duration=10.0)
        collector.record("tool3", success=True, duration=3.0)

        top_tools = collector.get_top_tools(limit=2, by="duration")
        assert len(top_tools) == 2
        assert top_tools[0].tool_name == "tool2"
        assert top_tools[1].tool_name == "tool1"

    def test_get_top_tools_by_failures(self):
        """Test getting top tools by failure count."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=False, duration=1.0)
        collector.record("tool2", success=False, duration=1.0)
        collector.record("tool2", success=False, duration=1.0)
        collector.record("tool3", success=True, duration=1.0)

        top_tools = collector.get_top_tools(limit=2, by="failures")
        assert len(top_tools) == 2
        assert top_tools[0].tool_name == "tool2"
        assert top_tools[0].failed_calls == 2
        assert top_tools[1].tool_name == "tool1"
        assert top_tools[1].failed_calls == 1

    def test_get_top_tools_invalid_criterion(self):
        """Test getting top tools with invalid criterion."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=1.0)

        with pytest.raises(ValueError, match="Invalid sort criterion"):
            collector.get_top_tools(by="invalid")

    def test_get_summary(self):
        """Test getting overall summary."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=2.0)
        collector.record("tool2", success=True, duration=3.0)
        collector.record("tool1", success=False, duration=1.0)

        summary = collector.get_summary()

        assert summary["total_tools"] == 2
        assert summary["total_calls"] == 3
        assert summary["successful_calls"] == 2
        assert summary["failed_calls"] == 1
        assert summary["success_rate"] == pytest.approx(66.67, rel=0.01)
        assert summary["total_duration"] == 6.0
        assert summary["avg_duration"] == 2.0
        assert summary["uptime"] >= 0
        assert summary["calls_per_second"] >= 0

    def test_get_summary_empty(self):
        """Test getting summary with no data."""
        collector = ToolMetricsCollector()
        summary = collector.get_summary()

        assert summary["total_tools"] == 0
        assert summary["total_calls"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["avg_duration"] == 0.0

    def test_reset(self):
        """Test resetting all metrics."""
        collector = ToolMetricsCollector()
        collector.record("tool1", success=True, duration=1.0)
        collector.record("tool2", success=True, duration=2.0)

        assert len(collector) == 2

        collector.reset()

        assert len(collector) == 0
        assert collector.get_all_metrics() == {}
        summary = collector.get_summary()
        assert summary["total_calls"] == 0
