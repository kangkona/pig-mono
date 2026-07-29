"""Tests for CodingAgent."""

import json
from typing import Any
from unittest.mock import Mock, patch

import pytest
from pig_agent_core import Session
from pig_agent_core.tools import Tool
from pig_coding_agent import permissions
from pig_coding_agent.agent import CodingAgent, SessionExitRequested
from pig_coding_agent.permissions import PermissionPolicy
from pig_llm import Response


@pytest.fixture
def mock_llm() -> Any:
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm


@pytest.fixture
def temp_workspace(tmp_path: Any) -> Any:
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_coding_agent_creation(mock_llm: Any, temp_workspace: Any) -> None:
    """Test creating a coding agent."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
    )

    assert agent.workspace == temp_workspace
    assert agent.llm == mock_llm
    assert agent.agent is not None
    assert agent.app_actions is not None
    assert agent.result_factory is not None


def test_coding_agent_default_llm(temp_workspace: Any) -> None:
    """Test agent with default LLM."""
    with patch("pig_coding_agent.agent.LLM") as mock_llm_class:
        mock_llm = Mock()
        mock_llm_class.return_value = mock_llm

        agent = CodingAgent(workspace=str(temp_workspace))
        assert agent.llm == mock_llm


def test_coding_agent_has_tools(mock_llm: Any, temp_workspace: Any) -> None:
    """Test agent has required tools."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    # Agent should have tools from FileTools, CodeTools, ShellTools
    assert len(agent.agent.registry) > 0

    # Check for some expected tools
    tool_names = agent.agent.registry.list_tools()
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "list_files" in tool_names
    assert "git_status" not in tool_names
    assert "git_commit" not in tool_names
    assert "git_push" not in tool_names


def test_coding_agent_system_prompt(mock_llm: Any, temp_workspace: Any) -> None:
    """Test agent has proper system prompt."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    system_prompt = agent._get_system_prompt()
    assert "coding assistant" in system_prompt.lower()
    assert str(temp_workspace) in system_prompt
    assert "confirm destructive operations" not in system_prompt.lower()


def test_coding_agent_uses_injected_permission_policy_for_tools(
    mock_llm: Any, temp_workspace: Any
) -> None:
    """CodingAgent should expose one policy boundary for file writes and shell execution."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        permission_policy=PermissionPolicy.allow_all(),
    )

    write_result = agent.agent.registry.execute_sync(
        "write_file",
        {"path": "created.txt", "content": "ok"},
    )

    assert write_result.ok is True
    assert (temp_workspace / "created.txt").read_text() == "ok"


def test_coding_agent_interactive_permission_policy_uses_runtime_confirmation(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    terminal_runtime = Mock()
    terminal_runtime.confirm.return_value = True
    with patch.object(
        agent.interaction_runtime,
        "_build_terminal_runtime",
        return_value=terminal_runtime,
    ):
        allowed, reason = agent.permission_policy.check("write_file", "demo.txt")

    assert allowed is True
    assert reason is None
    terminal_runtime.confirm.assert_called_once_with("Allow write_file on demo.txt?", default=False)


@pytest.mark.parametrize("tool_name", ["write_file", "edit_file", "run_command"])
def test_extension_side_effect_tools_use_agent_permission_boundary(
    mock_llm: Any, temp_workspace: Any, tool_name: Any
) -> None:
    calls = []

    def side_effect(target: str) -> str:
        calls.append(target)
        return "unsafe"

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
        permission_policy=PermissionPolicy.deny_all("blocked by host"),
    )
    agent.add_tool(Tool(side_effect, name=tool_name, description="side effect"))

    result = agent.agent.registry.execute_sync(tool_name, {"target": "demo"})

    assert result.ok is False
    assert result.error == "blocked by host"
    assert result.meta["permission_denial"] == {
        "code": permissions.PERMISSION_DENIED_CODE,
        "message": "blocked by host",
        "action": tool_name,
        "target": "demo",
    }
    assert calls == []


