"""Integration tests for pig-mono packages."""

from unittest.mock import patch


def test_ai_to_agent_integration():
    """Test pig-ai integration with pig-agent-core."""
    from pig_agent_core import Agent, tool
    from pig_llm import LLM

    # Mock LLM
    with patch("pig_llm.providers.openai.OpenAIProvider"):
        llm = LLM(provider="openai", api_key="test")

        @tool
        def test_tool(x: int) -> int:
            return x * 2

        agent = Agent(llm=llm, tools=[test_tool])

        assert agent.llm == llm
        assert len(agent.registry) == 1


def test_agent_to_tui_integration():
    """Test pig-agent-core integration with pig-tui."""
    from pig_agent_core import Agent
    from pig_tui import ChatUI

    with patch("pig_llm.providers.openai.OpenAIProvider"):
        from pig_llm import LLM

        llm = LLM(provider="openai", api_key="test")
        Agent(llm=llm)

    # Create chat UI
    chat = ChatUI(title="Test")

    # Simulate conversation
    chat.user("Hello")
    chat.assistant("Hi")

    assert chat.title == "Test"


def test_agent_to_webui_integration():
    """Test pig-agent-core integration with pig-web-ui."""
    from pig_agent_core import Agent
    from pig_web_ui import ChatServer

    with patch("pig_llm.providers.openai.OpenAIProvider"):
        from pig_llm import LLM

        llm = LLM(provider="openai", api_key="test")
        agent = Agent(llm=llm)

    server = ChatServer(agent=agent)

    assert server.agent == agent


def test_full_stack_integration():
    """Test full stack integration."""
    from pig_agent_core import Agent, tool
    from pig_llm import LLM
    from pig_web_ui import ChatServer

    # Create tool
    @tool(description="Double a number")
    def double(x: int) -> int:
        return x * 2

    # Create LLM and agent
    with patch("pig_llm.providers.openai.OpenAIProvider"):
        llm = LLM(provider="openai", api_key="test")
        agent = Agent(
            name="TestAgent",
            llm=llm,
            tools=[double],
            system_prompt="You are helpful",
        )

    # Create server
    server = ChatServer(agent=agent, title="Full Stack Test")

    assert server.agent == agent
    assert len(agent.registry) == 1
    assert "double" in agent.registry


def test_data_model_compatibility():
    """Test data models are compatible across packages."""
    from pig_agent_core.models import AgentState
    from pig_llm.models import Message, Response
    from pig_web_ui.models import ChatMessage

    # Test Message creation
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"

    # Test Response
    resp = Response(content="Hi", model="test")
    assert resp.content == "Hi"

    # Test ChatMessage
    chat_msg = ChatMessage(role="user", content="Hello")
    assert chat_msg.role == "user"

    # Test AgentState
    state = AgentState(name="Test")
    assert state.name == "Test"
