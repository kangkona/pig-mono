"""Regression tests for the consolidated tool package."""

from pig_agent_core.tools import Tool, tool


def test_legacy_tool_api_uses_a_normal_package_import() -> None:
    assert Tool.__module__ == "pig_agent_core.tools.legacy"
    assert tool.__module__ == "pig_agent_core.tools.legacy"