def test_extension_edit_file_retains_interactive_confirmation(
    mock_llm: Any, temp_workspace: Any
) -> None:
    calls = []

    def edit_file(path: str) -> str:
        calls.append(path)
        return "edited"

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )
    terminal_runtime = Mock()
    terminal_runtime.confirm.return_value = True
    with patch.object(
        agent.interaction_runtime,
        "_build_terminal_runtime",
        return_value=terminal_runtime,
    ):
        agent.add_tool(Tool(edit_file, name="edit_file", description="edit a file"))
        result = agent.agent.registry.execute_sync("edit_file", {"path": "demo.py"})

    assert result.ok is True
    assert result.data == "edited"
    assert calls == ["demo.py"]
    terminal_runtime.confirm.assert_called_once_with("Allow edit_file on demo.py?", default=False)


def test_coding_agent_run_once(mock_llm: Any, temp_workspace: Any) -> None:
    """Test running agent once."""
    # Mock the agent's run method
    with patch("pig_coding_agent.agent.Agent") as mock_agent_class:
        mock_agent_instance = Mock()
        mock_agent_instance.run = Mock(return_value=Mock(content="Test response"))
        mock_agent_class.return_value = mock_agent_instance

        agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
        result = agent.run_once("Create a hello world function")

        assert result == "Test response"
        mock_agent_instance.run.assert_called_once()
        assert [entry.role for entry in agent.session.get_current_conversation()] == [
            "user",
            "assistant",
        ]


def test_coding_agent_run_once_persists_transcript_and_usage(
    mock_llm: Any, temp_workspace: Any
) -> None:
    mock_llm.config.model = "test-model"
    mock_llm.config.max_retries = 1
    mock_llm.chat.return_value = Response(
        content="Persisted response",
        model="test-model",
        usage={"input_tokens": 13, "output_tokens": 5},
    )
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        enable_extensions=False,
        enable_skills=False,
    )

    result = agent.run_once("Persist this prompt")

    assert result == "Persisted response"
    conversation = agent.session.get_current_conversation()
    assert [(entry.role, entry.content) for entry in conversation] == [
        ("user", "Persist this prompt"),
        ("assistant", "Persisted response"),
    ]
    assert agent.session.usage_ledger.snapshot()["by_kind"]["assistant"] == {
        "calls": 1,
        "input_tokens": 13,
        "output_tokens": 5,
        "cached_tokens": 0,
    }

    loaded = Session.load(agent.session.save())
    assert [(entry.role, entry.content) for entry in loaded.get_current_conversation()] == [
        ("user", "Persist this prompt"),
        ("assistant", "Persisted response"),
    ]
    assert loaded.usage_ledger.snapshot()["by_kind"]["assistant"]["input_tokens"] == 13


def test_coding_agent_handle_exit_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling exit command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    with pytest.raises(SessionExitRequested):
        agent._handle_command("/exit")


def test_coding_agent_handle_quit_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling quit command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))

    with pytest.raises(SessionExitRequested):
        agent._handle_command("/quit")


def test_coding_agent_handle_clear_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling clear command."""
    with patch("pig_coding_agent.agent.Agent") as mock_agent_class:
        mock_agent_instance = Mock()
        mock_agent_class.return_value = mock_agent_instance

        agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
        agent._handle_command("/clear")

        mock_agent_instance.clear_history.assert_called_once()


def test_coding_agent_handle_help_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling help command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()

    # Should not raise
    agent._handle_command("/help")
    agent.ui.panel.assert_called()


def test_coding_agent_handle_files_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling files command."""
    # Create some test files
    (temp_workspace / "test.txt").write_text("content")

    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/files")

    agent.ui.panel.assert_called()


def test_coding_agent_handle_status_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling status command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/status")

    agent.ui.panel.assert_called()


