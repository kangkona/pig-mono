"""Tests for CLI commands."""

import io
import os
import signal
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pig_agent_core import ExtensionManager
from pig_coding_agent import AgentTurnResult, permissions
from pig_coding_agent.permissions import PermissionPolicy


@pytest.fixture
def mock_env():
    """Mock environment with API key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        yield


@pytest.fixture
def mock_llm():
    """Mock LLM instance."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm


@pytest.fixture
def mock_ctx():
    """Mock typer context."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    return ctx


def test_cli_imports():
    """Test CLI module imports."""
    from pig_coding_agent.cli import analyze, app, gen, main

    assert app is not None
    assert callable(main)
    assert callable(gen)
    assert callable(analyze)


def test_cli_does_not_export_nonexistent_chat_or_refactor_commands():
    """README and Typer app should not advertise unimplemented commands."""
    from pig_coding_agent.cli import app

    command_names = {command.name for command in app.registered_commands}

    assert "chat" not in command_names
    assert "refactor" not in command_names


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_gen_command(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test gen command."""
    from pig_coding_agent.cli import gen

    # Setup mocks
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_once_result = Mock(
        return_value=AgentTurnResult(content="# Generated code\nprint('hello')")
    )
    mock_agent_class.return_value = mock_agent

    # Test without output file
    with patch("pig_coding_agent.cli.console") as mock_console:
        gen(description="Create a hello world script", output=None, model=None)

        mock_llm_class.assert_called_once()
        mock_agent_class.assert_called_once()
        mock_agent.run_once_result.assert_called_once()
        mock_console.print.assert_called()
        policy = mock_agent_class.call_args.kwargs["permission_policy"]
        assert isinstance(policy, PermissionPolicy)
        assert policy.deny_reason == permissions.UNATTENDED_PERMISSION_DENIAL


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_gen_command_with_output(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test gen command with output file."""
    from pig_coding_agent.cli import gen

    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_once_result = Mock(return_value=AgentTurnResult(content="print('hello')"))
    mock_agent_class.return_value = mock_agent

    # Test with output file
    output_file = tmp_path / "output.py"

    with patch("pig_coding_agent.cli.console") as mock_console:
        gen(description="Create script", output=output_file, model=None)

        assert output_file.exists()
        assert output_file.read_text() == "print('hello')"
        mock_console.print.assert_called()
        assert isinstance(mock_agent_class.call_args.kwargs["permission_policy"], PermissionPolicy)
        assert mock_agent_class.call_args.kwargs["permission_policy"].default == "deny"
        assert (
            mock_agent_class.call_args.kwargs["permission_policy"].deny_reason
            == permissions.UNATTENDED_PERMISSION_DENIAL
        )


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_analyze_command(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test analyze command."""
    from pig_coding_agent.cli import analyze

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")

    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_once_result = Mock(
        return_value=AgentTurnResult(content="Analysis: Simple print statement")
    )
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console") as mock_console:
        analyze(path=test_file, model=None)

        mock_agent.run_once_result.assert_called_once()
        mock_console.print.assert_called()
        assert isinstance(mock_agent_class.call_args.kwargs["permission_policy"], PermissionPolicy)
        assert mock_agent_class.call_args.kwargs["permission_policy"].default == "deny"
        assert (
            mock_agent_class.call_args.kwargs["permission_policy"].deny_reason
            == permissions.UNATTENDED_PERMISSION_DENIAL
        )


def test_analyze_command_missing_file(mock_env):
    """Test analyze command with missing file."""
    from pig_coding_agent.cli import analyze

    with pytest.raises((SystemExit, Exception)):
        with patch("pig_coding_agent.cli.console"):
            analyze(path=Path("nonexistent.py"), model=None)


def test_main_without_api_key(mock_ctx):
    """Test main command without API key."""
    from pig_coding_agent.cli import main

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises((SystemExit, Exception)):
            with patch("pig_coding_agent.cli.console"):
                main(ctx=mock_ctx)


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_with_custom_model(mock_agent_class, mock_llm_class, mock_env, mock_ctx):
    """Test main with custom model."""
    from pig_coding_agent.cli import main

    # Setup mocks
    mock_llm = Mock()
    mock_llm.config = Mock(model="gpt-4")
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_interactive = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console"):
        main(ctx=mock_ctx, model="gpt-4", provider="openai", workspace=Path("."), verbose=True)

        # Verify LLM created with correct model
        assert mock_llm_class.call_args.kwargs.get("model") == "gpt-4"


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_with_workspace(mock_agent_class, mock_llm_class, mock_env, mock_ctx, tmp_path):
    """Test main with custom workspace."""
    from pig_coding_agent.cli import main

    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_interactive = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console"):
        main(ctx=mock_ctx, workspace=tmp_path, provider="openai")

        # Verify agent created with correct workspace
        assert mock_agent_class.call_args.kwargs.get("workspace") == str(tmp_path)


def test_run_json_mode_emits_shutdown_reason():
    """Interactive JSON mode should emit shutdown with a concrete reason."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=EOFError()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.emit_event.assert_any_call(
        "shutdown",
        {"reason": "eof"},
    )


def test_run_json_mode_emits_interrupt_shutdown_reason():
    """Interactive JSON mode should distinguish keyboard interrupts."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=KeyboardInterrupt()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.emit_event.assert_any_call(
        "shutdown",
        {"reason": "interrupt"},
    )


