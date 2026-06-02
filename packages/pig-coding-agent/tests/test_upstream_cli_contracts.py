"""CLI/RPC contract regressions absorbed from recent pi-mono behavior."""

from __future__ import annotations

import io
import json
from unittest.mock import Mock, patch

import click
from pig_agent_core import ExtensionManager
from pig_coding_agent.cli import JsonLineWriter, main, run_rpc_mode


def test_json_line_writer_emits_strict_jsonl() -> None:
    out = io.StringIO()
    writer = JsonLineWriter(out)

    writer.write({"type": "ready", "message": "hello\nworld"})
    writer.write({"type": "done"})

    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "ready", "message": "hello\nworld"}
    assert json.loads(lines[1]) == {"type": "done"}


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_maps_name_session_id_and_excluded_tools(mock_agent_class, mock_llm_class, tmp_path):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console"):
        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            name="startup-name",
            session_id="fixed-session",
            exclude_tools="read_file,run_command",
        )

    kwargs = mock_agent_class.call_args.kwargs
    assert kwargs["session_name"] == "startup-name"
    assert kwargs["session_id"] == "fixed-session"
    assert kwargs["excluded_tools"] == {"read_file", "run_command"}


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_main_rejects_empty_startup_name(tmp_path):
    ctx = Mock(invoked_subcommand=None)

    with (
        patch("pig_coding_agent.cli.console") as console,
        patch("pig_coding_agent.cli.LLM"),
    ):
        try:
            main(
                ctx=ctx,
                provider="openai",
                workspace=tmp_path,
                name="   ",
            )
        except (click.exceptions.Exit, SystemExit) as exc:
            assert getattr(exc, "exit_code", getattr(exc, "code", None)) == 1
        else:
            raise AssertionError("main should reject empty --name values")

    console.print.assert_any_call("[red]Error: --name requires a non-empty value[/red]")


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_main_rejects_session_id_with_conflicting_session_selector(tmp_path):
    ctx = Mock(invoked_subcommand=None)

    with (
        patch("pig_coding_agent.cli.console") as console,
        patch("pig_coding_agent.cli.LLM"),
    ):
        try:
            main(
                ctx=ctx,
                provider="openai",
                workspace=tmp_path,
                session_id="fixed-session",
                session_name="resume-me",
            )
        except (click.exceptions.Exit, SystemExit) as exc:
            assert getattr(exc, "exit_code", getattr(exc, "code", None)) == 1
        else:
            raise AssertionError("main should reject conflicting session selection flags")

    console.print.assert_any_call(
        "[red]Error: --session-id cannot be combined with --session[/red]"
    )


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_main_rejects_invalid_session_id(tmp_path):
    ctx = Mock(invoked_subcommand=None)

    with (
        patch("pig_coding_agent.cli.console") as console,
        patch("pig_coding_agent.cli.LLM"),
    ):
        try:
            main(
                ctx=ctx,
                provider="openai",
                workspace=tmp_path,
                session_id="-bad",
            )
        except (click.exceptions.Exit, SystemExit) as exc:
            assert getattr(exc, "exit_code", getattr(exc, "code", None)) == 1
        else:
            raise AssertionError("main should reject invalid session ids")

    console.print.assert_any_call(
        "[red]Error: Session id must be non-empty, contain only alphanumeric "
        "characters, '-', '_', and '.', and start and end with an alphanumeric character[/red]"
    )


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_main_rejects_fork_with_conflicting_session_selector(tmp_path):
    ctx = Mock(invoked_subcommand=None)

    with (
        patch("pig_coding_agent.cli.console") as console,
        patch("pig_coding_agent.cli.LLM"),
    ):
        try:
            main(
                ctx=ctx,
                provider="openai",
                workspace=tmp_path,
                fork="source-1234",
                session_name="resume-me",
            )
        except (click.exceptions.Exit, SystemExit) as exc:
            assert getattr(exc, "exit_code", getattr(exc, "code", None)) == 1
        else:
            raise AssertionError("main should reject conflicting fork/session selectors")

    console.print.assert_any_call("[red]Error: --fork cannot be combined with --session[/red]")


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_passes_explicit_compat_mode_to_llm(mock_agent_class, mock_llm_class, tmp_path):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    with patch("pig_coding_agent.cli.console"):
        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            base_url="https://custom.example/v1",
            compat_mode="qwen-chat-template",
        )

    assert mock_llm_class.call_args.kwargs["compat_mode"] == "qwen-chat-template"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_maps_fork_target_to_session_path(mock_agent_class, mock_llm_class, tmp_path):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    source_session = tmp_path / ".sessions" / "source-1234.jsonl"
    source_session.parent.mkdir(parents=True)
    source_session.write_text("{}\n")

    with (
        patch("pig_coding_agent.cli.console"),
        patch("pig_agent_core.SessionManager") as mock_session_manager_class,
    ):
        mock_session_manager = Mock()
        mock_session_manager.find_session.return_value = source_session
        mock_session_manager_class.return_value = mock_session_manager

        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            fork="source-1234",
        )

    kwargs = mock_agent_class.call_args.kwargs
    assert kwargs["session_path"] == source_session
    assert kwargs["session_id"] is None


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_maps_session_target_to_existing_session_path(
    mock_agent_class, mock_llm_class, tmp_path
):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    source_session = tmp_path / ".sessions" / "source-1234.jsonl"
    source_session.parent.mkdir(parents=True)
    source_session.write_text("{}\n")

    with (
        patch("pig_coding_agent.cli.console"),
        patch("pig_agent_core.SessionManager") as mock_session_manager_class,
    ):
        mock_session_manager = Mock()
        mock_session_manager.find_session.return_value = source_session
        mock_session_manager_class.return_value = mock_session_manager

        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            session_name="source-1234",
        )

    kwargs = mock_agent_class.call_args.kwargs
    assert kwargs["session_path"] == source_session


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_keeps_session_name_when_session_target_not_found(
    mock_agent_class, mock_llm_class, tmp_path
):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    with (
        patch("pig_coding_agent.cli.console"),
        patch("pig_agent_core.SessionManager") as mock_session_manager_class,
    ):
        mock_session_manager = Mock()
        mock_session_manager.find_session.return_value = None
        mock_session_manager_class.return_value = mock_session_manager

        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            session_name="startup-name",
        )

    kwargs = mock_agent_class.call_args.kwargs
    assert kwargs["session_path"] is None
    assert kwargs["session_name"] == "startup-name"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_main_accepts_explicit_fork_session_path(mock_agent_class, mock_llm_class, tmp_path):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent.run_interactive = Mock()
    mock_agent_class.return_value = mock_agent

    source_session = tmp_path / ".sessions" / "source-1234.jsonl"
    source_session.parent.mkdir(parents=True)
    source_session.write_text("{}\n")

    with patch("pig_coding_agent.cli.console"):
        main(
            ctx=ctx,
            provider="openai",
            workspace=tmp_path,
            fork=str(source_session),
        )

    kwargs = mock_agent_class.call_args.kwargs
    assert kwargs["session_path"] == source_session
    assert kwargs["fork_source_path"] == source_session


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_json_mode_does_not_print_rich_startup_to_stdout(
    mock_agent_class, mock_llm_class, tmp_path
):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with (
        patch("pig_coding_agent.cli.run_json_mode") as run_json_mode,
        patch("pig_coding_agent.cli.console") as console,
    ):
        main(ctx=ctx, provider="openai", workspace=tmp_path, mode="json")

    run_json_mode.assert_called_once_with(mock_agent)
    console.print.assert_not_called()
    assert mock_agent_class.call_args.kwargs["verbose"] is False


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("pig_coding_agent.cli.LLM")
@patch("pig_coding_agent.cli.CodingAgent")
def test_rpc_mode_reserves_stdout_by_disabling_verbose_startup(
    mock_agent_class, mock_llm_class, tmp_path
):
    ctx = Mock(invoked_subcommand=None)
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    mock_agent = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with (
        patch("pig_coding_agent.cli.run_rpc_mode") as run_rpc_mode,
        patch("pig_coding_agent.cli.console") as console,
    ):
        main(ctx=ctx, provider="openai", workspace=tmp_path, mode="rpc")

    run_rpc_mode.assert_called_once_with(mock_agent)
    console.print.assert_not_called()
    assert mock_agent_class.call_args.kwargs["verbose"] is False


