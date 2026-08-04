"""End-to-end permission-denial regressions for unattended public routes."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import click
import pytest
import typer
from pig_agent_core.tools import Tool
from pig_coding_agent import CodingAgent, create_agent_session, permissions
from pig_coding_agent.cli import analyze, gen, main, run_json_mode, run_rpc_mode
from pig_coding_agent.permissions import PermissionPolicy
from pig_llm import LLM

CLI_EXIT_EXCEPTIONS = (typer.Exit, click.exceptions.Exit, SystemExit)
DENIAL_TEXT = f"{permissions.PERMISSION_DENIED_CODE}: {permissions.UNATTENDED_PERMISSION_DENIAL}"


class ToolCallingLLM:
    """Request one tool call, then return model text that must not mask denial."""

    def __init__(self: Any, tool_name: str, arguments: dict[str, str]) -> None:
        self.config = SimpleNamespace(model="test-model", provider="openai")
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = 0

    def chat(self: Any, messages: Any, tools: Any = None) -> Any:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "function": {
                            "name": self.tool_name,
                            "arguments": json.dumps(self.arguments),
                        },
                    }
                ],
            )
        return SimpleNamespace(content="model tried to hide the denial", tool_calls=None)


def _agent(tmp_path: Any, llm: ToolCallingLLM) -> CodingAgent:
    return CodingAgent(
        llm=cast(LLM, llm),
        workspace=str(tmp_path),
        session_dir=tmp_path / "sessions",
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
        enable_resilience=False,
        enable_cost_tracking=False,
        permission_policy=PermissionPolicy.unattended(),
    )


def _expected_denial(action: str, target: str) -> dict[str, str]:
    return {
        "code": permissions.PERMISSION_DENIED_CODE,
        "message": permissions.UNATTENDED_PERMISSION_DENIAL,
        "action": action,
        "target": target,
    }


def test_json_route_emits_structured_write_denial_without_writing(
    tmp_path: Any, monkeypatch: Any
) -> None:
    blocked = tmp_path / "json-blocked.txt"
    agent = _agent(
        tmp_path,
        ToolCallingLLM(
            "write_file",
            {"path": blocked.name, "content": "must not be written"},
        ),
    )
    stdin = io.StringIO('{"message":"write the file"}\n')
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    with patch("select.select", return_value=([stdin], [], [])):
        run_json_mode(agent)

    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    denial = next(event for event in events if event["type"] == "permission_denied")
    assert {key: denial[key] for key in ("code", "message", "action", "target")} == (
        _expected_denial("write_file", str(blocked))
    )
    assistant = next(
        event for event in events if event["type"] == "message" and event["role"] == "assistant"
    )
    assert assistant["content"] == DENIAL_TEXT
    assert not blocked.exists()


def test_rpc_complete_returns_structured_command_denial_without_running(
    tmp_path: Any, monkeypatch: Any
) -> None:
    blocked = tmp_path / "rpc-blocked.txt"
    command = f"touch {blocked}"
    agent = _agent(tmp_path, ToolCallingLLM("run_command", {"command": command}))
    stdin = io.StringIO(
        json.dumps({"id": 1, "method": "complete", "params": {"message": "run it"}}) + "\n"
    )
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    run_rpc_mode(agent)

    response = json.loads(stdout.getvalue().splitlines()[0])
    assert response["error"] is None
    assert response["result"]["content"] == DENIAL_TEXT
    assert response["result"]["permissionDenials"] == [_expected_denial("run_command", command)]
    assert not blocked.exists()


def test_piped_stdin_prints_stable_command_denial_without_running(
    tmp_path: Any, monkeypatch: Any
) -> None:
    blocked = tmp_path / "pipe-blocked.txt"
    command = f"touch {blocked}"
    llm = ToolCallingLLM("run_command", {"command": command})
    stdin = io.StringIO("run the command\n")
    stdout = io.StringIO()
    ctx = Mock(invoked_subcommand=None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    with (
        patch("pig_coding_agent.cli.LLM", return_value=llm),
        patch("pig_coding_agent.cli.console"),
        patch("select.select", return_value=([stdin], [], [])),
        pytest.raises(CLI_EXIT_EXCEPTIONS) as exc_info,
    ):
        main(
            ctx=ctx,
            model="test-model",
            provider="openai",
            workspace=tmp_path,
            verbose=False,
            no_extensions=True,
            no_skills=True,
            no_resilience=True,
            no_cost_tracking=True,
            mode="interactive",
        )

    assert getattr(exc_info.value, "exit_code", getattr(exc_info.value, "code", None)) == 2
    assert stdout.getvalue().splitlines()[-1] == DENIAL_TEXT
    assert not blocked.exists()


def test_gen_denies_model_write_and_does_not_create_explicit_output(
    tmp_path: Any, monkeypatch: Any
) -> None:
    blocked = tmp_path / "gen-blocked.txt"
    explicit_output = tmp_path / "generated.py"
    llm = ToolCallingLLM(
        "write_file",
        {"path": blocked.name, "content": "must not be written"},
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(tmp_path / "sessions"))

    with (
        patch("pig_coding_agent.cli.LLM", return_value=llm),
        patch("pig_coding_agent.cli.console") as console,
        pytest.raises(CLI_EXIT_EXCEPTIONS) as exc_info,
    ):
        gen(description="generate code", output=explicit_output, model="test-model")

    assert getattr(exc_info.value, "exit_code", getattr(exc_info.value, "code", None)) == 2
    console.print.assert_any_call(f"[red]{DENIAL_TEXT}[/red]")
    assert not blocked.exists()
    assert not explicit_output.exists()


def test_analyze_denies_model_command_without_running(tmp_path: Any, monkeypatch: Any) -> None:
    blocked = tmp_path / "analyze-blocked.txt"
    command = f"touch {blocked}"
    source = tmp_path / "source.py"
    source.write_text("print('safe')\n")
    llm = ToolCallingLLM("run_command", {"command": command})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(tmp_path / "sessions"))

    with (
        patch("pig_coding_agent.cli.LLM", return_value=llm),
        patch("pig_coding_agent.cli.console") as console,
        pytest.raises(CLI_EXIT_EXCEPTIONS) as exc_info,
    ):
        analyze(path=source, model="test-model")

    assert getattr(exc_info.value, "exit_code", getattr(exc_info.value, "code", None)) == 2
    console.print.assert_any_call(f"[red]{DENIAL_TEXT}[/red]")
    assert not blocked.exists()


def test_sdk_prompt_result_denies_extension_edit_with_machine_data(tmp_path: Any) -> None:
    blocked = tmp_path / "sdk-blocked.txt"
    calls: list[str] = []
    llm = ToolCallingLLM(
        "edit_file",
        {"path": str(blocked), "content": "must not be written"},
    )
    runtime = create_agent_session(
        workspace=tmp_path,
        session_dir=tmp_path / "sessions",
        llm=cast(LLM, llm),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )

    def edit_file(path: str, content: str) -> str:
        calls.append(path)
        blocked.write_text(content)
        return "edited"

    runtime.agent.add_tool(Tool(edit_file, name="edit_file", description="edit a file"))

    result = runtime.prompt_result("edit the file")

    assert result.content == DENIAL_TEXT
    assert list(result.permission_denials) == [_expected_denial("edit_file", str(blocked))]
    assert calls == []
    assert not blocked.exists()


def test_sdk_prompt_returns_stable_write_denial_text(tmp_path: Any) -> None:
    blocked = tmp_path / "sdk-prompt-blocked.txt"
    runtime = create_agent_session(
        workspace=tmp_path,
        session_dir=tmp_path / "sessions",
        llm=cast(
            LLM,
            ToolCallingLLM(
                "write_file",
                {"path": blocked.name, "content": "must not be written"},
            ),
        ),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )

    assert runtime.prompt("write the file") == DENIAL_TEXT
    assert not blocked.exists()