def test_run_json_mode_emits_extension_shutdown_event_on_eof():
    """JSON mode should pass EOF shutdown reasons into extension cleanup."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.extension_manager = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=EOFError()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_run_json_mode_emits_extension_shutdown_event_on_interrupt():
    """JSON mode should pass interrupt shutdown reasons into extension cleanup."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.extension_manager = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=KeyboardInterrupt()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="interrupt")


def test_run_json_mode_cleans_up_extensions_on_shutdown():
    """JSON mode should clean up extensions after shutdown."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.extension_manager = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=EOFError()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_run_json_mode_piped_input_emits_shutdown_reason_and_cleanup(monkeypatch):
    """Piped JSON mode should still terminate with explicit shutdown semantics."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.run_once_result.return_value = AgentTurnResult(content="done")
    agent.extension_manager = Mock()
    json_mode = Mock()

    monkeypatch.setattr("sys.stdin", io.StringIO('{"message":"hello"}\n'))

    with (
        patch("select.select", return_value=([object()], [], [])),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.emit_event.assert_any_call("shutdown", {"reason": "eof"})
    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_run_json_mode_piped_input_emits_error_shutdown_reason(monkeypatch):
    """Piped JSON mode should emit a concrete shutdown reason when agent execution fails."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.run_once_result.side_effect = RuntimeError("boom")
    agent.extension_manager = Mock()
    json_mode = Mock()

    monkeypatch.setattr("sys.stdin", io.StringIO('{"message":"hello"}\n'))

    with (
        patch("select.select", return_value=([object()], [], [])),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.error.assert_called_once_with("Error: boom")
    json_mode.emit_event.assert_any_call("shutdown", {"reason": "error"})
    agent.extension_manager.cleanup.assert_called_once_with(reason="error")


def test_run_json_mode_piped_input_emits_interrupt_shutdown_reason(monkeypatch):
    """Piped JSON mode should emit interrupt shutdown semantics on keyboard interrupt."""
    from pig_coding_agent.cli import run_json_mode

    class InterruptingInput:
        def __iter__(self):
            return self

        def __next__(self):
            raise KeyboardInterrupt()

    agent = Mock()
    agent.extension_manager = Mock()
    json_mode = Mock()

    monkeypatch.setattr("sys.stdin", InterruptingInput())

    with (
        patch("select.select", return_value=([object()], [], [])),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.emit_event.assert_any_call("shutdown", {"reason": "interrupt"})
    agent.extension_manager.cleanup.assert_called_once_with(reason="interrupt")


def test_run_json_mode_emits_extension_shutdown_once_with_real_extension_manager() -> None:
    """JSON mode should not duplicate extension shutdown events."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    manager = ExtensionManager(Mock())
    shutdown_events = []

    @manager.api.on("session_shutdown")
    def on_shutdown(event, ctx):
        shutdown_events.append(event)

    agent.extension_manager = manager
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=EOFError()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    assert shutdown_events == [{"reason": "eof"}]


def test_run_json_mode_cleans_up_extensions_before_shutdown_event() -> None:
    """Protocol shutdown events should not fire before extension teardown."""
    from pig_coding_agent.cli import run_json_mode

    order: list[str] = []
    agent = Mock()
    agent.extension_manager = Mock()
    agent.extension_manager.cleanup.side_effect = lambda reason: order.append(f"cleanup:{reason}")
    json_mode = Mock()
    json_mode.emit_event.side_effect = lambda event, data: order.append(
        f"event:{event}:{data.get('reason', '')}"
    )

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=EOFError()),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    shutdown_event_index = order.index("event:shutdown:eof")
    cleanup_index = order.index("cleanup:eof")
    assert cleanup_index < shutdown_event_index