def test_rpc_bash_can_exclude_output_from_context(monkeypatch) -> None:
    requests = iter(
        [
            json.dumps(
                {
                    "id": 1,
                    "method": "bash",
                    "params": {"command": "printf secret", "excludeFromContext": True},
                }
            )
            + "\n",
            "",
        ]
    )
    out = io.StringIO()
    agent = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    response = json.loads(out.getvalue().splitlines()[0])
    assert response["id"] == 1
    assert response["error"] is None
    assert response["result"]["excludedFromContext"] is True
    assert response["result"]["output"] == "[Output excluded from model context]"


def test_rpc_mode_emits_shutdown_reason_on_eof(monkeypatch) -> None:
    requests = iter([""])
    out = io.StringIO()
    agent = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "shutdown"
    assert event["data"] == {"reason": "eof"}


def test_rpc_mode_emits_extension_shutdown_event_on_eof(monkeypatch) -> None:
    requests = iter([""])
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_rpc_mode_emits_shutdown_reason_on_interrupt(monkeypatch) -> None:
    requests = iter(KeyboardInterrupt() for _ in range(1))
    out = io.StringIO()
    agent = Mock()

    def interrupted_readline():
        raise next(requests)

    monkeypatch.setattr("sys.stdin.readline", interrupted_readline)

    with patch("sys.stdout", out):
        run_rpc_mode(agent)

    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "shutdown"
    assert event["data"] == {"reason": "interrupt"}


