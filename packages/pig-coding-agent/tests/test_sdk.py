"""Tests for the public embeddable SDK surface."""

from unittest.mock import Mock

from pig_coding_agent import CodingAgent, create_agent_session, permissions
from pig_coding_agent.permissions import PermissionPolicy
from pig_coding_agent.project_trust import ProjectTrustResponse, ProjectTrustStore


def test_create_agent_session_returns_stable_runtime_contract(tmp_path):
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


def test_runtime_prompt_delegates_to_coding_agent(tmp_path):
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")
    runtime = create_agent_session(workspace=tmp_path, llm=llm, verbose=False)
    runtime.agent.run_once = Mock(return_value="answer")

    assert runtime.prompt("hello") == "answer"
    runtime.agent.run_once.assert_called_once_with("hello")


def test_sdk_defaults_to_structured_fail_closed_write_policy(tmp_path):
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


def test_sdk_host_can_decide_and_remember_project_trust(tmp_path):
    workspace = tmp_path / "workspace"
    skill_dir = workspace / ".agents" / "skills" / "trusted"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Trusted")
    store = ProjectTrustStore(tmp_path / "trust.json")
    requests = []
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")

    runtime = create_agent_session(
        workspace=workspace,
        llm=llm,
        verbose=False,
        enable_extensions=False,
        project_trust_decider=lambda request: (
            requests.append(request) or ProjectTrustResponse(True, remember=True)
        ),
        project_trust_store=store,
    )

    assert len(requests) == 1
    assert "trusted" in runtime.agent.skill_manager
    assert store.get(requests[0].identity) == "allow"