def test_coding_agent_handle_unknown_command(mock_llm: Any, temp_workspace: Any) -> None:
    """Test handling unknown command."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace))
    agent.ui = Mock()
    agent._handle_command("/unknown")

    agent.ui.error.assert_called()


def test_coding_agent_handle_command_delegates_to_interaction_runtime(
    mock_llm: Any, temp_workspace: Any
) -> None:
    """CodingAgent should keep only a thin delegation surface for interactive commands."""
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.interaction_runtime = Mock()

    agent._handle_command("/help")

    agent.interaction_runtime.handle_command.assert_called_once_with("/help")


def test_interaction_runtime_handle_command_delegates_to_dispatcher(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.interaction_runtime.dispatcher = Mock()

    agent.interaction_runtime.handle_command("/help")

    agent.interaction_runtime.dispatcher.dispatch.assert_called_once_with("/help")


def test_coding_agent_run_interactive_delegates_to_interactive_mode(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.interactive_mode = Mock()

    agent.run_interactive()

    agent.interactive_mode.run_interactive.assert_called_once_with()


def test_coding_agent_run_turn_delegates_to_interactive_mode(
    mock_llm: Any, temp_workspace: Any
) -> None:
    import asyncio

    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    async def _run_turn(user_input: Any, cancel: Any = None) -> Any:
        assert user_input == "hello"
        assert cancel is None

    agent.interactive_mode = Mock()
    agent.interactive_mode.run_turn = Mock(side_effect=_run_turn)

    asyncio.run(agent._run_turn("hello"))

    agent.interactive_mode.run_turn.assert_called_once()


def test_coding_agent_exposes_app_layer_services(mock_llm: Any, temp_workspace: Any) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    assert agent.interaction_runtime is not None
    assert agent.interaction_catalog is not None
    assert agent.app_actions is not None
    assert agent.result_factory is not None
    assert hasattr(agent.interaction_runtime, "_build_simple_command_routes")
    assert hasattr(agent.interaction_runtime, "_build_prefix_command_routes")


def test_interaction_catalog_builds_base_and_dynamic_commands(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    commands = agent.interaction_catalog.build_commands()

    for command in ("/help", "/tree", "/settings", "/copy"):
        assert command in commands


def test_interaction_runtime_prefix_routes_cover_command_families(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    routes = agent.interaction_runtime._build_prefix_command_routes()

    for prefix in (
        "/fork",
        "/compact",
        "/skill:",
        "/export",
        "/model",
        "/logout",
        "/resume",
        "/name",
        "/import",
        "/settings",
    ):
        assert prefix in routes


def test_coding_agent_session_commands_return_structured_results(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.session.add_message("user", "hello")
    agent.session.add_message("assistant", "world")

    fork_result = agent.app_actions.fork_session("forked")
    assert fork_result["ok"] is True
    assert fork_result["name"] == "forked"
    assert "save_path" in fork_result

    new_result = agent.app_actions.new_session()
    assert new_result["ok"] is True
    assert "session_id" in new_result


def test_coding_agent_tree_actions_return_structured_results(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    entry = agent.session.add_message("user", "branch here")

    label_result = agent.app_actions.label_tree(entry.id[:8], "milestone")
    assert label_result["ok"] is True
    assert label_result["entry_id"] == entry.id
    assert label_result["label"] == "milestone"

    switch_result = agent.app_actions.switch_tree(entry.id[:8])
    assert switch_result["ok"] is True
    assert switch_result["entry_id"] == entry.id

    parent_result = agent.app_actions.parent_tree_entry_id(entry.id[:8])
    assert parent_result == entry.id

    fork_result = agent.app_actions.fork_tree_entry(entry.id[:8], "forked-branch")
    assert fork_result["ok"] is True
    assert fork_result["name"] == "forked-branch"
    assert fork_result["entries"] == 1


def test_tree_browser_view_data_can_filter_children(mock_llm: Any, temp_workspace: Any) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    root = agent.session.add_message("user", "root")
    child_a = agent.session.add_message("assistant", "child a", parent_id=root.id)
    child_b = agent.session.add_message("assistant", "child b", parent_id=root.id)

    browser = agent.app_actions.tree_browser_view_data(root.id, scope="children")

    assert browser is not None
    assert [option.value for option in browser["options"]] == [child_a.id, child_b.id]
    assert browser["state"].scope == "children"
    assert browser["state"].current_entry_id == agent.session.tree.current_id
    assert browser["state"].selected_entry_id == root.id
    assert browser["state"].anchor_entry_id == root.id
    assert browser["state"].path_state is not None
    assert browser["state"].path_state.parts == ("[user] root...",)
    assert browser["state"].path_state.selected_label == "[user] root..."
    assert browser["state"].path_state.anchor_label == "[user] root..."
    assert browser["state"].summary_state is not None
    assert browser["state"].summary_state.visible_count == 2
    assert browser["state"].summary_state.total_count == 3
    assert browser["state"].summary_state.current_path_length == 2
    assert (
        browser["state"].summary_state.current_entry_short_id == agent.session.tree.current_id[:8]
    )
    detail_state = browser["options"][0].detail_state
    assert detail_state is not None
    assert detail_state.role == "assistant"
    assert detail_state.short_id == child_a.id[:8]
    assert detail_state.depth == 1
    assert detail_state.children_count == 0
    assert detail_state.label is None
    assert detail_state.preview == "child a"
    assert detail_state.path_length == 2
    assert detail_state.path_labels == ("[user] root...", "[assistant] child a...")
    detail_rows = dict(browser["options"][0].detail_rows)
    assert detail_rows["Role"] == "assistant"
    assert detail_rows["ID"] == child_a.id[:8]
    assert detail_rows["Depth"] == "1"
    assert detail_rows["Children"] == "0"
    assert detail_rows["Label"] == "-"
    assert detail_rows["Preview"] == "child a"
    assert detail_rows["Path"] == "2"


def test_coding_agent_setting_update_returns_structured_result(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    result = agent.app_actions.set_setting("auto_compact_threshold", "0.5")
    assert result["ok"] is True
    assert result["key"] == "auto_compact_threshold"
    assert result["value"] == 0.5

    invalid = agent.app_actions.set_setting("provider", "hacked")
    assert invalid["ok"] is False
    assert "Unknown or read-only setting" in str(invalid["error"])


def test_coding_agent_settings_expose_only_runtime_backed_application_modes(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    assert agent._EDITABLE_SETTINGS == ("auto_compact", "auto_compact_threshold")
    assert all(
        agent.app_actions.setting_apply_mode(key) == "live" for key in agent._EDITABLE_SETTINGS
    )
    assert agent.app_actions.setting_apply_mode("theme") == "unsupported"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("yes", True),
        ("on", True),
        ("1", True),
        ("false", False),
        ("no", False),
        ("off", False),
        ("0", False),
    ],
)
def test_coding_agent_setting_boolean_tokens_are_explicit(
    mock_llm: Any, temp_workspace: Any, raw_value: Any, expected: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    result = agent.app_actions.set_setting("auto_compact", raw_value)

    assert result["ok"] is True
    assert result["value"] is expected
    assert result["needs_restart"] is False
    assert agent.config_manager.load_config().auto_compact is expected


def test_coding_agent_compact_and_export_return_structured_results(
    mock_llm: Any, temp_workspace: Any, tmp_path: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    for i in range(4):
        agent.session.add_message("user", f"Message {i}")

    compact_result = agent.app_actions.compact_session(None)
    assert compact_result["ok"] is True
    assert compact_result.before is not None
    assert compact_result.after is not None
    assert compact_result.before >= compact_result.after

    export_path = tmp_path / "demo.html"
    with patch("pig_agent_core.SessionExporter.export_to_html", return_value=export_path):
        export_result = agent.app_actions.export_session(None)
    assert export_result["ok"] is True
    assert export_result["exported"] == str(export_path)


def test_coding_agent_short_compaction_does_not_reuse_stale_checkpoint(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    for i in range(12):
        agent.session.add_message("user", f"Message {i}")

    first = agent.app_actions.compact_session(None)
    second = agent.app_actions.compact_session(None)

    assert first["checkpoint_id"]
    assert second["checkpoint_id"] is None


def test_coding_agent_app_actions_cover_session_tree_and_settings_flows(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)

    for name in (
        "build_tree_selector_options",
        "tree_browser_view_data",
        "parent_tree_entry_id",
        "resolve_entry_id",
        "label_tree",
        "switch_tree",
        "rebuild_history_from_session",
        "switch_to_session",
        "new_session",
        "resume_session",
        "clone_session",
        "name_session",
        "import_session",
        "copy_last_message",
        "set_setting",
        "compact_session",
        "export_session",
    ):
        assert hasattr(agent.app_actions, name)


def test_coding_agent_verbose_mode(mock_llm: Any, temp_workspace: Any) -> None:
    """Test agent in verbose mode."""
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=True,
    )

    assert agent.verbose is True
    assert agent.agent.verbose is True


def test_coding_agent_reuses_existing_session_by_session_id(
    mock_llm: Any, temp_workspace: Any
) -> None:
    session = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "hello")
    save_path = session.save()
    assert save_path.exists()

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id=session.id,
    )

    assert agent.session.id == session.id
    assert agent.session.name == "existing"
    assert len(agent.session.tree.entries) == 1


def test_coding_agent_creates_new_session_when_session_id_missing(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id="manual-session-id",
    )

    assert agent.session.id == "manual-session-id"


def test_coding_agent_preserves_full_explicit_session_id_in_saved_filename(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id="manual-session-id",
    )

    saved = agent.session.save()

    assert saved.name == "coding-session-manual-session-id.jsonl"


def test_coding_agent_uses_env_session_dir_for_new_sessions(
    mock_llm: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(session_dir))

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
    )

    saved = agent.session.save()
    assert saved.parent == session_dir


def test_list_sessions_reports_resolved_env_session_dir(
    mock_llm: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(session_dir))

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
    )
    agent.ui = Mock()

    assert agent.interaction_runtime.views is not None
    agent.interaction_runtime.views.list_sessions()

    messages = [call.args[0] for call in agent.ui.system.call_args_list]
    assert f"Sessions are saved to: {session_dir}" in messages


def test_coding_agent_explicit_session_dir_overrides_env(
    mock_llm: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env_session_dir = tmp_path / "env-sessions"
    explicit_session_dir = tmp_path / "explicit-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(env_session_dir))

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
        session_dir=explicit_session_dir,
    )

    saved = agent.session.save()
    assert saved.parent == explicit_session_dir


def test_coding_agent_uses_project_config_session_dir_when_env_missing(
    mock_llm: Any, tmp_path: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "config-sessions"
    config_dir = workspace / ".agents"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "session_dir": str(session_dir),
            }
        )
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
        project_trust=True,
    )

    saved = agent.session.save()
    assert saved.parent == session_dir


def test_coding_agent_uses_global_config_session_dir_when_project_missing(
    mock_llm: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "global-sessions"
    fake_home = tmp_path / "home"
    (fake_home / ".agents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    ((fake_home / ".agents") / "config.json").write_text(
        json.dumps(
            {
                "session_dir": str(session_dir),
            }
        )
    )

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
    )

    saved = agent.session.save()
    assert saved.parent == session_dir


def test_coding_agent_project_config_session_dir_overrides_global_config(
    mock_llm: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    global_session_dir = tmp_path / "global-sessions"
    project_session_dir = tmp_path / "project-sessions"
    fake_home = tmp_path / "home"
    (fake_home / ".agents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    ((fake_home / ".agents") / "config.json").write_text(
        json.dumps(
            {
                "session_dir": str(global_session_dir),
            }
        )
    )
    agents_dir = workspace / ".agents"
    agents_dir.mkdir()
    (agents_dir / "config.json").write_text(json.dumps({"session_dir": str(project_session_dir)}))

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(workspace),
        verbose=False,
        project_trust=True,
    )

    saved = agent.session.save()
    assert saved.parent == project_session_dir


def test_coding_agent_fork_keeps_explicit_session_id(mock_llm: Any, temp_workspace: Any) -> None:
    source = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    source.add_message("user", "hello")
    source.add_message("assistant", "world")
    session_path = source.save()

    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        session_id="fork-target-id",
        fork_source_path=session_path,
    )

    assert agent.session.id == "fork-target-id"
    assert agent.session.name == "existing-fork"
    assert len(agent.session.tree.entries) == 2


def test_coding_agent_verbose_false_suppresses_startup_prints_on_resume(
    mock_llm: Any, temp_workspace: Any
) -> None:
    session = Session(name="existing", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "hello")
    session_path = session.save()

    mock_skill_manager = Mock()
    mock_skill_manager.__len__ = Mock(return_value=2)
    mock_prompt_manager = Mock()
    mock_prompt_manager.__len__ = Mock(return_value=3)

    with (
        patch("pig_coding_agent.agent.SkillManager", return_value=mock_skill_manager),
        patch("pig_coding_agent.agent.PromptManager", return_value=mock_prompt_manager),
        patch("builtins.print") as mock_print,
    ):
        CodingAgent(
            llm=mock_llm,
            workspace=str(temp_workspace),
            verbose=False,
            session_path=session_path,
        )

    mock_print.assert_not_called()


def test_coding_agent_rejects_invalid_manual_session_id(mock_llm: Any, temp_workspace: Any) -> None:
    with pytest.raises(ValueError, match="Session id must be non-empty"):
        CodingAgent(
            llm=mock_llm,
            workspace=str(temp_workspace),
            verbose=False,
            session_id="-bad",
        )


def test_login_command_does_not_advertise_oauth_or_subscription_login(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.ui = Mock()

    agent._handle_command("/login")

    panel = agent.ui.panel.call_args.args[0]
    assert "OAuth" not in panel
    assert "subscription" not in panel.lower()
    assert "API keys" in panel


def test_tree_command_switches_to_entry_prefix_and_rebuilds_history(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.ui = Mock()
    first = agent.session.add_message("user", "first prompt")
    agent.session.add_message("assistant", "first answer")
    second = agent.session.add_message("user", "second prompt")
    agent.session.add_message("assistant", "second answer")

    agent._handle_command(f"/tree {first.id[:8]}")

    assert agent.session.tree.current_id == first.id
    assert [msg.content for msg in agent.agent.history if msg.role != "system"] == ["first prompt"]
    agent.ui.system.assert_any_call(f"[ok] Switched session tree to: {first.id}")
    assert second.id in agent.session.tree.entries


def test_tree_command_emits_extension_lifecycle_when_switching_entry(
    mock_llm: Any, temp_workspace: Any
) -> None:
    ext_dir = temp_workspace / ".agents" / "extensions"
    ext_dir.mkdir(parents=True)
    log_file = temp_workspace / "tree_events.log"
    ext_file = ext_dir / "tree_ext.py"
    ext_file.write_text(
        f"""
