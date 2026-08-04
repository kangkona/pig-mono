"""Tests for pig-coding-agent presentation builders."""

from pig_coding_agent.presentation import (
    build_help_panel,
    build_login_panel,
    build_model_panel,
    build_queue_panel,
    build_share_panel,
    build_template_variables_panel,
)


def test_build_help_panel_contains_command_reference() -> None:
    panel = build_help_panel()

    assert "Help" == panel.title
    assert "/help" in panel.content
    assert "/tree" in panel.content
    assert "AGENTS.md" in panel.content


def test_build_template_variables_panel_contains_usage_and_example() -> None:
    panel = build_template_variables_panel("fix-bug", ["issue", "path"])

    assert "Template: fix-bug" == panel.title
    assert "issue" in panel.content
    assert '/fix-bug issue="example"' in panel.content


def test_build_model_panel_contains_current_selection() -> None:
    panel = build_model_panel("openai/gpt-4", "openai", "gpt-4")

    assert "Model" == panel.title
    assert "openai/gpt-4" in panel.content


def test_build_login_panel_documents_env_var_flow() -> None:
    panel = build_login_panel()

    assert "Login" == panel.title
    assert "OPENAI_API_KEY" in panel.content
    assert "browser-based login flow" in panel.content


def test_build_share_panel_contains_gist_fields() -> None:
    panel = build_share_panel({"url": "https://gist.github.com/x", "id": "123", "public": False})

    assert "Shared" == panel.title
    assert "https://gist.github.com/x" in panel.content
    assert "123" in panel.content


def test_build_queue_panel_separates_steering_and_followup() -> None:
    panel = build_queue_panel(
        ["fix this"],
        ["then add tests"],
        steering_mode="one-at-a-time",
        followup_mode="all",
    )

    assert "steer: fix this" in panel.content
    assert "follow-up: then add tests" in panel.content
    assert "steering=one-at-a-time" in panel.content
