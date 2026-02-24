"""Integration tests for py-coding-agent with session/extension/skills."""

from unittest.mock import Mock

import pytest
from pig_coding_agent.agent import CodingAgent


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")
    return llm


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_coding_agent_with_session(mock_llm, temp_workspace):
    """Test coding agent with session management."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="test-session",
        verbose=False,
    )

    # Session should be created
    assert agent.session is not None
    assert agent.session.name == "test-session"


def test_coding_agent_load_existing_session(mock_llm, temp_workspace):
    """Test loading existing session."""
    # Create a session first
    agent1 = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="existing",
        verbose=False,
    )

    session_path = agent1.session.save()

    # Load it
    agent2 = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_path=session_path,
        verbose=False,
    )

    assert agent2.session.name == "existing"


def test_coding_agent_with_extensions(mock_llm, temp_workspace):
    """Test coding agent with extensions."""
    # Create extension
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)

    ext_file = ext_dir / "test_ext.py"
    ext_file.write_text("""
def extension(api):
    @api.tool(description="Test tool")
    def test_tool(x: int) -> int:
        return x * 2

    @api.command("test")
    def test_cmd():
        return "Test command executed"
""")

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
    )

    # Extension should be loaded
    assert agent.extension_manager is not None
    assert len(agent.extension_manager.extensions) > 0


def test_coding_agent_with_skills(mock_llm, temp_workspace):
    """Test coding agent with skills."""
    # Create skill
    skill_dir = temp_workspace / ".agents" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("""# Test Skill

This is a test skill.

## Steps
1. Do this
2. Do that
""")

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_skills=True,
        verbose=False,
    )

    # Manually discover skills in the temp workspace
    agent.skill_manager.discover_skills([temp_workspace / ".agents" / "skills"])

    # Skill should be loaded
    assert agent.skill_manager is not None
    assert "test-skill" in agent.skill_manager


def test_tree_command(mock_llm, temp_workspace):
    """Test /tree command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )
    agent.ui = Mock()

    # Add some messages to session
    agent.session.add_message("user", "Hello")
    agent.session.add_message("assistant", "Hi")

    # Run /tree command
    agent._handle_command("/tree")

    # Should call ui.panel
    agent.ui.panel.assert_called()


def test_fork_command(mock_llm, temp_workspace):
    """Test /fork command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )

    agent.session.add_message("user", "Message")

    # Run /fork command
    agent._handle_command("/fork test-fork")

    # Should save the fork
    fork_file = temp_workspace / ".sessions" / "test-fork.jsonl"
    assert fork_file.exists()


def test_compact_command(mock_llm, temp_workspace):
    """Test /compact command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )
    agent.ui = Mock()

    # Add many messages
    for i in range(15):
        agent.session.add_message("user", f"Message {i}")

    len(agent.session.tree.entries)

    # Run /compact
    agent._handle_command("/compact")

    # Should show system message
    agent.ui.system.assert_called()


def test_session_command(mock_llm, temp_workspace):
    """Test /session command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="test",
        verbose=False,
    )
    agent.ui = Mock()

    agent._handle_command("/session")

    # Should display session info
    agent.ui.panel.assert_called()


def test_skills_command(mock_llm, temp_workspace):
    """Test /skills command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_skills=True,
        verbose=False,
    )
    agent.ui = Mock()

    agent._list_skills()

    # Should show skills info (panel if skills found, system if empty, error if disabled)
    assert agent.ui.system.called or agent.ui.panel.called or agent.ui.error.called


def test_extensions_command(mock_llm, temp_workspace):
    """Test /extensions command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
    )
    agent.ui = Mock()

    agent._handle_command("/extensions")

    # Should show extensions (even if empty)
    agent.ui.system.assert_called()


def test_skill_invocation(mock_llm, temp_workspace):
    """Test invoking a skill."""
    # Create skill
    skill_dir = temp_workspace / ".agents" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# My Skill\nDescription\n## Steps\n1. Step")

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_skills=True,
        verbose=False,
    )
    agent.ui = Mock()
    agent.skill_manager.discover_skills([temp_workspace / ".agents" / "skills"])

    agent._handle_command("/skill:my-skill")

    # Should show skill panel
    agent.ui.panel.assert_called()
