"""Billing and cost tracking for coding agent."""

import json
from pathlib import Path
from typing import Any


class CostTracker:
    """Track LLM and tool usage costs."""

    # Pricing per 1M tokens (as of 2024)
    PRICING = {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        "gemini-pro": {"input": 0.5, "output": 1.5},
    }

    def __init__(self, workspace: Path | None = None):
        """Initialize cost tracker.

        Args:
            workspace: Workspace directory for saving usage data
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.usage_file = self.workspace / ".agents" / "usage.json"

        # In-memory tracking
        self.llm_calls: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []

        # Load existing usage
        self._load_usage()

    def _load_usage(self):
        """Load usage data from file."""
        if self.usage_file.exists():
            try:
                data = json.loads(self.usage_file.read_text())
                self.llm_calls = data.get("llm_calls", [])
                self.tool_calls = data.get("tool_calls", [])
            except Exception:
                pass

    def _save_usage(self):
        """Save usage data to file."""
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"llm_calls": self.llm_calls, "tool_calls": self.tool_calls}
        self.usage_file.write_text(json.dumps(data, indent=2))

    def on_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track LLM call.

        Args:
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            user_id: Optional user ID
            metadata: Optional metadata
        """
        # Calculate cost
        pricing = self.PRICING.get(model, {"input": 1.0, "output": 2.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        call_data = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": total_cost,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        self.llm_calls.append(call_data)
        self._save_usage()

    def on_tool_call(
        self,
        tool_name: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track tool call.

        Args:
            tool_name: Tool name
            user_id: Optional user ID
            metadata: Optional metadata
        """
        call_data = {
            "tool_name": tool_name,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        self.tool_calls.append(call_data)
        self._save_usage()

    def get_usage_summary(self, user_id: str | None = None) -> dict[str, Any]:
        """Get usage summary.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            Usage summary dictionary
        """
        # Filter by user if specified
        llm_calls = self.llm_calls
        tool_calls = self.tool_calls

        if user_id:
            llm_calls = [c for c in llm_calls if c.get("user_id") == user_id]
            tool_calls = [c for c in tool_calls if c.get("user_id") == user_id]

        # Calculate totals
        total_input_tokens = sum(c["input_tokens"] for c in llm_calls)
        total_output_tokens = sum(c["output_tokens"] for c in llm_calls)
        total_cost = sum(c["cost"] for c in llm_calls)

        # Group by model
        by_model: dict[str, dict[str, Any]] = {}
        for call in llm_calls:
            model = call["model"]
            if model not in by_model:
                by_model[model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                }
            by_model[model]["calls"] += 1
            by_model[model]["input_tokens"] += call["input_tokens"]
            by_model[model]["output_tokens"] += call["output_tokens"]
            by_model[model]["cost"] += call["cost"]

        # Group tools by name
        by_tool: dict[str, int] = {}
        for call in tool_calls:
            tool_name = call["tool_name"]
            by_tool[tool_name] = by_tool.get(tool_name, 0) + 1

        return {
            "total_llm_calls": len(llm_calls),
            "total_tool_calls": len(tool_calls),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost": total_cost,
            "by_model": by_model,
            "by_tool": by_tool,
        }

    def reset_usage(self):
        """Reset all usage tracking."""
        self.llm_calls = []
        self.tool_calls = []
        self._save_usage()

    def format_summary(self, user_id: str | None = None) -> str:
        """Format usage summary as text.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            Formatted summary string
        """
        summary = self.get_usage_summary(user_id)

        lines = ["**Usage Summary**\n"]
        lines.append(f"Total LLM calls: {summary['total_llm_calls']}")
        lines.append(f"Total tool calls: {summary['total_tool_calls']}")
        lines.append(
            f"Total tokens: {summary['total_input_tokens']:,} in + "
            f"{summary['total_output_tokens']:,} out"
        )
        lines.append(f"Total cost: ${summary['total_cost']:.4f}\n")

        if summary["by_model"]:
            lines.append("**By Model:**")
            for model, stats in summary["by_model"].items():
                lines.append(
                    f"  {model}: {stats['calls']} calls, "
                    f"{stats['input_tokens']:,} in + {stats['output_tokens']:,} out, "
                    f"${stats['cost']:.4f}"
                )
            lines.append("")

        if summary["by_tool"]:
            lines.append("**By Tool:**")
            for tool, count in sorted(summary["by_tool"].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {tool}: {count} calls")

        return "\n".join(lines)
