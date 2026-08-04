"""Tests for cost tracking."""

import tempfile
from pathlib import Path
from typing import Any

from pig_coding_agent.billing import CostTracker, CostTrackerBillingHook


def test_cost_tracker_initialization() -> None:
    """Test cost tracker initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))
        assert tracker.workspace == Path(tmpdir)
        assert len(tracker.llm_calls) == 0
        assert len(tracker.tool_calls) == 0


def test_on_llm_call() -> None:
    """Test tracking LLM call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_llm_call(
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
            user_id="user123",
        )

        assert len(tracker.llm_calls) == 1
        call = tracker.llm_calls[0]
        assert call["model"] == "gpt-4"
        assert call["input_tokens"] == 1000
        assert call["output_tokens"] == 500
        assert call["user_id"] == "user123"
        assert "cost" in call
        assert call["cost"] > 0


def test_on_llm_call_cost_calculation() -> None:
    """Test LLM call cost calculation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        # GPT-4: $30/1M input, $60/1M output
        tracker.on_llm_call(model="gpt-4", input_tokens=1_000_000, output_tokens=1_000_000)

        call = tracker.llm_calls[0]
        expected_cost = 30.0 + 60.0  # $90 total
        assert abs(call["cost"] - expected_cost) < 0.01


def test_on_tool_call() -> None:
    """Test tracking tool call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_tool_call(tool_name="read_file", user_id="user123")

        assert len(tracker.tool_calls) == 1
        call = tracker.tool_calls[0]
        assert call["tool_name"] == "read_file"
        assert call["user_id"] == "user123"


def test_get_usage_summary() -> None:
    """Test getting usage summary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        # Add some calls
        tracker.on_llm_call("gpt-4", 1000, 500)
        tracker.on_llm_call("gpt-3.5-turbo", 2000, 1000)
        tracker.on_tool_call("read_file")
        tracker.on_tool_call("write_file")

        summary = tracker.get_usage_summary()

        assert summary["total_llm_calls"] == 2
        assert summary["total_tool_calls"] == 2
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        assert summary["total_cost"] > 0


def test_get_usage_summary_by_model() -> None:
    """Test usage summary grouped by model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_llm_call("gpt-4", 1000, 500)
        tracker.on_llm_call("gpt-4", 2000, 1000)
        tracker.on_llm_call("gpt-3.5-turbo", 3000, 1500)

        summary = tracker.get_usage_summary()

        assert "gpt-4" in summary["by_model"]
        assert "gpt-3.5-turbo" in summary["by_model"]

        gpt4_stats = summary["by_model"]["gpt-4"]
        assert gpt4_stats["calls"] == 2
        assert gpt4_stats["input_tokens"] == 3000
        assert gpt4_stats["output_tokens"] == 1500


def test_get_usage_summary_by_tool() -> None:
    """Test usage summary grouped by tool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_tool_call("read_file")
        tracker.on_tool_call("read_file")
        tracker.on_tool_call("write_file")

        summary = tracker.get_usage_summary()

        assert summary["by_tool"]["read_file"] == 2
        assert summary["by_tool"]["write_file"] == 1


def test_get_usage_summary_filtered_by_user() -> None:
    """Test usage summary filtered by user ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_llm_call("gpt-4", 1000, 500, user_id="user1")
        tracker.on_llm_call("gpt-4", 2000, 1000, user_id="user2")
        tracker.on_tool_call("read_file", user_id="user1")
        tracker.on_tool_call("write_file", user_id="user2")

        summary = tracker.get_usage_summary(user_id="user1")

        assert summary["total_llm_calls"] == 1
        assert summary["total_tool_calls"] == 1
        assert summary["total_input_tokens"] == 1000


