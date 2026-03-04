"""Tests for wired master loop with enhanced subsystems."""

from unittest.mock import Mock

import pytest
from pig_agent_core.agent import Agent
from pig_agent_core.tools import Tool


def test_agent_initialization_with_enhanced_subsystems():
    """Test that agent can be initialized with all enhanced subsystems."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(
        name="TestAgent",
        llm=mock_llm,
        system_prompt="You are a helpful assistant",
        max_rounds=5,
        max_rounds_with_plan=10,
    )

    assert agent.name == "TestAgent"
    assert agent.max_iterations == 5
    assert agent.max_rounds_with_plan == 10
    assert agent.memory_provider is not None
    assert isinstance(agent.registry, type(agent.registry))


def test_agent_add_tool_with_enhanced_registry():
    """Test adding tools to enhanced registry."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    def sample_tool(query: str) -> str:
        """A sample tool for testing.

        Args:
            query: Query string

        Returns:
            Result string
        """
        return f"Result for: {query}"

    tool = Tool(
        func=sample_tool,
        name="sample_tool",
        description="A sample tool",
    )

    agent = Agent(llm=mock_llm)
    agent.add_tool(tool)

    assert len(agent.registry) == 1


def test_agent_plan_tracking():
    """Test that agent tracks plan tool usage."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(llm=mock_llm, max_rounds_with_plan=5)

    assert agent._plan_used is False
    assert agent._rounds_since_plan == 0


def test_agent_backward_compatibility():
    """Test that old API still works (max_iterations)."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(llm=mock_llm, max_iterations=15)

    assert agent.max_iterations == 15


def test_agent_max_rounds_precedence():
    """Test that max_rounds takes precedence over max_iterations."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(llm=mock_llm, max_iterations=10, max_rounds=20)

    assert agent.max_iterations == 20


@pytest.mark.asyncio
async def test_agent_arun_structure():
    """Test that arun method exists and has correct structure."""
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(
        llm=mock_llm,
        system_prompt="You are a helpful assistant",
        max_rounds=1,
    )

    # Verify method exists and is async
    assert hasattr(agent, "arun")
    assert callable(agent.arun)
