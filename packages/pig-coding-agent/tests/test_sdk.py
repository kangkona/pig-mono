"""Tests for the public embeddable SDK surface."""

from typing import Any
from unittest.mock import Mock, patch

from pig_agent_core import OperationKind, RunStatus
from pig_coding_agent import CodingAgent, create_agent_session, permissions
from pig_coding_agent.permissions import PermissionPolicy
from pig_coding_agent.project_trust import (
    ProjectTrustRequest,
    ProjectTrustResponse,
    ProjectTrustStore,
)
from pig_llm import Response


def test_create_agent_session_returns_stable_runtime_contract(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")

    runtime = create_agent_session(
        workspace=tmp_path,
        llm=llm,
        verbose=False,
        permission_policy=PermissionPolicy.allow_all(),
    )

    assert isinstance(runtime.agent, CodingAgent)
    assert runtime.session_id == runtime.agent.session.id
    assert runtime.workspace == tmp_path.resolve()
    assert callable(runtime.prompt)
    assert callable(runtime.close)
    assert runtime.run_store is None
    assert runtime.last_run_id is None


def test_runtime_prompt_delegates_to_coding_agent(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")
    runtime = create_agent_session(workspace=tmp_path, llm=llm, verbose=False)
    with patch.object(runtime.agent, "run_once", return_value="answer") as run_once:
        assert runtime.prompt("hello") == "answer"
        run_once.assert_called_once_with("hello")


def test_sdk_defaults_to_structured_fail_closed_write_policy(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")

    runtime = create_agent_session(
        workspace=tmp_path,
        llm=llm,
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )

    result = runtime.agent.agent.registry.execute_sync(
        "write_file",
        {"path": "blocked.txt", "content": "must not be written"},
    )

    assert result.ok is False
    assert result.error == permissions.UNATTENDED_PERMISSION_DENIAL
    assert result.meta["permission_denial"] == {
        "code": permissions.PERMISSION_DENIED_CODE,
        "message": permissions.UNATTENDED_PERMISSION_DENIAL,
        "action": "write_file",
        "target": str(tmp_path / "blocked.txt"),
    }
    assert not (tmp_path / "blocked.txt").exists()


def test_sdk_host_can_decide_and_remember_project_trust(tmp_path: Any) -> None:
    workspace = tmp_path / "workspace"
    skill_dir = workspace / ".agents" / "skills" / "trusted"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Trusted")
    store = ProjectTrustStore(tmp_path / "trust.json")
    requests: list[ProjectTrustRequest] = []
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")

    def decide(request: ProjectTrustRequest) -> ProjectTrustResponse:
        requests.append(request)
        return ProjectTrustResponse(True, remember=True)

    runtime = create_agent_session(
        workspace=workspace,
        llm=llm,
        verbose=False,
        enable_extensions=False,
        project_trust_decider=decide,
        project_trust_store=store,
    )

    assert len(requests) == 1
    assert runtime.agent.skill_manager is not None
    assert "trusted" in runtime.agent.skill_manager
    assert store.get(requests[0].identity) == "allow"


def test_sdk_opt_in_run_ledger_preserves_prompt_result_contract(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai", max_retries=0)
    llm.chat.return_value = Response(
        content="answer",
        model="test-model",
        finish_reason="stop",
        usage={"prompt_tokens": 4, "completion_tokens": 2},
    )
    ledger_path = tmp_path / "run-ledger.sqlite3"

    runtime = create_agent_session(
        workspace=tmp_path,
        llm=llm,
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
        project_trust=True,
        run_ledger_path=ledger_path,
        run_owner_id="sdk-test",
    )
    result = runtime.prompt_result("hello")

    assert result.content == "answer"
    assert result.completed is True
    assert ledger_path.exists()
    assert runtime.run_store is not None
    assert runtime.last_run_id is not None
    snapshot = runtime.run_store.verify(runtime.last_run_id)
    assert snapshot.run.status is RunStatus.COMPLETED
    assert snapshot.run.owner_id is None
    assert len(snapshot.operations) == 1
    assert len(snapshot.attempts) == 1

    runtime.close()


def test_sdk_run_ledger_captures_provider_and_tool_effects(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai", max_retries=0)
    llm.chat.side_effect = [
        Response(
            content="",
            model="test-model",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": "call-write-1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"effect.txt","content":"hello"}',
                    },
                }
            ],
        ),
        Response(content="done", model="test-model", finish_reason="stop"),
    ]

    runtime = create_agent_session(
        workspace=tmp_path,
        llm=llm,
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
        permission_policy=PermissionPolicy.allow_all(),
        project_trust=True,
        run_ledger_path=tmp_path / "run-ledger.sqlite3",
    )
    result = runtime.prompt_result("write effect.txt")

    assert result.content == "done"
    assert (tmp_path / "effect.txt").read_text() == "hello"
    assert runtime.run_store is not None
    assert runtime.last_run_id is not None
    snapshot = runtime.run_store.verify(runtime.last_run_id)
    kinds = [operation.kind for operation in snapshot.operations.values()]
    assert kinds.count(OperationKind.PROVIDER) == 2
    assert kinds.count(OperationKind.TOOL) == 1
    tool_operation = next(
        operation
        for operation in snapshot.operations.values()
        if operation.kind is OperationKind.TOOL
    )
    assert tool_operation.effect_started is True
    assert tool_operation.receipt_recorded is True
    assert snapshot.run.status is RunStatus.COMPLETED

    runtime.close()