def test_rpc_mode_emits_extension_shutdown_event_on_interrupt(monkeypatch) -> None:
    requests = iter(KeyboardInterrupt() for _ in range(1))
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    def interrupted_readline():
        raise next(requests)

    monkeypatch.setattr("sys.stdin.readline", interrupted_readline)

    with patch("sys.stdout", out):
        run_rpc_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="interrupt")


def test_rpc_mode_cleans_up_extensions_on_shutdown(monkeypatch) -> None:
    requests = iter([""])
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="eof")


def test_rpc_mode_cleans_up_extensions_on_interrupt(monkeypatch) -> None:
    requests = iter(KeyboardInterrupt() for _ in range(1))
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    def interrupted_readline():
        raise next(requests)

    monkeypatch.setattr("sys.stdin.readline", interrupted_readline)

    with patch("sys.stdout", out):
        run_rpc_mode(agent)

    agent.extension_manager.cleanup.assert_called_once_with(reason="interrupt")


def test_rpc_mode_emits_error_shutdown_reason_on_handler_failure(monkeypatch) -> None:
    requests = iter(
        [json.dumps({"id": 1, "method": "complete", "params": {"message": "hi"}}) + "\n", ""]
    )
    out = io.StringIO()
    agent = Mock()
    agent.agent.run.side_effect = RuntimeError("boom")
    agent.extension_manager = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    error_response = json.loads(lines[0])
    shutdown_event = json.loads(lines[1])

    assert error_response["id"] == 1
    assert error_response["error"] == "boom"
    assert shutdown_event["event"] == "shutdown"
    assert shutdown_event["data"] == {"reason": "error"}
    agent.extension_manager.cleanup.assert_called_once_with(reason="error")


def test_rpc_mode_emits_error_shutdown_reason_on_invalid_json(monkeypatch) -> None:
    requests = iter(["not-json\n", ""])
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    error_response = json.loads(lines[0])
    shutdown_event = json.loads(lines[1])

    assert error_response["error"].startswith("Invalid JSON:")
    assert shutdown_event["event"] == "shutdown"
    assert shutdown_event["data"] == {"reason": "error"}
    agent.extension_manager.cleanup.assert_called_once_with(reason="error")


def test_rpc_mode_emits_error_shutdown_reason_on_read_exception(monkeypatch) -> None:
    out = io.StringIO()
    agent = Mock()
    agent.extension_manager = Mock()

    def broken_readline():
        raise OSError("stdin broke")

    monkeypatch.setattr("sys.stdin.readline", broken_readline)
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    error_response = json.loads(lines[0])
    shutdown_event = json.loads(lines[1])

    assert error_response["error"] == "Error reading request: stdin broke"
    assert shutdown_event["event"] == "shutdown"
    assert shutdown_event["data"] == {"reason": "error"}
    agent.extension_manager.cleanup.assert_called_once_with(reason="error")


def test_rpc_mode_emits_extension_shutdown_once_with_real_extension_manager(
    monkeypatch,
) -> None:
    requests = iter([""])
    out = io.StringIO()
    agent = Mock()
    manager = ExtensionManager(Mock())
    shutdown_events = []

    @manager.api.on("session_shutdown")
    def on_shutdown(event, ctx):
        shutdown_events.append(event)

    agent.extension_manager = manager

    monkeypatch.setattr("sys.stdin.readline", lambda: next(requests))
    monkeypatch.setattr("sys.stdout", out)

    run_rpc_mode(agent)

    assert shutdown_events == [{"reason": "eof"}]
