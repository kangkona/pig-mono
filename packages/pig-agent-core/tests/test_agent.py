"""Tests for Agent class."""

import pytest
from unittest.mock import Mock, patch
from pig_agent_core import Agent, tool
from pig_agent_core.models import AgentState


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm


def test_agent_creation(mock_llm):
    """Test creating an agent."""
    agent = Agent(name="TestAgent", llm=mock_llm)
    assert agent.name == "TestAgent"
    assert agent.llm == mock_llm
    assert len(agent.history) == 0


def test_agent_with_system_prompt(mock_llm):
    """Test agent with system prompt."""
    agent = Agent(
        name="TestAgent",
        llm=mock_llm,
        system_prompt="You are helpful",
    )
    assert len(agent.history) == 1
    assert agent.history[0].role == "system"
    assert agent.history[0].content == "You are helpful"


def test_agent_add_tool(mock_llm):
    """Test adding a tool to agent."""
    @tool
    def my_tool(x: int) -> int:
        return x * 2
    
    agent = Agent(llm=mock_llm)
    agent.add_tool(my_tool)
    
    assert len(agent.registry) == 1
    assert "my_tool" in agent.registry


def test_agent_with_tools(mock_llm):
    """Test agent initialized with tools."""
    @tool
    def tool1(x: int) -> int:
        return x
    
    @tool
    def tool2(x: int) -> int:
        return x * 2
    
    agent = Agent(llm=mock_llm, tools=[tool1, tool2])
    assert len(agent.registry) == 2


def test_agent_clear_history(mock_llm):
    """Test clearing agent history."""
    agent = Agent(
        llm=mock_llm,
        system_prompt="System",
    )
    
    from pig_llm.models import Message
    agent.history.append(Message(role="user", content="Hello"))
    agent.history.append(Message(role="assistant", content="Hi"))
    
    assert len(agent.history) == 3  # system + user + assistant
    
    agent.clear_history()
    
    # Should keep system prompt
    assert len(agent.history) == 1
    assert agent.history[0].role == "system"


def test_agent_get_state(mock_llm):
    """Test getting agent state."""
    agent = Agent(
        name="TestAgent",
        llm=mock_llm,
        system_prompt="System prompt",
    )
    
    state = agent.get_state()
    assert isinstance(state, AgentState)
    assert state.name == "TestAgent"
    assert state.system_prompt == "System prompt"


def test_agent_save_load_state(mock_llm, tmp_path):
    """Test saving and loading agent state."""
    # Create agent
    agent1 = Agent(
        name="TestAgent",
        llm=mock_llm,
        system_prompt="System",
    )
    
    from pig_llm.models import Message
    agent1.history.append(Message(role="user", content="Hello"))
    
    # Save state
    state_file = tmp_path / "state.json"
    agent1.save_state(state_file)
    
    assert state_file.exists()
    
    # Load state
    agent2 = Agent.from_state(state_file, llm=mock_llm)
    
    assert agent2.name == "TestAgent"
    assert agent2.system_prompt == "System"
    assert len(agent2.history) == 2  # system + user


def test_agent_max_iterations(mock_llm):
    """Test max iterations parameter."""
    agent = Agent(llm=mock_llm, max_iterations=5)
    assert agent.max_iterations == 5
