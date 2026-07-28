"""Tests for the public embeddable SDK surface."""

from unittest.mock import Mock

from pig_coding_agent import CodingAgent, create_agent_session
from pig_coding_agent.permissions import PermissionPolicy


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