def test_reset_usage() -> None:
    """Test resetting usage data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_llm_call("gpt-4", 1000, 500)
        tracker.on_tool_call("read_file")

        assert len(tracker.llm_calls) == 1
        assert len(tracker.tool_calls) == 1

        tracker.reset_usage()

        assert len(tracker.llm_calls) == 0
        assert len(tracker.tool_calls) == 0


def test_format_summary() -> None:
    """Test formatting usage summary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        tracker.on_llm_call("gpt-4", 1000, 500)
        tracker.on_tool_call("read_file")

        formatted = tracker.format_summary()

        assert "Usage Summary" in formatted
        assert "Total LLM calls: 1" in formatted
        assert "Total tool calls: 1" in formatted
        assert "gpt-4" in formatted
        assert "read_file" in formatted


def test_persistence() -> None:
    """Test usage data persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create tracker and add data
        tracker1 = CostTracker(Path(tmpdir))
        tracker1.on_llm_call("gpt-4", 1000, 500)
        tracker1.on_tool_call("read_file")

        # Create new tracker (should load existing data)
        tracker2 = CostTracker(Path(tmpdir))

        assert len(tracker2.llm_calls) == 1
        assert len(tracker2.tool_calls) == 1
        assert tracker2.llm_calls[0]["model"] == "gpt-4"
        assert tracker2.tool_calls[0]["tool_name"] == "read_file"


def test_unknown_model_pricing() -> None:
    """Test handling unknown model pricing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = CostTracker(Path(tmpdir))

        # Use unknown model
        tracker.on_llm_call("unknown-model", 1000, 500)

        call = tracker.llm_calls[0]
        # Should use default pricing
        assert call["cost"] > 0


def test_cached_tokens_are_billed_at_cache_read_rate(tmp_path: Any) -> None:
    """Cached input tokens are discounted at the model's cache-read rate."""
    from pig_coding_agent.billing import CostTracker

    ct = CostTracker(tmp_path)
    # gpt-4o-2024-08-06: input 2.5, output 10, cache_read 1.25 ($/M)
    ct.on_llm_call(
        model="gpt-4o-2024-08-06", input_tokens=1000, output_tokens=50, cached_tokens=800
    )
    summary = ct.get_usage_summary()
    # 200 fresh@2.5 + 800 cached@1.25 + 50 out@10 = 0.0005 + 0.001 + 0.0005 = 0.002
    assert abs(summary["total_cost"] - 0.002) < 1e-6
    assert summary["total_cached_tokens"] == 800


def test_cached_tokens_remain_the_fourth_positional_argument(tmp_path: Any) -> None:
    """Keep the original CostTracker positional API stable for existing callers."""
    tracker = CostTracker(tmp_path)

    tracker.on_llm_call("gpt-4o-2024-08-06", 1000, 50, 800, "legacy-user")

    call = tracker.llm_calls[-1]
    assert call["cached_tokens"] == 800
    assert call["user_id"] == "legacy-user"


def test_billing_hook_adapter_forwards_core_keywords_to_legacy_tracker(tmp_path: Any) -> None:
    """Keep the core hook protocol separate from CostTracker's public positional API."""
    tracker = CostTracker(tmp_path)
    hook = CostTrackerBillingHook(tracker)

    hook.on_llm_call(
        "gpt-4o-2024-08-06",
        1000,
        50,
        user_id="core-user",
        metadata={"source": "core"},
        cached_tokens=800,
    )

    call = tracker.llm_calls[-1]
    assert call["cached_tokens"] == 800
    assert call["user_id"] == "core-user"
    assert call["metadata"] == {"source": "core"}


def test_on_llm_call_without_cached_tokens_is_backward_compatible(tmp_path: Any) -> None:
    from pig_coding_agent.billing import CostTracker

    ct = CostTracker(tmp_path)
    ct.on_llm_call(model="gpt-4o-mini", input_tokens=100, output_tokens=10)
    summary = ct.get_usage_summary()
    assert summary["total_llm_calls"] == 1
    assert summary["total_cached_tokens"] == 0
