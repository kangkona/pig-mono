"""Integration tests for py-coding-agent with session/extension/skills."""

from unittest.mock import Mock, patch

import pytest
from pig_agent_core import ExtensionManager
from pig_coding_agent.agent import CodingAgent
from pig_tui import hyperlink


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
    )
    agent.ui = Mock()

    assert "hello" in agent.extension_manager.api.get_commands()

    ext_file.unlink()
    agent._reload_resources()

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
    )
    agent.ui = Mock()
    session_path = agent.session.save()

    agent._reload_resources()

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
        agent._export_session(None)

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
    )
    agent.ui = Mock()

    assert "message_received" in agent.extension_manager.api._event_handlers

    ext_file.unlink()
    agent._reload_resources()

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

    agent._show_queue()

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

    with patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt):
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

    with patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt):
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
        patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt),
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
        patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt),
        patch.object(agent, "_handle_command", side_effect=wrapped_handle_command),
    ):
        agent.run_interactive()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert any("To resume this session:" in message for message in messages)
    assert any(agent.session.id in message for message in messages)


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
        patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt),
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

    with patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt):
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

    with patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt):
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

    with patch("pig_coding_agent.agent.InteractivePrompt", return_value=prompt):
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


def _streaming_chunk(*, content="", tool_calls=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content or None, tool_calls=tool_calls),
                finish_reason=None,
            )
        ]
    )


def test_run_turn_streams_and_records_session(mock_llm, temp_workspace):
    """_run_turn drives the streaming path and records user + assistant messages."""
    import asyncio

    def achat_stream(messages, tools=None):
        async def stream():
            yield _streaming_chunk(content="hello ")
            yield _streaming_chunk(content="world")

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
    agent.ui = Mock()
    writer = Mock()
    agent.ui.assistant_stream.return_value.__enter__ = Mock(return_value=writer)
    agent.ui.assistant_stream.return_value.__exit__ = Mock(return_value=False)
    writer.__enter__ = Mock(return_value=writer)
    writer.__exit__ = Mock(return_value=False)

    asyncio.run(agent._run_turn("hi there"))

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

    # Stream one chunk, then the turn is cancelled before the second arrives.
    captured = {}

    def achat_stream(messages, tools=None):
        async def stream():
            yield _streaming_chunk(content="partial ")
            captured["cancel"].set()
            yield _streaming_chunk(content="dropped")

        return stream()

    mock_llm.achat_stream = achat_stream

    real_respond_stream = agent.agent.respond_stream

    def respond_stream(message, cancel=None, max_iterations=None):
        captured["cancel"] = cancel
        return real_respond_stream(message, cancel=cancel, max_iterations=max_iterations)

    agent.agent.respond_stream = respond_stream
    agent.ui = Mock()
    writer = Mock()
    agent.ui.assistant_stream.return_value.__enter__ = Mock(return_value=writer)
    agent.ui.assistant_stream.return_value.__exit__ = Mock(return_value=False)
    writer.__enter__ = Mock(return_value=writer)
    writer.__exit__ = Mock(return_value=False)

    asyncio.run(agent._run_turn("do something"))

    agent.ui.system.assert_any_call("[aborted]")
    convo = [(m.role, m.content) for m in agent.session.get_current_conversation()]
    assert ("user", "do something") in convo
    assert ("assistant", "partial ") in convo
