"""Integration tests for py-coding-agent with session/extension/skills."""

import json
from unittest.mock import Mock, patch

import pytest
from pig_agent_core import ExtensionManager
from pig_coding_agent.agent import CodingAgent
from pig_tui import (
    EditorSession,
    SelectionEditorSession,
    SelectionEditResult,
    SelectionSession,
    SelectOption,
    TreeBrowserResult,
    TreeBrowserSession,
    hyperlink,
)


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
        project_trust=True,
    )

    # Extension should be loaded
    assert agent.extension_manager is not None
    assert len(agent.extension_manager.extensions) > 0


def test_coding_agent_emits_session_start_on_extension_startup(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "session_events.log"

    ext_file = ext_dir / "session_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"start:{{event['reason']}}\\n")
"""
    )

    CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )

    assert log_file.read_text().splitlines() == ["start:startup"]


def test_coding_agent_emits_resume_session_start_when_loading_existing_session(
    mock_llm, temp_workspace
):
    session = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="existing",
        verbose=False,
        enable_extensions=False,
    ).session
    session_path = session.save()

    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "resume_events.log"

    ext_file = ext_dir / "resume_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"start:{{event['reason']}}\\n")
"""
    )

    CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_path=session_path,
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )

    assert log_file.read_text().splitlines() == ["start:resume"]


def test_coding_agent_resume_session_start_includes_previous_session_file(mock_llm, temp_workspace):
    session = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="existing",
        verbose=False,
        enable_extensions=False,
    ).session
    session_path = session.save()

    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "resume_previous_session.log"

    ext_file = ext_dir / "resume_previous_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"previous:{{event.get('previousSessionFile')}}\\n")
"""
    )

    CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_path=session_path,
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )

    assert log_file.read_text().splitlines() == [f"previous:{session_path}"]


def test_coding_agent_emits_fork_session_start_when_loading_fork_target(mock_llm, temp_workspace):
    source = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="existing",
        verbose=False,
        enable_extensions=False,
    ).session
    source.add_message("user", "Message 1")
    source.add_message("assistant", "Response 1")
    session_path = source.save()

    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "fork_session_start.log"

    ext_file = ext_dir / "fork_start_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                f"start:{{event['reason']}}:{{event.get('previousSessionFile')}}:"
                f"{{api.agent.session.name}}\\n"
            )
"""
    )

    CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_path=session_path,
        enable_extensions=True,
        verbose=False,
        fork_source_path=session_path,
        project_trust=True,
    )

    assert log_file.read_text().splitlines() == [f"start:fork:{session_path}:existing-fork"]


def test_coding_agent_session_start_handlers_can_access_ui(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "session_ui_ready.log"

    ext_file = ext_dir / "ui_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        ui_ready = hasattr(api.agent, "ui")
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"ui_ready:{{ui_ready}}\\n")
"""
    )

    CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )

    assert log_file.read_text().splitlines() == ["ui_ready:True"]


def test_excluded_tools_filter_extension_tools_registered_on_session_start(
    mock_llm, temp_workspace
):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)

    ext_file = ext_dir / "excluded_ext.py"
    ext_file.write_text(
        """
def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        @api.tool(name="ask_question", description="Ask a question")
        def ask_question() -> str:
            return "nope"

        @api.tool(name="dynamic_tool", description="Dynamic test tool")
        def dynamic_tool() -> str:
            return "ok"
"""
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        excluded_tools={"ask_question"},
        project_trust=True,
    )

    schemas = agent.agent.registry.get_schemas()
    schema_names = sorted(schema["function"]["name"] for schema in schemas)

    assert "ask_question" not in schema_names
    assert "dynamic_tool" in schema_names
    assert "ask_question" not in agent.agent.registry
    assert "dynamic_tool" in agent.agent.registry


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
    fork_files = list((temp_workspace / ".sessions").glob("test-fork-*.jsonl"))
    assert len(fork_files) == 1


def test_fork_command_switches_current_session_and_emits_fork_lifecycle(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "fork_events.log"

    ext_file = ext_dir / "fork_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                f"start:{{event['reason']}}:{{event.get('previousSessionFile')}}:"
                f"{{api.agent.session.name}}\\n"
            )

    @api.on("session_shutdown")
    def on_shutdown(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                f"shutdown:{{event['reason']}}:{{event.get('targetSessionFile')}}\\n"
            )
"""
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="original",
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )
    agent.ui = Mock()
    agent.session.add_message("user", "Message")
    previous_session_file = agent.session.save()

    agent._handle_command("/fork test-fork")

    assert agent.session.name == "test-fork"
    assert log_file.read_text().splitlines() == [
        "start:startup:None:original",
        f"shutdown:fork:{previous_session_file}",
        f"start:fork:{previous_session_file}:test-fork",
    ]


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

    agent.interaction_runtime.views.list_skills()

    # Should show skills info (panel if skills found, system if empty, error if disabled)
    assert agent.ui.system.called or agent.ui.panel.called or agent.ui.error.called


def test_extensions_command(mock_llm, temp_workspace):
    """Test /extensions command."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )
    agent.ui = Mock()

    agent._handle_command("/extensions")

    # Should show extensions (even if empty)
    agent.ui.system.assert_called()


def test_reload_resources_clears_stale_extension_commands(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)

    ext_file = ext_dir / "test_ext.py"
    ext_file.write_text(
        """
