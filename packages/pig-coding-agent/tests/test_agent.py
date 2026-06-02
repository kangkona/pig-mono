"""Tests for CodingAgent."""

from unittest.mock import Mock, patch

import pytest
from pig_agent_core import Session
from pig_coding_agent.agent import CodingAgent, SessionExitRequested


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_coding_agent_creation(mock_llm, temp_workspace):
    """Test creating a coding agent."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )

    assert agent.workspace == temp_workspace
    assert agent.llm == mock_llm
    assert agent.agent is not None


def test_coding_agent_default_llm(temp_workspace):
    """Test agent with default LLM."""
    with patch("pig_coding_agent.agent.LLM") as mock_llm_class:
        mock_llm = Mock()
        mock_llm_class.return_value = mock_llm

        agent = CodingAgent(workspace=str(temp_workspace))
        assert agent.llm == mock_llm


def test_coding_agent_has_tools(mock_llm, temp_workspace):
    """Test agent has required tools."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    # Agent should have tools from FileTools, CodeTools, ShellTools
    assert len(agent.agent.registry) > 0

    # Check for some expected tools
    tool_names = agent.agent.registry.list_tools()
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "list_files" in tool_names


def test_coding_agent_system_prompt(mock_llm, temp_workspace):
    """Test agent has proper system prompt."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    system_prompt = agent._get_system_prompt()
    assert "coding assistant" in system_prompt.lower()
    assert str(temp_workspace) in system_prompt


def test_coding_agent_run_once(mock_llm, temp_workspace):
    """Test running agent once."""
    # Mock the agent's run method
    with patch("pig_coding_agent.agent.Agent") as mock_agent_class:
        mock_agent_instance = Mock()
        mock_agent_instance.run = Mock(return_value=Mock(content="Test response"))
        mock_agent_class.return_value = mock_agent_instance

        agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
        result = agent.run_once("Create a hello world function")

        assert result == "Test response"
        mock_agent_instance.run.assert_called_once()


def test_coding_agent_handle_exit_command(mock_llm, temp_workspace):
    """Test handling exit command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    with pytest.raises(SessionExitRequested):
        agent._handle_command("/exit")


def test_coding_agent_handle_quit_command(mock_llm, temp_workspace):
    """Test handling quit command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    with pytest.raises(SessionExitRequested):
        agent._handle_command("/quit")


def test_coding_agent_handle_clear_command(mock_llm, temp_workspace):
    """Test handling clear command."""
    with patch("pig_coding_agent.agent.Agent") as mock_agent_class:
        mock_agent_instance = Mock()
        mock_agent_class.return_value = mock_agent_instance

        agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
        agent._handle_command("/clear")

        mock_agent_instance.clear_history.assert_called_once()


def test_coding_agent_handle_help_command(mock_llm, temp_workspace):
    """Test handling help command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()

    # Should not raise
    agent._handle_command("/help")
    agent.ui.panel.assert_called()


def test_coding_agent_handle_files_command(mock_llm, temp_workspace):
    """Test handling files command."""
    # Create some test files
    (temp_workspace / "test.txt").write_text("content")

    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/files")

    agent.ui.panel.assert_called()


def test_coding_agent_handle_status_command(mock_llm, temp_workspace):
    """Test handling status command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/status")

    agent.ui.panel.assert_called()


def test_coding_agent_handle_unknown_command(mock_llm, temp_workspace):
    """Test handling unknown command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/unknown")

    agent.ui.error.assert_called()


def test_coding_agent_verbose_mode(mock_llm, temp_workspace):
    """Test agent in verbose mode."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=True,
    )

    assert agent.verbose is True
    assert agent.agent.verbose is True


def test_coding_agent_reuses_existing_session_by_session_id(mock_llm, temp_workspace):
    session = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "hello")
    save_path = session.save()
    assert save_path.exists()

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id=session.id,
    )

    assert agent.session.id == session.id
    assert agent.session.name == "existing"
    assert len(agent.session.tree.entries) == 1


def test_coding_agent_creates_new_session_when_session_id_missing(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id="manual-session-id",
    )

    assert agent.session.id == "manual-session-id"


def test_coding_agent_uses_env_session_dir_for_new_sessions(mock_llm, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(session_dir))

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
    )

    saved = agent.session.save()
    assert saved.parent == session_dir


def test_coding_agent_fork_keeps_explicit_session_id(mock_llm, temp_workspace):
    source = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    source.add_message("user", "hello")
    source.add_message("assistant", "world")
    session_path = source.save()

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id="fork-target-id",
        fork_source_path=session_path,
    )

    assert agent.session.id == "fork-target-id"
    assert agent.session.name == "existing-fork"
    assert len(agent.session.tree.entries) == 2


def test_coding_agent_verbose_false_suppresses_startup_prints_on_resume(mock_llm, temp_workspace):
    session = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "hello")
    session_path = session.save()

    mock_skill_manager = Mock()
    mock_skill_manager.__len__ = Mock(return_value=2)
    mock_prompt_manager = Mock()
    mock_prompt_manager.__len__ = Mock(return_value=3)

    with (
        patch("pig_coding_agent.agent.SkillManager", return_value=mock_skill_manager),
        patch("pig_coding_agent.agent.PromptManager", return_value=mock_prompt_manager),
        patch("builtins.print") as mock_print,
    ):
        CodingAgent(
            llm=mock_llm,
            workspace=str(temp_workspace),
            verbose=False,
            session_path=session_path,
        )

    mock_print.assert_not_called()


def test_coding_agent_rejects_invalid_manual_session_id(mock_llm, temp_workspace):
    with pytest.raises(ValueError, match="Session id must be non-empty"):
        CodingAgent(
            llm=mock_llm,
            workspace=str(temp_workspace),
            verbose=False,
            session_id="-bad",
        )
