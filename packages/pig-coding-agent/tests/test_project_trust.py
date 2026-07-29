"""Regression tests for the project-local resource trust boundary."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from pig_coding_agent.agent import CodingAgent
from pig_coding_agent.config import AgentConfig, ConfigManager
from pig_coding_agent.project_trust import (
    ProjectTrustResponse,
    ProjectTrustStore,
    canonical_workspace_identity,
    resolve_project_trust,
)


def _mock_llm() -> Mock:
    llm = Mock()
    llm.config = Mock(model="test-model", provider="openai")
    return llm


def _write_extension(directory: Path, marker: Path, label: str) -> None:
    directory.mkdir(parents=True)
    (directory / f"{label}.py").write_text(
        f"from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text({label!r})\n"
        "def extension(api):\n"
        "    pass\n"
    )


def test_canonical_workspace_identity_resolves_symlinks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)

    assert canonical_workspace_identity(alias) == canonical_workspace_identity(workspace)


def test_unknown_unattended_workspace_fails_closed_without_persisting(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".agents" / "skills").mkdir(parents=True)
    store = ProjectTrustStore(tmp_path / "trust.json")

    assert resolve_project_trust(workspace, store=store, unattended=True) is False
    assert not store.path.exists()


def test_workspace_without_resources_stays_untrusted_until_explicitly_allowed(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "empty-workspace"
    workspace.mkdir()
    store = ProjectTrustStore(tmp_path / "trust.json")

    assert resolve_project_trust(workspace, store=store, unattended=True) is False
    assert resolve_project_trust(workspace, store=store, override=False) is False
    assert resolve_project_trust(workspace, store=store, override=True) is True
    assert not store.path.exists()


def test_interactive_decider_can_remember_allow_and_deny(tmp_path: Path) -> None:
    allow_workspace = tmp_path / "allow"
    deny_workspace = tmp_path / "deny"
    (allow_workspace / ".agents").mkdir(parents=True)
    (deny_workspace / ".agents").mkdir(parents=True)
    (allow_workspace / ".agents" / "config.json").write_text("{}")
    (deny_workspace / ".agents" / "config.json").write_text("{}")
    store = ProjectTrustStore(tmp_path / "trust.json")

    assert resolve_project_trust(
        allow_workspace,
        store=store,
        unattended=False,
        decider=lambda request: ProjectTrustResponse(True, remember=True),
    )
    assert not resolve_project_trust(
        deny_workspace,
        store=store,
        unattended=False,
        decider=lambda request: ProjectTrustResponse(False, remember=True),
    )

    assert resolve_project_trust(allow_workspace, store=store, unattended=True)
    assert not resolve_project_trust(deny_workspace, store=store, unattended=True)


def test_explicit_override_wins_over_persisted_decision(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".agents").mkdir(parents=True)
    (workspace / ".agents" / "config.json").write_text("{}")
    store = ProjectTrustStore(tmp_path / "trust.json")
    identity = canonical_workspace_identity(workspace)
    store.set(identity, "deny")

    assert resolve_project_trust(workspace, store=store, override=True)
    assert not resolve_project_trust(workspace, store=store, override=False)
    assert store.get(identity) == "deny"


def test_untrusted_project_resources_are_skipped_but_global_resources_load(
    tmp_path: Path, monkeypatch: Any
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    global_marker = tmp_path / "global-loaded"
    project_marker = tmp_path / "project-loaded"
    _write_extension(home / ".agents" / "extensions", global_marker, "global")
    _write_extension(workspace / ".agents" / "extensions", project_marker, "project")

    (home / ".agents" / "prompts").mkdir(parents=True)
    (home / ".agents" / "prompts" / "global.md").write_text("global prompt")
    (workspace / ".agents" / "prompts").mkdir(parents=True)
    (workspace / ".agents" / "prompts" / "project.md").write_text("project prompt")

    (home / ".agents" / "skills" / "global").mkdir(parents=True)
    (home / ".agents" / "skills" / "global" / "SKILL.md").write_text("# Global")
    (workspace / ".agents" / "skills" / "project").mkdir(parents=True)
    (workspace / ".agents" / "skills" / "project" / "SKILL.md").write_text("# Project")

    (home / ".agents" / "AGENTS.md").write_text("GLOBAL_INSTRUCTION")
    (workspace / "AGENTS.md").write_text("PROJECT_INSTRUCTION")

    agent = CodingAgent(
        llm=_mock_llm(),
        workspace=str(workspace),
        verbose=False,
        enable_resilience=False,
        enable_cost_tracking=False,
        project_trust=False,
    )

    assert global_marker.read_text() == "global"
    assert not project_marker.exists()
    assert "global" in agent.prompt_manager.templates
    assert "project" not in agent.prompt_manager.templates
    assert agent.skill_manager is not None
    assert "global" in agent.skill_manager.skills
    assert "project" not in agent.skill_manager.skills
    assert "GLOBAL_INSTRUCTION" in (agent.agent.system_prompt or "")
    assert "PROJECT_INSTRUCTION" not in (agent.agent.system_prompt or "")


def test_trusted_project_resources_load(tmp_path: Path, monkeypatch: Any) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    marker = tmp_path / "project-loaded"
    _write_extension(workspace / ".agents" / "extensions", marker, "project")
    (workspace / "AGENTS.md").write_text("PROJECT_INSTRUCTION")

    agent = CodingAgent(
        llm=_mock_llm(),
        workspace=str(workspace),
        verbose=False,
        enable_resilience=False,
        enable_cost_tracking=False,
        project_trust=True,
    )

    assert marker.read_text() == "project"
    assert "PROJECT_INSTRUCTION" in (agent.agent.system_prompt or "")


def test_trusted_nested_workspace_preserves_ancestor_instructions(
    tmp_path: Path, monkeypatch: Any
) -> None:
    home = tmp_path / "home"
    repository = tmp_path / "repository"
    workspace = repository / "packages" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    ancestor = repository / "AGENTS.md"
    ancestor.write_text("ANCESTOR_INSTRUCTION")

    trusted = CodingAgent(
        llm=_mock_llm(),
        workspace=str(workspace),
        verbose=False,
        enable_resilience=False,
        enable_cost_tracking=False,
        project_trust=True,
    )
    untrusted = CodingAgent(
        llm=_mock_llm(),
        workspace=str(workspace),
        verbose=False,
        enable_resilience=False,
        enable_cost_tracking=False,
        project_trust=False,
    )

    assert "ANCESTOR_INSTRUCTION" in (trusted.agent.system_prompt or "")
    assert "ANCESTOR_INSTRUCTION" not in (untrusted.agent.system_prompt or "")

    seen_resources: list[Path] = []

    def decide(request: Any) -> Any:
        seen_resources.extend(request.resources)
        return ProjectTrustResponse(False, remember=False)

    assert not resolve_project_trust(workspace, unattended=False, decider=decide)
    assert ancestor in seen_resources


def test_project_config_requires_trust_while_global_config_remains_available(
    tmp_path: Path, monkeypatch: Any
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    (home / ".agents").mkdir(parents=True)
    (workspace / ".agents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    (home / ".agents" / "config.json").write_text('{"theme": "light"}')
    (workspace / ".agents" / "config.json").write_text('{"theme": "dark"}')

    assert ConfigManager(workspace, project_trusted=False).load_config().theme == "light"
    assert ConfigManager(workspace, project_trusted=True).load_config().theme == "dark"


def test_untrusted_settings_never_parse_or_modify_existing_project_config(
    tmp_path: Path, monkeypatch: Any
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    (workspace / ".agents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    project_config = workspace / ".agents" / "config.json"
    original = b'{"auto_compact": false, "unknown_extension_hook": "run-me"}'
    project_config.write_bytes(original)
    manager = ConfigManager(workspace, project_trusted=False)

    with pytest.raises(PermissionError, match="existing untrusted project config"):
        manager.set_config_value("auto_compact", True)

    assert project_config.read_bytes() == original
    assert manager.load_config().auto_compact is True

    with pytest.raises(PermissionError, match="existing untrusted project config"):
        manager.save_config(AgentConfig(auto_compact=False))
    assert project_config.read_bytes() == original


def test_untrusted_settings_never_reread_a_project_file_created_by_this_process(
    tmp_path: Path, monkeypatch: Any
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    manager = ConfigManager(workspace, project_trusted=False)

    manager.set_config_value("auto_compact", False)
    project_config = workspace / ".agents" / "config.json"
    project_config.write_text('{"malicious": "injected", "auto_compact": true}')
    manager.set_config_value("auto_compact_threshold", 0.5)

    assert json.loads(project_config.read_text()) == {
        "auto_compact": False,
        "auto_compact_threshold": 0.5,
    }


def test_project_config_write_rejects_symlinked_agents_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    external = tmp_path / "external"
    workspace.mkdir()
    external.mkdir()
    external_config = external / "config.json"
    original = b'{"external": true}'
    external_config.write_bytes(original)
    (workspace / ".agents").symlink_to(external, target_is_directory=True)
    manager = ConfigManager(workspace, project_trusted=False)

    with pytest.raises(PermissionError, match="symlink"):
        manager.set_config_value("auto_compact", False)

    assert external_config.read_bytes() == original


def test_project_config_write_rejects_symlinked_config_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    agents_dir = workspace / ".agents"
    agents_dir.mkdir(parents=True)
    external_config = tmp_path / "external.json"
    original = b'{"external": true}'
    external_config.write_bytes(original)
    (agents_dir / "config.json").symlink_to(external_config)
    manager = ConfigManager(workspace, project_trusted=False)

    with pytest.raises(PermissionError, match="symlink"):
        manager.save_config(AgentConfig(auto_compact=False))

    assert external_config.read_bytes() == original


def test_project_config_write_rejects_dangling_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    agents_dir = workspace / ".agents"
    agents_dir.mkdir(parents=True)
    missing_external = tmp_path / "missing.json"
    project_config = agents_dir / "config.json"
    project_config.symlink_to(missing_external)
    manager = ConfigManager(workspace, project_trusted=False)

    with pytest.raises(PermissionError, match="symlink"):
        manager.set_config_value("auto_compact", False)

    assert project_config.is_symlink()
    assert not missing_external.exists()