def extension(api):
    @api.command("hello")
    def hello_cmd():
        return "Hello!"
"""
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )
    agent.ui = Mock()

    assert "hello" in agent.extension_manager.api.get_commands()

    ext_file.unlink()
    agent.interaction_runtime.commands.reload_resources()

    assert "hello" not in agent.extension_manager.api.get_commands()


def test_reload_resources_emits_session_shutdown_then_session_start(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "reload_events.log"

    ext_file = ext_dir / "reload_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"start:{{event['reason']}}\\n")

    @api.on("session_shutdown")
    def on_shutdown(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(
                f"shutdown:{{event['reason']}}:{{event.get('targetSessionFile')}}\\n"
            )
"""
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )
    agent.ui = Mock()
    session_path = agent.session.save()

    agent.interaction_runtime.commands.reload_resources()

    assert log_file.read_text().splitlines() == [
        "start:startup",
        f"shutdown:reload:{session_path}",
        "start:reload",
    ]


def test_export_session_uses_clickable_file_hyperlink_when_supported(
    mock_llm, temp_workspace, monkeypatch
):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )
    agent.ui = Mock()

    export_path = temp_workspace / "demo.html"

    monkeypatch.setenv("TERM_PROGRAM", "WezTerm")

    with patch("pig_agent_core.SessionExporter.export_to_html", return_value=export_path):
        agent._handle_command("/export")

    expected = hyperlink(
        str(export_path.absolute()),
        f"file://{export_path.absolute()}",
    )
    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert f"  Open in browser: {expected}" in messages


def test_reload_resources_clears_stale_extension_handlers(mock_llm, temp_workspace):
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)

    ext_file = ext_dir / "test_ext.py"
    ext_file.write_text(
        """
def extension(api):
    @api.on("message_received")
    def on_message(event, ctx):
        return None
"""
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=True,
        verbose=False,
        project_trust=True,
    )
    agent.ui = Mock()

    assert "message_received" in agent.extension_manager.api._event_handlers

    ext_file.unlink()
    agent.interaction_runtime.commands.reload_resources()

    assert "message_received" not in agent.extension_manager.api._event_handlers


def test_queue_command_reports_remaining_followups_after_single_drain(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )
    agent.ui = Mock()

    agent.agent.message_queue.add_followup("F1")
    agent.agent.message_queue.add_followup("F2")

    drained = agent.agent.message_queue.get_followup_messages()
    assert [m.content for m in drained] == ["F1"]

    agent.interaction_runtime.views.show_queue()

    agent.ui.panel.assert_called()
    queue_text = agent.ui.panel.call_args.args[0]
    assert "F2" in queue_text


