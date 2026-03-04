"""Tool metrics for tracking usage patterns and performance.

Provides aggregated statistics and performance metrics for tool executions.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolMetrics:
    """Aggregated metrics for a tool.

    Attributes:
        tool_name: Name of the tool
        total_calls: Total number of calls
        successful_calls: Number of successful calls
        failed_calls: Number of failed calls
        total_duration: Total execution time in seconds
        avg_duration: Average execution time in seconds
        min_duration: Minimum execution time in seconds
        max_duration: Maximum execution time in seconds
        total_result_size: Total size of results in characters
        avg_result_size: Average result size in characters
    """

    tool_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0
    total_result_size: int = 0
    avg_result_size: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
            "total_duration": self.total_duration,
            "avg_duration": self.avg_duration,
            "min_duration": self.min_duration if self.min_duration != float("inf") else 0.0,
            "max_duration": self.max_duration,
            "total_result_size": self.total_result_size,
            "avg_result_size": self.avg_result_size,
        }

    @property
    def success_rate(self) -> float:
        """Calculate success rate.

        Returns:
            Success rate as percentage (0-100)
        """
        if self.total_calls == 0:
            return 0.0
        return (self.successful_calls / self.total_calls) * 100


class ToolMetricsCollector:
    """Collector for tool execution metrics.

    Tracks aggregated statistics and performance metrics across tool executions.
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._metrics: dict[str, ToolMetrics] = {}
        self._user_metrics: dict[str, dict[str, ToolMetrics]] = defaultdict(dict)
        self._start_time = time.time()

    def record(
        self,
        tool_name: str,
        success: bool,
        duration: float,
        result_size: int = 0,
        user_id: str | None = None,
    ) -> None:
        """Record a tool execution.

        Args:
            tool_name: Name of the tool
            success: Whether execution succeeded
            duration: Execution duration in seconds
            result_size: Size of result in characters
            user_id: Optional user ID for per-user metrics
        """
        # Update global metrics
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetrics(tool_name=tool_name)

        metrics = self._metrics[tool_name]
        self._update_metrics(metrics, success, duration, result_size)

        # Update per-user metrics if user_id provided
        if user_id:
            if tool_name not in self._user_metrics[user_id]:
                self._user_metrics[user_id][tool_name] = ToolMetrics(tool_name=tool_name)

            user_metrics = self._user_metrics[user_id][tool_name]
            self._update_metrics(user_metrics, success, duration, result_size)

    def _update_metrics(
        self,
        metrics: ToolMetrics,
        success: bool,
        duration: float,
        result_size: int,
    ) -> None:
        """Update metrics object with new data.

        Args:
            metrics: Metrics object to update
            success: Whether execution succeeded
            duration: Execution duration
            result_size: Result size
        """
        metrics.total_calls += 1

        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1

        metrics.total_duration += duration
        metrics.avg_duration = metrics.total_duration / metrics.total_calls

        metrics.min_duration = min(metrics.min_duration, duration)
        metrics.max_duration = max(metrics.max_duration, duration)

        metrics.total_result_size += result_size
        metrics.avg_result_size = metrics.total_result_size / metrics.total_calls

    def get_metrics(self, tool_name: str) -> ToolMetrics | None:
        """Get metrics for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolMetrics object or None if tool not found
        """
        return self._metrics.get(tool_name)

    def get_all_metrics(self) -> dict[str, ToolMetrics]:
        """Get metrics for all tools.

        Returns:
            Dictionary mapping tool names to metrics
        """
        return self._metrics.copy()

    def get_user_metrics(
        self, user_id: str, tool_name: str | None = None
    ) -> dict[str, ToolMetrics]:
        """Get metrics for a specific user.

        Args:
            user_id: User ID
            tool_name: Optional tool name to filter by

        Returns:
            Dictionary mapping tool names to metrics
        """
        if user_id not in self._user_metrics:
            return {}

        user_metrics = self._user_metrics[user_id]

        if tool_name:
            if tool_name in user_metrics:
                return {tool_name: user_metrics[tool_name]}
            return {}

        return user_metrics.copy()

    def get_top_tools(self, limit: int = 10, by: str = "calls") -> list[ToolMetrics]:
        """Get top tools by usage or performance.

        Args:
            limit: Maximum number of tools to return
            by: Sort criterion ("calls", "duration", "failures")

        Returns:
            List of ToolMetrics sorted by criterion
        """
        metrics_list = list(self._metrics.values())

        if by == "calls":
            metrics_list.sort(key=lambda m: m.total_calls, reverse=True)
        elif by == "duration":
            metrics_list.sort(key=lambda m: m.total_duration, reverse=True)
        elif by == "failures":
            metrics_list.sort(key=lambda m: m.failed_calls, reverse=True)
        else:
            raise ValueError(f"Invalid sort criterion: {by}")

        return metrics_list[:limit]

    def get_summary(self) -> dict[str, Any]:
        """Get overall summary statistics.

        Returns:
            Dictionary with summary statistics
        """
        total_calls = sum(m.total_calls for m in self._metrics.values())
        total_successful = sum(m.successful_calls for m in self._metrics.values())
        total_failed = sum(m.failed_calls for m in self._metrics.values())
        total_duration = sum(m.total_duration for m in self._metrics.values())

        uptime = time.time() - self._start_time

        return {
            "total_tools": len(self._metrics),
            "total_calls": total_calls,
            "successful_calls": total_successful,
            "failed_calls": total_failed,
            "success_rate": (total_successful / total_calls * 100) if total_calls > 0 else 0.0,
            "total_duration": total_duration,
            "avg_duration": total_duration / total_calls if total_calls > 0 else 0.0,
            "uptime": uptime,
            "calls_per_second": total_calls / uptime if uptime > 0 else 0.0,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()
        self._user_metrics.clear()
        self._start_time = time.time()

    def __len__(self) -> int:
        """Get number of tools being tracked."""
        return len(self._metrics)