from pathlib import Path

LOG = Path({str(log_file)!r})

def extension(api):
    @api.on("session_start")
    def on_start(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"start:{{event['reason']}}:{{event.get('entryId')}}\\n")

    @api.on("session_shutdown")
    def on_shutdown(event, ctx):
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"shutdown:{{event['reason']}}:{{event.get('targetEntryId')}}\\n")
"""
    )
    agent = CodingAgent(
        llm=mock_llm,
        workspace=str(temp_workspace),
        verbose=False,
        enable_extensions=True,
        project_trust=True,
    )
    agent.ui = Mock()
    entry = agent.session.add_message("user", "choose me")

    agent._handle_command(f"/tree {entry.id[:8]}")

    assert log_file.read_text().splitlines() == [
        "start:startup:None",
        f"shutdown:tree:{entry.id}",
        f"start:tree:{entry.id}",
    ]


def test_tree_label_command_persists_label_and_shows_in_tree(
    mock_llm: Any, temp_workspace: Any
) -> None:
    agent = CodingAgent(llm=mock_llm, workspace=str(temp_workspace), verbose=False)
    agent.ui = Mock()
    entry = agent.session.add_message("user", "label me")

    agent._handle_command(f"/tree label {entry.id[:8]} milestone")

    assert agent.session.tree.entries[entry.id].metadata["label"] == "milestone"
    agent.ui.system.assert_any_call(f"[ok] Labeled session entry {entry.id} as: milestone")

    agent.ui.reset_mock()
    agent._handle_command("/tree")
    panel_text = agent.ui.panel.call_args.args[0]
    assert "{milestone}" in panel_text