def test_run_json_mode_interactive_emits_error_shutdown_reason() -> None:
    """Interactive JSON mode should emit a concrete shutdown reason on agent failure."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.run_once_result.side_effect = RuntimeError("boom")
    agent.extension_manager = Mock()
    json_mode = Mock()

    with (
        patch("select.select", return_value=([], [], [])),
        patch("builtins.input", side_effect=["hello"]),
        patch("pig_agent_core.JSONOutputMode", return_value=json_mode),
    ):
        run_json_mode(agent)

    json_mode.message.assert_any_call("user", "hello")
    json_mode.error.assert_called_once_with("Error: boom")
    json_mode.emit_event.assert_any_call("shutdown", {"reason": "error"})
    agent.extension_manager.cleanup.assert_called_once_with(reason="error")


def test_main_installs_signal_cleanup_for_interactive_mode(mock_env, mock_ctx, tmp_path):
    from pig_coding_agent.cli import _available_cleanup_signals, main

    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = Mock()
    mock_agent.extension_manager.extensions = {}
    mock_agent.run_interactive = Mock()

    handlers: dict[int, object] = {}

    def fake_signal(sig, handler):
        if sig not in handlers:
            handlers[sig] = handler
        return None

    with (
        patch("pig_coding_agent.cli.LLM", return_value=mock_llm),
        patch("pig_coding_agent.cli.CodingAgent", return_value=mock_agent),
        patch("pig_coding_agent.cli.console"),
        patch("sys.stdin", Mock(isatty=Mock(return_value=True))),
        patch("signal.signal", side_effect=fake_signal),
    ):
        main(ctx=mock_ctx, provider="openai", workspace=tmp_path)

    expected_signals = _available_cleanup_signals()
    assert signal.SIGTERM in handlers
    assert tuple(handlers) == expected_signals

    with patch("sys.exit", side_effect=SystemExit(0)):
        try:
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        except SystemExit:
            pass

    mock_agent.extension_manager.cleanup.assert_called_once_with(reason="sigterm")


def test_available_cleanup_signals_skips_missing_sighup(monkeypatch):
    from pig_coding_agent import cli

    monkeypatch.delattr(cli.signal, "SIGHUP", raising=False)

    assert cli._available_cleanup_signals() == (signal.SIGTERM,)


def test_run_with_signal_cleanup_prefers_protocol_shutdown_callback() -> None:
    from pig_coding_agent import cli

    agent = Mock()
    agent._protocol_shutdown = Mock()
    handlers: dict[int, object] = {}

    def fake_signal(sig, handler):
        handlers[sig] = handler
        return None

    with (
        patch("signal.signal", side_effect=fake_signal),
        patch("sys.exit", side_effect=SystemExit(0)),
    ):
        try:
            cli._run_with_signal_cleanup(
                agent, lambda: handlers[signal.SIGTERM](signal.SIGTERM, None)
            )
        except SystemExit:
            pass

    agent._protocol_shutdown.assert_called_once_with("sigterm")
    agent.extension_manager.cleanup.assert_not_called()
