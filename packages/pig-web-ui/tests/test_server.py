"""Tests for chat server."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from pig_web_ui.server import ChatServer


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    llm.complete = Mock(return_value=Mock(content="Test response"))
    return llm


def test_server_creation_with_llm(mock_llm):
    """Test creating server with LLM."""
    server = ChatServer(llm=mock_llm, title="Test")
    assert server.title == "Test"
    assert server.llm == mock_llm
    assert server.port == 8000


def test_server_creation_requires_llm_or_agent():
    """Test server requires either LLM or agent."""
    with pytest.raises(ValueError, match="Must provide either llm or agent"):
        ChatServer()


def test_server_creation_with_custom_port(mock_llm):
    """Test server with custom port."""
    server = ChatServer(llm=mock_llm, port=8080)
    assert server.port == 8080


def test_server_creation_with_cors(mock_llm):
    """Test server with CORS enabled."""
    server = ChatServer(llm=mock_llm, cors=True)
    # CORS middleware should be added
    assert any(
        m.cls.__name__ == "CORSMiddleware"
        for m in server.app.user_middleware
    )


def test_server_routes(mock_llm):
    """Test server has required routes."""
    server = ChatServer(llm=mock_llm)
    client = TestClient(server.app)
    
    # Test home page
    response = client.get("/")
    assert response.status_code == 200
    
    # Test history endpoint
    response = client.get("/api/history")
    assert response.status_code == 200
    assert "messages" in response.json()


def test_server_clear_history(mock_llm):
    """Test clearing history."""
    server = ChatServer(llm=mock_llm)
    client = TestClient(server.app)
    
    # Add some history
    server.history.append(Mock())
    assert len(server.history) > 0
    
    # Clear history
    response = client.delete("/api/history")
    assert response.status_code == 200
    assert len(server.history) == 0


def test_server_format_sse(mock_llm):
    """Test SSE formatting."""
    from pig_web_ui.models import StreamChunk
    
    server = ChatServer(llm=mock_llm)
    chunk = StreamChunk(type="token", content="Hello")
    
    sse = server._format_sse(chunk)
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    assert "Hello" in sse


def test_server_with_agent():
    """Test server with agent."""
    mock_agent = Mock()
    mock_agent.run = Mock(return_value=Mock(content="Agent response"))
    
    server = ChatServer(agent=mock_agent)
    assert server.agent == mock_agent
    assert server.llm is None


def test_server_theme(mock_llm):
    """Test server with custom theme."""
    theme = {"primary_color": "#ff0000"}
    server = ChatServer(llm=mock_llm, theme=theme)
    assert server.theme == theme
