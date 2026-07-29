"""Tests for Agent class."""

import asyncio
from unittest.mock import Mock

import pytest
from pig_agent_core import Agent, tool
from pig_agent_core.models import AgentState
from pig_llm import StreamChunk


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
    schemas = agent.registry.get_schemas()
    assert [schema["function"]["name"] for schema in schemas] == ["my_tool"]


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

    # Mock streaming response (StreamChunk shape: text deltas as .content)
    async def mock_stream(*, messages, **kwargs):
        del messages, kwargs
        yield StreamChunk(content="Hello")
        yield StreamChunk(content=" world")

    mock_llm.achat_stream = mock_stream

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

    # Mock streaming response (StreamChunk shape)
    async def mock_stream(*, messages, **kwargs):
        del messages, kwargs
        yield StreamChunk(content="Complete")
        yield StreamChunk(content=" response")

    mock_llm.achat_stream = mock_stream

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
    async def mock_stream(*, messages, **kwargs):
        del messages, kwargs
        chunk = Mock()
        chunk.choices = [Mock()]
        chunk.choices[0].delta = Mock()
        chunk.choices[0].delta.content = "Should not see this"
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_llm.achat_stream = mock_stream

    agent = Agent(llm=mock_llm)

    # Create cancel event and set it immediately
    cancel = asyncio.Event()
    cancel.set()

    # Test cancellation: aborts cleanly, yielding nothing (no fake message).
    chunks = []
    async for chunk in agent.respond_stream("Hello", cancel=cancel):
        chunks.append(chunk)

    assert chunks == []


def _mock_llm_returning(content):
    llm = Mock()
    llm.config = Mock(model="test-model")
    llm.chat.return_value = Mock(content=content, tool_calls=None)
    return llm


def test_verbose_log_renders_through_attached_ui_without_duplicate_turns():
    """With a UI attached, turn echoes are suppressed and markup is rendered.

    Regression: core Agent._log used a raw print(), so it (a) double-printed
    User/Agent lines already shown by the UI and (b) emitted literal Rich
    markup tags like '[bold blue]'.
    """
    import io

    from rich.console import Console

    ui = Mock()
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=80)

    agent = Agent(llm=_mock_llm_returning("hi"), verbose=True)
    agent.ui = ui

    captured = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(captured):
        agent.run("ping")

    stdout_text = captured.getvalue()
    ui_text = ui.console.file.getvalue()

    # UI owns turn rendering -> no raw stdout echoes
    assert "User:" not in stdout_text
    assert "Agent:" not in stdout_text
    # Markup must be rendered, never emitted literally
    assert "[bold blue]" not in stdout_text
    assert "[bold blue]" not in ui_text
    # Execution trace still surfaces, now through the Rich console
    assert "Iteration" in ui_text


def test_verbose_log_does_not_parse_arbitrary_content_as_markup():
    """Tool output containing '[...]' must render verbatim, never as Rich markup.

    Regression: routing _log through the Rich console parsed interpolated
    content as markup, which swallowed '[tag]'-looking substrings and raised
    MarkupError on unbalanced tags like '[/]'.
    """
    import io

    from rich.console import Console

    ui = Mock()
    ui.console = Console(file=io.StringIO(), force_terminal=True, width=100)

    agent = Agent(llm=_mock_llm_returning("hi"), verbose=True)
    agent.ui = ui

    # Adversarial content that previously broke rendering
    agent._log("✓ Result: WARN [deprecated] see [/] for details", style="green")

    out = ui.console.file.getvalue()
    assert "[deprecated]" in out  # not swallowed
    assert "[/]" in out  # did not raise MarkupError
    assert "[green]" not in out  # style applied via style=, not as a literal tag
    assert "\x1b[32m" in out  # green actually applied


def test_verbose_log_falls_back_to_print_without_ui():
    """Headless library use keeps printing turns + trace (unchanged behavior)."""
    import contextlib
    import io

    agent = Agent(llm=_mock_llm_returning("hi"), verbose=True)

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        agent.run("ping")

    text = captured.getvalue()
    assert "User:" in text
    assert "Agent:" in text
    assert "Iteration" in text


def test_format_tool_args_truncates_long_values():
    """Long tool-call argument values are previewed + char-counted, not dumped."""
    out = Agent._format_tool_args({"content": "A" * 5000, "path": "index.html"})
    assert "(5000 chars)" in out
    assert out.count("A") < 200  # preview only, not the whole 5000
    assert "path='index.html'" in out


def test_format_tool_args_keeps_short_values():
    out = Agent._format_tool_args({"pattern": "foo", "path": "."})
    assert out == "pattern='foo', path='.'"
