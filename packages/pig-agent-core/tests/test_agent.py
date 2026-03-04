"""Tests for Agent class."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
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


@pytest.mark.asyncio
async def test_agent_respond_stream_basic():
    """Test basic streaming response without tool calls."""
    # Create mock LLM with streaming support
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")

    # Mock streaming response
    async def mock_stream():
        # Simulate streaming chunks
        chunk1 = Mock()
        chunk1.choices = [Mock()]
        chunk1.choices[0].delta = Mock()
        chunk1.choices[0].delta.content = "Hello"
        chunk1.choices[0].delta.tool_calls = None

        chunk2 = Mock()
        chunk2.choices = [Mock()]
        chunk2.choices[0].delta = Mock()
        chunk2.choices[0].delta.content = " world"
        chunk2.choices[0].delta.tool_calls = None

        yield chunk1
        yield chunk2

    mock_llm.achat_stream = AsyncMock(return_value=mock_stream())

    agent = Agent(llm=mock_llm)

    # Test streaming
    chunks = []
    async for chunk in agent.respond_stream("Hello"):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]
    assert len(agent.history) == 2  # user + assistant


@pytest.mark.asyncio
async def test_agent_respond_non_streaming():
    """Test non-streaming respond method."""
    # Create mock LLM with streaming support
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")

    # Mock streaming response
    async def mock_stream():
        chunk1 = Mock()
        chunk1.choices = [Mock()]
        chunk1.choices[0].delta = Mock()
        chunk1.choices[0].delta.content = "Complete"
        chunk1.choices[0].delta.tool_calls = None

        chunk2 = Mock()
        chunk2.choices = [Mock()]
        chunk2.choices[0].delta = Mock()
        chunk2.choices[0].delta.content = " response"
        chunk2.choices[0].delta.tool_calls = None

        yield chunk1
        yield chunk2

    mock_llm.achat_stream = AsyncMock(return_value=mock_stream())

    agent = Agent(llm=mock_llm)

    # Test non-streaming
    response = await agent.respond("Hello")

    assert response == "Complete response"
    assert len(agent.history) == 2  # user + assistant


@pytest.mark.asyncio
async def test_agent_respond_with_cancellation():
    """Test cancellation support."""
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")

    # Mock streaming response
    async def mock_stream():
        chunk = Mock()
        chunk.choices = [Mock()]
        chunk.choices[0].delta = Mock()
        chunk.choices[0].delta.content = "Should not see this"
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_llm.achat_stream = AsyncMock(return_value=mock_stream())

    agent = Agent(llm=mock_llm)

    # Create cancel event and set it immediately
    cancel = asyncio.Event()
    cancel.set()

    # Test cancellation
    chunks = []
    async for chunk in agent.respond_stream("Hello", cancel=cancel):
        chunks.append(chunk)

    assert chunks == ["Request was cancelled."]
