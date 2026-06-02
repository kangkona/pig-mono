"""Tests for CLI commands."""

import io
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pig_agent_core import ExtensionManager


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
    mock_agent.run_once = Mock(return_value="# Generated code\nprint('hello')")
    mock_agent_class.return_value = mock_agent

    # Test without output file
    with patch("pig_coding_agent.cli.console") as mock_console:
        gen(description="Create a hello world script", output=None, model=None)

        mock_llm_class.assert_called_once()
        mock_agent_class.assert_called_once()
        mock_agent.run_once.assert_called_once()
        mock_console.print.assert_called()


@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_gen_command_with_output(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test gen command with output file."""
    from pig_coding_agent.cli import gen

    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_once = Mock(return_value="print('hello')")
    mock_agent_class.return_value = mock_agent

    # Test with output file
    output_file = tmp_path / "output.py"

    with patch("pig_coding_agent.cli.console") as mock_console:
        gen(description="Create script", output=output_file, model=None)

        assert output_file.exists()
        assert output_file.read_text() == "print('hello')"
        mock_console.print.assert_called()


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
    mock_agent.run_once = Mock(return_value="Analysis: Simple print statement")
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console") as mock_console:
        analyze(path=test_file, model=None)

        mock_agent.run_once.assert_called_once()
        mock_console.print.assert_called()


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
    agent.agent.run.return_value = Mock(content="done")
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
    agent.agent.run.side_effect = RuntimeError("boom")
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


def test_run_json_mode_interactive_emits_error_shutdown_reason() -> None:
    """Interactive JSON mode should emit a concrete shutdown reason on agent failure."""
    from pig_coding_agent.cli import run_json_mode

    agent = Mock()
    agent.agent.run.side_effect = RuntimeError("boom")
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
