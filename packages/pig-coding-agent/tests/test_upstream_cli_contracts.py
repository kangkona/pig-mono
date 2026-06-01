"""CLI/RPC contract regressions absorbed from recent pi-mono behavior."""

from __future__ import annotations

import io
import json
from unittest.mock import Mock, patch

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

    agent.extension_manager.emit_event.assert_called_once_with(
        "session_shutdown",
        {"reason": "eof"},
    )


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

    agent.extension_manager.emit_event.assert_called_once_with(
        "session_shutdown",
        {"reason": "interrupt"},
    )