def test_run_interactive_emits_session_shutdown_reason_on_eof(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = EOFError()

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        agent.run_interactive()

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_run_interactive_emits_session_shutdown_reason_on_interrupt(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = KeyboardInterrupt()

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        agent.run_interactive()

    agent.extension_manager.cleanup.assert_called_once_with(reason="interrupt")


def test_run_interactive_emits_session_shutdown_reason_on_clean_exit(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = ["/exit"]

    original_handle_command = agent._handle_command

    def wrapped_handle_command(command: str):
        original_handle_command(command)

    with (
        patch("pig_tui.runtime.PromptRuntime", return_value=prompt),
        patch.object(agent, "_handle_command", side_effect=wrapped_handle_command),
    ):
        agent.run_interactive()

    agent.extension_manager.cleanup.assert_called_once_with(reason="normal")


def test_run_interactive_prints_resume_hint_on_clean_exit(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = ["/exit"]

    original_handle_command = agent._handle_command

    def wrapped_handle_command(command: str):
        original_handle_command(command)

    with (
        patch("pig_tui.runtime.PromptRuntime", return_value=prompt),
        patch.object(agent, "_handle_command", side_effect=wrapped_handle_command),
    ):
        agent.run_interactive()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert any("Resume with:" in message for message in messages)
    assert any(agent.session.id in message for message in messages)


def test_run_interactive_prints_resume_hint_on_eof_exit(mock_llm, temp_workspace):
    """The resume hint must appear however the user exits (here: Ctrl-D / EOF)."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = EOFError()

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        agent.run_interactive()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert any("Resume with:" in message and agent.session.id in message for message in messages)


def test_run_interactive_resume_hint_includes_explicit_session_dir(mock_llm, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
        enable_extensions=False,
        session_dir=session_dir,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = ["/exit"]

    original_handle_command = agent._handle_command

    def wrapped_handle_command(command: str):
        original_handle_command(command)

    with (
        patch("pig_tui.runtime.PromptRuntime", return_value=prompt),
        patch.object(agent, "_handle_command", side_effect=wrapped_handle_command),
    ):
        agent.run_interactive()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert any("--session-id" in message for message in messages)
    assert any(f"--session-dir {session_dir}" in message for message in messages)


def test_run_interactive_cleans_up_extensions_on_shutdown(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = EOFError()

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        agent.run_interactive()

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_run_interactive_emits_session_shutdown_reason_on_terminal_loss(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = RuntimeError("lost terminal")

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        with pytest.raises(RuntimeError, match="lost terminal"):
            agent.run_interactive()

    agent.extension_manager.cleanup.assert_called_once_with(reason="lost_terminal")


def test_run_interactive_does_not_print_resume_hint_on_terminal_loss(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.ui = Mock()
    agent.extension_manager = Mock()

    prompt = Mock()
    prompt.ask.side_effect = RuntimeError("lost terminal")

    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        with pytest.raises(RuntimeError, match="lost terminal"):
            agent.run_interactive()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert all("To resume this session:" not in message for message in messages)


def test_shutdown_extensions_helper_emits_signal_reason_and_cleans_up(mock_llm, temp_workspace):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    agent.extension_manager = Mock()

    agent._shutdown_extensions("sigterm")

    agent.extension_manager.cleanup.assert_called_once_with(reason="sigterm")


def test_shutdown_extensions_helper_emits_signal_reason_once_with_real_extension_manager(
    mock_llm, temp_workspace
):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    manager = ExtensionManager(agent.agent)
    shutdown_events = []

    @manager.api.on("session_shutdown")
    def on_shutdown(event, ctx):
        shutdown_events.append(event)

    agent.extension_manager = manager

    agent._shutdown_extensions("sigterm")

    assert shutdown_events == [{"reason": "sigterm"}]


def test_shutdown_extensions_helper_is_idempotent_with_real_extension_manager(
    mock_llm, temp_workspace
):
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
    )
    manager = ExtensionManager(agent.agent)
    shutdown_events = []

    @manager.api.on("session_shutdown")
    def on_shutdown(event, ctx):
        shutdown_events.append(event)

    agent.extension_manager = manager

    agent._shutdown_extensions("sigterm")
    agent._shutdown_extensions("sigterm")

    assert shutdown_events == [{"reason": "sigterm"}]


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


def _stream_chunk(*, content="", tool_calls=None):
    from pig_llm import StreamChunk

    return StreamChunk(content=content, tool_calls=tool_calls)


def test_run_turn_streams_tokens_and_records_session(mock_llm, temp_workspace):
    """_run_turn streams tokens via the writer and records user + assistant."""
    import asyncio

    def achat_stream(messages, tools=None):
        async def stream():
            yield _stream_chunk(content="hello ")
            yield _stream_chunk(content="world")

        return stream()

    mock_llm.achat_stream = achat_stream

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="turn-test",
        verbose=False,
        enable_skills=False,
        enable_extensions=False,
    )
    written = []
    agent.ui = Mock()
    writer = Mock()
    writer.write = lambda chunk: written.append(chunk)
    cm = agent.ui.assistant_stream_markdown.return_value
    cm.__enter__ = Mock(return_value=writer)
    cm.__exit__ = Mock(return_value=False)

    asyncio.run(agent._run_turn("hi there"))

    assert "".join(written) == "hello world"
    convo = [(m.role, m.content) for m in agent.session.get_current_conversation()]
    assert ("user", "hi there") in convo
    assert ("assistant", "hello world") in convo


def test_run_turn_aborts_and_preserves_partial(mock_llm, temp_workspace):
    """A cancel mid-turn records the partial assistant text and shows [aborted]."""
    import asyncio

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        session_name="abort-test",
        verbose=False,
        enable_skills=False,
        enable_extensions=False,
    )
    captured = {}

    def achat_stream(messages, tools=None):
        async def stream():
            yield _stream_chunk(content="partial ")
            captured["cancel"].set()
            yield _stream_chunk(content="dropped")

        return stream()

    mock_llm.achat_stream = achat_stream
    real_respond_stream = agent.agent.respond_stream

    def respond_stream(message, cancel=None, max_iterations=None):
        captured["cancel"] = cancel
        return real_respond_stream(message, cancel=cancel, max_iterations=max_iterations)

    agent.agent.respond_stream = respond_stream
    agent.ui = Mock()
    writer = Mock()
    cm = agent.ui.assistant_stream_markdown.return_value
    cm.__enter__ = Mock(return_value=writer)
    cm.__exit__ = Mock(return_value=False)

    asyncio.run(agent._run_turn("do something"))

    agent.ui.system.assert_any_call("[aborted]")
    convo = [(m.role, m.content) for m in agent.session.get_current_conversation()]
    assert ("user", "do something") in convo
    assert ("assistant", "partial ") in convo


def test_run_turn_running_messages_are_visible_and_routed_by_prefix(mock_llm, temp_workspace):
    import asyncio

    from pig_tui import TurnResult

    agent = _agent(mock_llm, temp_workspace)
    runtime = Mock()

    async def stream_turn(*, stream, on_steering, cancel_event=None):
        del stream, cancel_event
        on_steering("!steer now")
        on_steering(">>follow later")
        on_steering("plain running message")
        return TurnResult(content="done", aborted=False)

    runtime.stream_turn = Mock(side_effect=stream_turn)
    agent.interaction_runtime._build_terminal_runtime = Mock(return_value=runtime)
    agent.ui = Mock()

    asyncio.run(agent._run_turn("initial"))

    agent.ui.user.assert_any_call("!steer now")
    agent.ui.user.assert_any_call(">>follow later")
    agent.ui.user.assert_any_call("plain running message")
    agent.ui.system.assert_any_call("⚡ Queued steering message: steer now...")
    agent.ui.system.assert_any_call("📝 Queued follow-up message: follow later...")
    agent.ui.system.assert_any_call("⚡ Queued steering message: plain running message...")

    steering = [m.content for m in agent.agent.message_queue.queue if m.type.value == "steering"]
    followup = [m.content for m in agent.agent.message_queue.queue if m.type.value == "followup"]
    assert steering == ["steer now", "plain running message"]
    assert followup == ["follow later"]


def _agent(mock_llm, ws, **kw):
    return CodingAgent(
        llm=mock_llm,
        workspace=str(ws),
        verbose=False,
        enable_skills=False,
        enable_extensions=False,
        **kw,
    )


def test_command_name_sets_display_name(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="orig")
    agent.ui = Mock()
    agent._handle_command("/name My Cool Session")
    assert agent.session.name == "My Cool Session"


def test_command_name_without_arg_uses_terminal_runtime_editor(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="orig")
    agent.ui = Mock()
    runtime = Mock()
    runtime.run_editor_session.return_value = "Renamed via Runtime"
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/name")

    assert agent.session.name == "Renamed via Runtime"
    runtime.run_editor_session.assert_called_once()
    session = runtime.run_editor_session.call_args.args[0]
    assert isinstance(session, EditorSession)
    assert session.title == "Rename Session"
    assert session.initial_value == "orig"


def test_command_new_starts_fresh_session(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    old_id = agent.session.id
    agent.session.add_message("user", "hello")
    agent._handle_command("/new")
    assert agent.session.id != old_id
    # New session has no prior conversation in the agent context.
    assert all(m.role == "system" for m in agent.agent.history)


def test_command_clone_duplicates_and_switches(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="base")
    agent.ui = Mock()
    agent.session.add_message("user", "hi")
    agent.session.add_message("assistant", "hello there")
    old_id = agent.session.id
    agent._handle_command("/clone")
    assert agent.session.id != old_id
    assert agent.session.name == "base-clone"
    # The cloned conversation is rebuilt into the agent context.
    contents = [m.content for m in agent.agent.history]
    assert "hi" in contents and "hello there" in contents


def test_command_resume_switches_and_restores_context(mock_llm, temp_workspace):
    a = _agent(mock_llm, temp_workspace, session_name="first")
    a.ui = Mock()
    a.session.add_message("user", "remember X")
    a.session.add_message("assistant", "noted X")
    target_id = a.session.id
    a.session.save()

    # Start elsewhere, then resume the first session by id.
    a._handle_command("/new")
    assert a.session.id != target_id
    a._handle_command(f"/resume {target_id}")
    assert a.session.id == target_id
    contents = [m.content for m in a.agent.history]
    assert "remember X" in contents and "noted X" in contents


def test_command_resume_without_arg_uses_terminal_runtime_selector(mock_llm, temp_workspace):
    current = _agent(mock_llm, temp_workspace, session_name="current")
    current.ui = Mock()

    target = _agent(mock_llm, temp_workspace, session_name="target")
    target.ui = Mock()
    target.session.add_message("user", "remember Y")
    target.session.add_message("assistant", "noted Y")
    target_id = target.session.id
    target.session.save()

    runtime = Mock()
    runtime.run_selection_session.return_value = SelectOption(
        value=target_id,
        label="target",
        description="recent",
    )
    current.interaction_runtime._terminal_runtime = runtime

    current._handle_command("/resume")

    assert current.session.id == target_id
    contents = [m.content for m in current.agent.history]
    assert "remember Y" in contents and "noted Y" in contents
    runtime.run_selection_session.assert_called_once()
    session = runtime.run_selection_session.call_args.args[0]
    assert isinstance(session, SelectionSession)
    assert session.title == "Resume Session"
    assert any(
        option.label == "target" and option.value.startswith("target-")
        for option in session.options
    )


def test_tree_command_without_arg_uses_terminal_runtime_selector(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime")
    agent.ui = Mock()
    first = agent.session.add_message("user", "first prompt")
    agent.session.add_message("assistant", "first answer")
    second = agent.session.add_message("user", "second prompt")
    agent.session.add_message("assistant", "second answer")
    current_before_switch = agent.session.tree.current_id

    runtime = Mock()
    runtime.run_tree_browser_session.return_value = TreeBrowserResult(
        entry=Mock(
            value=first.id,
            label="first",
            description=first.id[:8],
        ),
        action=SelectOption("switch", "Switch branch"),
    )
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.current_id == first.id
    assert [msg.content for msg in agent.agent.history if msg.role != "system"] == ["first prompt"]
    runtime.run_tree_browser_session.assert_called_once()
    session = runtime.run_tree_browser_session.call_args.args[0]
    assert isinstance(session, TreeBrowserSession)
    assert session.title == "Session Tree"
    assert first.id in {entry.value for entry in session.entries}
    assert session.entries[session.default_entry_index].value == current_before_switch
    assert "Current path:" in (session.note or "")
    assert "close" in {action.value for action in session.actions}
    assert second.id in agent.session.tree.entries


def test_tree_command_without_arg_can_label_entry_via_runtime_browser(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-label")
    agent.ui = Mock()
    entry = agent.session.add_message("user", "first prompt")
    entry.metadata["label"] = "draft"

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(
                value=entry.id,
                label="first",
                description=entry.id[:8],
            ),
            action=SelectOption("label", "Label entry"),
        ),
        TreeBrowserResult(
            entry=Mock(
                value=entry.id,
                label="release",
                description=entry.id[:8],
            ),
            action=SelectOption("close", "Close browser"),
        ),
    ]
    runtime.run_editor_session.return_value = "release"
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.entries[entry.id].metadata["label"] == "release"
    assert runtime.run_tree_browser_session.call_count == 2
    refreshed_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert any("{release}" in option.label for option in refreshed_session.entries)
    runtime.run_editor_session.assert_called_once()


def test_tree_command_label_cancel_returns_to_browser_without_mutation(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-label-cancel")
    agent.ui = Mock()
    entry = agent.session.add_message("user", "first prompt")

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(value=entry.id, label="first", description=entry.id[:8]),
            action=SelectOption("label", "Label entry"),
        ),
        TreeBrowserResult(
            entry=Mock(value=entry.id, label="first", description=entry.id[:8]),
            action=SelectOption("close", "Close browser"),
        ),
    ]
    runtime.run_editor_session.return_value = "  "
    agent.interaction_runtime._terminal_runtime = runtime

    with patch.object(
        agent.app_actions,
        "label_tree",
        wraps=agent.app_actions.label_tree,
    ) as label_tree:
        agent._handle_command("/tree")

    label_tree.assert_not_called()
    assert "label" not in entry.metadata
    assert runtime.run_tree_browser_session.call_count == 2


def test_tree_command_close_exits_without_tree_mutation(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-close")
    agent.ui = Mock()
    entry = agent.session.add_message("user", "first prompt")
    current_id = agent.session.tree.current_id

    runtime = Mock()
    runtime.run_tree_browser_session.return_value = TreeBrowserResult(
        entry=Mock(value=entry.id, label="first", description=entry.id[:8]),
        action=SelectOption("close", "Close browser"),
    )
    agent.interaction_runtime._terminal_runtime = runtime

    with (
        patch.object(agent.app_actions, "switch_tree") as switch_tree,
        patch.object(agent.app_actions, "label_tree") as label_tree,
        patch.object(agent.app_actions, "fork_tree_entry") as fork_tree_entry,
    ):
        agent._handle_command("/tree")

    assert agent.session.tree.current_id == current_id
    switch_tree.assert_not_called()
    label_tree.assert_not_called()
    fork_tree_entry.assert_not_called()


def test_tree_command_without_arg_can_fork_from_selected_entry_via_runtime_browser(
    mock_llm, temp_workspace
):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-fork")
    agent.ui = Mock()
    first = agent.session.add_message("user", "first prompt")
    agent.session.add_message("assistant", "first answer")
    agent.session.add_message("user", "second prompt")
    previous_id = agent.session.id

    runtime = Mock()
    runtime.run_tree_browser_session.return_value = TreeBrowserResult(
        entry=Mock(
            value=first.id,
            label="first",
            description=first.id[:8],
        ),
        action=SelectOption("fork", "Fork session here"),
    )
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.id != previous_id
    assert agent.session.name == "tree-runtime-fork-fork"
    assert [msg.content for msg in agent.session.get_current_conversation()] == ["first prompt"]
    runtime.run_tree_browser_session.assert_called_once()


def test_tree_command_without_arg_can_jump_to_parent_before_switch(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-parent")
    agent.ui = Mock()
    parent = agent.session.add_message("user", "parent prompt")
    parent_answer = agent.session.add_message("assistant", "parent answer")
    child = agent.session.add_message("user", "child prompt")
    agent.session.add_message("assistant", "child answer")

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(
                value=child.id,
                label="child",
                description=child.id[:8],
            ),
            action=SelectOption("parent", "Jump parent"),
        ),
        TreeBrowserResult(
            entry=Mock(
                value=parent.id,
                label="parent",
                description=parent.id[:8],
            ),
            action=SelectOption("switch", "Switch branch"),
        ),
    ]
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.current_id == parent.id
    assert runtime.run_tree_browser_session.call_count == 2
    second_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert second_session.entries[second_session.default_entry_index].value == parent_answer.id


def test_tree_command_without_arg_can_jump_to_current_before_switch(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-current")
    agent.ui = Mock()
    first = agent.session.add_message("user", "first prompt")
    agent.session.add_message("assistant", "first answer")
    agent.session.add_message("user", "second prompt")
    agent.session.add_message("assistant", "second answer")
    current_tip = agent.session.tree.current_id

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(
                value=first.id,
                label="first",
                description=first.id[:8],
            ),
            action=SelectOption("current", "Jump current"),
        ),
        TreeBrowserResult(
            entry=Mock(
                value=current_tip,
                label="current",
                description=str(current_tip)[:8],
            ),
            action=SelectOption("switch", "Switch branch"),
        ),
    ]
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.current_id == current_tip
    assert runtime.run_tree_browser_session.call_count == 2
    second_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert second_session.entries[second_session.default_entry_index].value == current_tip


def test_tree_command_without_arg_can_filter_children_before_switch(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-children")
    agent.ui = Mock()
    root = agent.session.add_message("user", "root prompt")
    child_a = agent.session.add_message("assistant", "child a", parent_id=root.id)
    child_b = agent.session.add_message("assistant", "child b", parent_id=root.id)

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(
                value=root.id,
                label="root",
                description=root.id[:8],
            ),
            action=SelectOption("children", "Show children"),
        ),
        TreeBrowserResult(
            entry=Mock(
                value=child_a.id,
                label="child a",
                description=child_a.id[:8],
            ),
            action=SelectOption("switch", "Switch branch"),
        ),
    ]
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.current_id == child_a.id
    assert runtime.run_tree_browser_session.call_count == 2
    second_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert [entry.value for entry in second_session.entries] == [child_a.id, child_b.id]


def test_tree_command_children_on_leaf_returns_to_full_browser(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-leaf-children")
    agent.ui = Mock()
    root = agent.session.add_message("user", "root prompt")
    leaf = agent.session.add_message("assistant", "leaf answer", parent_id=root.id)

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(value=leaf.id, label="leaf", description=leaf.id[:8]),
            action=SelectOption("children", "Show children"),
        ),
        TreeBrowserResult(
            entry=Mock(value=leaf.id, label="leaf", description=leaf.id[:8]),
            action=SelectOption("close", "Close browser"),
        ),
    ]
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert runtime.run_tree_browser_session.call_count == 2
    fallback_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert fallback_session.state.scope == "all"
    assert {entry.value for entry in fallback_session.entries} == {root.id, leaf.id}
    runtime.show_status.assert_called_once()


def test_tree_command_without_arg_can_filter_siblings_before_switch(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-runtime-siblings")
    agent.ui = Mock()
    root = agent.session.add_message("user", "root prompt")
    child_a = agent.session.add_message("assistant", "child a", parent_id=root.id)
    child_b = agent.session.add_message("assistant", "child b", parent_id=root.id)
    other_root = agent.session.add_message("user", "other root")

    runtime = Mock()
    runtime.run_tree_browser_session.side_effect = [
        TreeBrowserResult(
            entry=Mock(
                value=child_a.id,
                label="child a",
                description=child_a.id[:8],
            ),
            action=SelectOption("siblings", "Show siblings"),
        ),
        TreeBrowserResult(
            entry=Mock(
                value=child_b.id,
                label="child b",
                description=child_b.id[:8],
            ),
            action=SelectOption("switch", "Switch branch"),
        ),
    ]
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree")

    assert agent.session.tree.current_id == child_b.id
    assert runtime.run_tree_browser_session.call_count == 2
    second_session = runtime.run_tree_browser_session.call_args_list[1].args[0]
    assert [entry.value for entry in second_session.entries] == [child_a.id, child_b.id]
    assert other_root.id not in [entry.value for entry in second_session.entries]


def test_tree_label_without_args_uses_runtime_selector_and_editor(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-label-runtime")
    agent.ui = Mock()
    entry = agent.session.add_message("user", "label this entry")

    runtime = Mock()
    runtime.run_selection_editor_session.return_value = SelectionEditResult(
        option=SelectOption(entry.id, "entry", entry.id[:8], ""),
        edited_value="milestone",
    )
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/tree label")

    assert agent.session.tree.entries[entry.id].metadata["label"] == "milestone"
    runtime.run_selection_editor_session.assert_called_once()
    session = runtime.run_selection_editor_session.call_args.args[0]
    assert isinstance(session, SelectionEditorSession)
    assert session.title == "Label Session Entry"
    assert session.use_selected_description_as_initial is False


def test_tree_label_with_entry_selector_uses_runtime_editor(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="tree-label-edit-runtime")
    agent.ui = Mock()
    entry = agent.session.add_message("user", "label this specific entry")
    entry.metadata["label"] = "draft"

    runtime = Mock()
    runtime.run_editor_session.return_value = "release"
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command(f"/tree label {entry.id[:8]}")

    assert agent.session.tree.entries[entry.id].metadata["label"] == "release"
    runtime.run_editor_session.assert_called_once()
    session = runtime.run_editor_session.call_args.args[0]
    assert isinstance(session, EditorSession)
    assert session.title == "Edit Tree Label"
    assert session.initial_value == "draft"


def test_command_import_loads_jsonl_session(mock_llm, temp_workspace, tmp_path):
    # Produce a session file elsewhere.
    src = _agent(mock_llm, temp_workspace, session_name="exported")
    src.ui = Mock()
    src.session.add_message("user", "imported question")
    src.session.add_message("assistant", "imported answer")
    src_path = src.session.save()

    other_ws = tmp_path / "other"
    other_ws.mkdir()
    agent = _agent(mock_llm, other_ws)
    agent.ui = Mock()
    agent._handle_command(f"/import {src_path}")
    contents = [m.content for m in agent.agent.history]
    assert "imported question" in contents and "imported answer" in contents


def test_command_copy_uses_clipboard(mock_llm, temp_workspace):
    from unittest.mock import patch

    from pig_llm import Message

    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    agent.agent.history.append(Message(role="assistant", content="the final answer"))

    with patch.object(CodingAgent, "_copy_to_clipboard", return_value=True) as cp:
        agent._handle_command("/copy")
    cp.assert_called_once_with("the final answer")


def test_command_settings_shows_panel(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    with patch.object(
        agent.interaction_runtime.views,
        "show_settings",
        wraps=agent.interaction_runtime.views.show_settings,
    ) as show_settings:
        agent._handle_command("/settings")

    show_settings.assert_called_once_with()
    agent.ui.panel.assert_called_once()
    body = agent.ui.panel.call_args.args[0]
    assert "Settings" in body and "Model:" in body
    assert "project config" in body
    assert "live" in body
    for key in agent._EDITABLE_SETTINGS:
        assert key in body
    assert "temperature" not in body


def test_command_settings_without_arg_uses_runtime_selector_and_editor(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    runtime = Mock()
    runtime.run_selection_editor_session.return_value = SelectionEditResult(
        option=SelectOption(
            "auto_compact_threshold",
            "auto_compact_threshold",
            "0.85",
            "0.85",
        ),
        edited_value="0.5",
    )
    agent.interaction_runtime._terminal_runtime = runtime

    agent._handle_command("/settings")

    cfg = agent.config_manager.load_config()
    assert cfg.auto_compact_threshold == 0.5
    runtime.run_selection_editor_session.assert_called_once()
    session = runtime.run_selection_editor_session.call_args.args[0]
    assert isinstance(session, SelectionEditorSession)
    assert session.title == "Edit Setting"
    assert session.edit_title == "Edit Setting Value"
    threshold = next(
        option for option in session.options if option.value == "auto_compact_threshold"
    )
    assert threshold.initial_value == "0.85"
    assert "live" in threshold.description
    assert {option.value for option in session.options} == set(agent._EDITABLE_SETTINGS)
    assert all("live" in option.description for option in session.options)
    assert str(agent.config_manager.project_config) in (session.edit_note or "")
    assert str(agent.config_manager.global_config) in (session.edit_note or "")
    assert "true/false" in (session.edit_note or "")


def test_command_settings_cancel_does_not_write_config(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    runtime = Mock()
    runtime.run_selection_editor_session.return_value = SelectionEditResult(
        option=None,
        edited_value=None,
    )
    agent.interaction_runtime._terminal_runtime = runtime

    with patch.object(
        agent.app_actions,
        "set_setting",
        wraps=agent.app_actions.set_setting,
    ) as set_setting:
        agent._handle_command("/settings")

    set_setting.assert_not_called()
    assert not agent.config_manager.project_config.exists()


def test_command_settings_with_missing_value_reports_usage(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()

    agent._handle_command("/settings auto_compact_threshold")

    agent.ui.error.assert_called_once_with("Usage: /settings <key> <value>")


def test_context_window_lookup_matches_model(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.agent.llm.config.model = "google/gemini-3.5-flash"
    assert agent.interactive_mode.context_window() == 1_048_576  # real value from the registry
    agent.agent.llm.config.model = "gpt-4o-mini"
    assert agent.interactive_mode.context_window() == 128_000
    agent.agent.llm.config.model = "some-unknown-model"
    assert agent.interactive_mode.context_window() == agent.interactive_mode._DEFAULT_CONTEXT_WINDOW


def test_show_turn_status_reports_context_and_cost(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.agent.llm.config.model = "gpt-4o-mini"
    agent.ui = Mock()
    agent.agent.last_llm_usage = {"input_tokens": 34000, "output_tokens": 1500}
    agent.interactive_mode.show_turn_status(cost_before=0.0)
    line = agent.ui.system.call_args_list[0].args[0]
    assert "context" in line and "%" in line


def test_auto_compact_triggers_only_when_context_nearly_full(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.agent.llm.config.model = "gpt-4o-mini"  # 128k window
    agent.ui = Mock()

    # Well under threshold -> no compaction.
    agent.agent.last_llm_usage = {"input_tokens": 10000, "output_tokens": 500}
    agent.interactive_mode.maybe_auto_compact()
    assert not any("auto-compacting" in c.args[0] for c in agent.ui.system.call_args_list)

    # Over 85% -> compaction announced.
    agent.ui.reset_mock()
    agent.agent.last_llm_usage = {"input_tokens": 120000, "output_tokens": 2000}
    agent.interactive_mode.maybe_auto_compact()
    assert any("auto-compacting" in c.args[0] for c in agent.ui.system.call_args_list)


def test_startup_session_id_resume_restores_llm_context(mock_llm, temp_workspace):
    """pig --session-id at startup must replay the conversation into context."""
    src = _agent(mock_llm, temp_workspace, session_name="ctx")
    src.session.add_message("user", "the secret is 1234")
    src.session.add_message("assistant", "noted: 1234")
    sid = src.session.id
    src.session.save()

    resumed = _agent(mock_llm, temp_workspace, session_id=sid)
    contents = [m.content for m in resumed.agent.history]
    assert any("the secret is 1234" in c for c in contents)
    assert any("noted: 1234" in c for c in contents)


def test_startup_fresh_session_has_no_replayed_history(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace, session_name="brand-new")
    assert all(m.role == "system" for m in agent.agent.history)


def test_settings_set_and_read_back(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    agent._handle_command("/settings auto_compact_threshold 0.5")
    agent._handle_command("/settings auto_compact false")
    cfg = agent.config_manager.load_config()
    assert cfg.auto_compact_threshold == 0.5
    assert cfg.auto_compact is False


def test_settings_write_only_patches_project_scope(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    global_config = temp_workspace / "global-config.json"
    global_config.write_text('{"theme": "light", "auto_compact": true}')
    agent.config_manager.global_config = global_config

    agent._handle_command("/settings auto_compact false")

    project_data = json.loads(agent.config_manager.project_config.read_text())
    assert project_data == {"auto_compact": False}


@pytest.mark.parametrize("command", ["/treehouse", "/settingsfoo"])
def test_command_prefixes_require_token_boundaries(mock_llm, temp_workspace, command):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()

    agent._handle_command(command)

    agent.ui.error.assert_called_once_with(f"Unknown command: {command}")


def test_settings_validation_rejects_bad_values(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    initial_auto_compact = agent.config_manager.load_config().auto_compact
    agent._handle_command("/settings auto_compact_threshold 2.0")  # out of range
    agent._handle_command("/settings provider hacked")  # read-only key
    agent._handle_command("/settings theme light")  # modeled but not runtime-backed
    agent._handle_command("/settings auto_compact maybe")  # invalid boolean
    errors = " ".join(c.args[0] for c in agent.ui.error.call_args_list)
    assert "between 0.0 and 1.0" in errors
    assert "read-only" in errors or "Unknown" in errors
    assert "theme" in errors
    assert "Invalid value for auto_compact" in errors
    assert agent.config_manager.load_config().auto_compact is initial_auto_compact


def test_auto_compact_respects_config(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.agent.llm.config.model = "gpt-4o-mini"  # 128k
    agent.ui = Mock()

    # Disabled -> no compaction even when near full.
    agent._handle_command("/settings auto_compact false")
    agent.agent.last_llm_usage = {"input_tokens": 127000, "output_tokens": 0}
    agent.ui.reset_mock()
    agent.interactive_mode.maybe_auto_compact()
    assert not any("auto-compacting" in c.args[0] for c in agent.ui.system.call_args_list)

    # Re-enabled with a low threshold -> triggers earlier.
    agent._handle_command("/settings auto_compact true")
    agent._handle_command("/settings auto_compact_threshold 0.5")
    agent.agent.last_llm_usage = {"input_tokens": 70000, "output_tokens": 0}
    agent.ui.reset_mock()
    agent.interactive_mode.maybe_auto_compact()
    assert any("auto-compacting" in c.args[0] for c in agent.ui.system.call_args_list)


def test_run_interactive_reuses_one_event_loop_across_turns(mock_llm, temp_workspace):
    """Multiple turns must share one event loop (provider SDKs cache per-loop
    clients; a per-turn asyncio.run() caused 'Event loop is closed')."""
    import asyncio
    from unittest.mock import patch

    from pig_llm import StreamChunk

    loops = []

    def achat_stream(messages, tools=None):
        async def stream():
            loops.append(id(asyncio.get_event_loop()))
            yield StreamChunk(content="ok")

        return stream()

    mock_llm.achat_stream = achat_stream
    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()
    writer = Mock()
    cm = agent.ui.assistant_stream_markdown.return_value
    cm.__enter__ = Mock(return_value=writer)
    cm.__exit__ = Mock(return_value=False)

    prompt = Mock()
    prompt.ask.side_effect = ["first", "second", EOFError()]
    with patch("pig_tui.runtime.PromptRuntime", return_value=prompt):
        agent.run_interactive()

    assert len(loops) == 2  # both turns ran
    assert len(set(loops)) == 1  # on the same loop


def test_run_interactive_reuses_one_terminal_runtime_instance(mock_llm, temp_workspace):
    from pig_tui import ShellLoopResult

    agent = _agent(mock_llm, temp_workspace)
    agent.ui = Mock()

    created = []

    class FakeTerminalRuntime:
        def __init__(self, **kwargs):
            created.append(self)

        def run_shell_loop(self, session):
            assert session.run_turn.__self__ is agent.interactive_mode
            assert session.run_turn.__func__ is agent.interactive_mode.run_turn.__func__
            return ShellLoopResult(reason="eof")

    with patch("pig_coding_agent.interaction_runtime.TerminalRuntime", FakeTerminalRuntime):
        agent.run_interactive()

    assert len(created) == 1


def test_help_command_renders_through_presenter_panel(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.interaction_runtime.presenter = Mock()

    agent._handle_command("/help")

    agent.interaction_runtime.presenter.show_panel.assert_called_once()
    panel = agent.interaction_runtime.presenter.show_panel.call_args.args[0]
    assert panel.title == "Help"
    assert "/help" in panel.content


def test_status_command_renders_through_presenter_panel(mock_llm, temp_workspace):
    agent = _agent(mock_llm, temp_workspace)
    agent.interaction_runtime.presenter = Mock()

    agent._handle_command("/status")

    agent.interaction_runtime.presenter.show_panel.assert_called_once()
    panel = agent.interaction_runtime.presenter.show_panel.call_args.args[0]
    assert panel.title == "Status"
    assert "test-model" in panel.content


def test_files_command_renders_through_presenter_panel(mock_llm, temp_workspace):
    (temp_workspace / "alpha.py").write_text("print('x')")
    agent = _agent(mock_llm, temp_workspace)
    agent.interaction_runtime.presenter = Mock()

    agent._handle_command("/files")

    agent.interaction_runtime.presenter.show_panel.assert_called_once()
    panel = agent.interaction_runtime.presenter.show_panel.call_args.args[0]
    assert panel.title == "Files"
    assert "alpha.py" in panel.content
