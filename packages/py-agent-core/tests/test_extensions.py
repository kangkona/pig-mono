"""Tests for extension system."""

import pytest
from unittest.mock import Mock
from pathlib import Path
from py_agent_core import Agent, ExtensionAPI, ExtensionManager, tool


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = Mock()
    agent.add_tool = Mock()
    agent.registry = Mock()
    agent.registry.list_tools = Mock(return_value=[])
    return agent


def test_extension_api_creation(mock_agent):
    """Test creating extension API."""
    api = ExtensionAPI(mock_agent)
    assert api.agent == mock_agent


def test_extension_api_register_tool(mock_agent):
    """Test registering a tool via API."""
    api = ExtensionAPI(mock_agent)
    
    @tool
    def my_tool(x: int) -> int:
        return x * 2
    
    api.register_tool(my_tool)
    mock_agent.add_tool.assert_called_once_with(my_tool)


def test_extension_api_tool_decorator(mock_agent):
    """Test @api.tool decorator."""
    api = ExtensionAPI(mock_agent)
    
    @api.tool(description="Double a number")
    def double(x: int) -> int:
        return x * 2
    
    mock_agent.add_tool.assert_called_once()


def test_extension_api_register_command(mock_agent):
    """Test registering a command."""
    api = ExtensionAPI(mock_agent)
    
    def my_command():
        return "Command executed"
    
    api.register_command("test", my_command, "Test command")
    
    commands = api.get_commands()
    assert "test" in commands
    assert commands["test"]() == "Command executed"


def test_extension_api_command_decorator(mock_agent):
    """Test @api.command decorator."""
    api = ExtensionAPI(mock_agent)
    
    @api.command("stats", "Show stats")
    def show_stats():
        return "Stats"
    
    commands = api.get_commands()
    assert "stats" in commands


def test_extension_api_event_handler(mock_agent):
    """Test registering event handler."""
    api = ExtensionAPI(mock_agent)
    
    called = []
    
    @api.on("test_event")
    def handler(event, context):
        called.append(event)
    
    api.emit("test_event", {"data": "test"})
    
    assert len(called) == 1
    assert called[0]["data"] == "test"


def test_extension_api_multiple_handlers(mock_agent):
    """Test multiple handlers for same event."""
    api = ExtensionAPI(mock_agent)
    
    calls = []
    
    @api.on("event")
    def handler1(event, ctx):
        calls.append(1)
    
    @api.on("event")
    def handler2(event, ctx):
        calls.append(2)
    
    api.emit("event", {})
    
    assert calls == [1, 2]


def test_extension_manager_creation(mock_agent):
    """Test creating extension manager."""
    manager = ExtensionManager(mock_agent)
    assert manager.agent == mock_agent
    assert isinstance(manager.api, ExtensionAPI)


def test_extension_manager_handle_command(mock_agent):
    """Test handling commands via manager."""
    manager = ExtensionManager(mock_agent)
    
    @manager.api.command("test")
    def test_command():
        return "Test result"
    
    result = manager.handle_command("test")
    assert result == "Test result"


def test_extension_manager_handle_unknown_command(mock_agent):
    """Test handling unknown command."""
    manager = ExtensionManager(mock_agent)
    
    with pytest.raises(ValueError, match="Unknown command"):
        manager.handle_command("unknown")


def test_extension_manager_emit_event(mock_agent):
    """Test emitting events via manager."""
    manager = ExtensionManager(mock_agent)
    
    called = []
    
    @manager.api.on("test")
    def handler(event, ctx):
        called.append(event)
    
    manager.emit_event("test", {"data": "value"})
    
    assert len(called) == 1


def test_extension_manager_load_extension(mock_agent, tmp_path):
    """Test loading extension from file."""
    manager = ExtensionManager(mock_agent)
    
    # Create extension file
    ext_file = tmp_path / "test_ext.py"
    ext_file.write_text("""
def extension(api):
    @api.tool(description="Test tool")
    def test_tool(x: int) -> int:
        return x * 2
    
    @api.command("hello")
    def hello_cmd():
        return "Hello!"
""")
    
    # Load extension
    manager.load_extension(ext_file)
    
    # Verify tool was registered
    assert mock_agent.add_tool.called
    
    # Verify command was registered
    commands = manager.api.get_commands()
    assert "hello" in commands


def test_extension_manager_discover(mock_agent, tmp_path):
    """Test discovering extensions."""
    manager = ExtensionManager(mock_agent)
    
    # Create extension directory
    ext_dir = tmp_path / "extensions"
    ext_dir.mkdir()
    
    # Create extension files
    (ext_dir / "ext1.py").write_text("def extension(api): pass")
    (ext_dir / "ext2.py").write_text("def extension(api): pass")
    (ext_dir / "_private.py").write_text("# Should be skipped")
    
    # Discover
    extensions = manager.discover_extensions(ext_dir)
    
    assert len(extensions) == 2  # Should skip _private.py
