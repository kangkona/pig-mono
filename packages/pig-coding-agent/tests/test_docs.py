"""Documentation truthfulness and parity-matrix guardrails."""

from pathlib import Path

import pig_coding_agent

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_readme_does_not_advertise_unimplemented_cli_commands_or_tools() -> None:
    readme = (PACKAGE_ROOT / "README.md").read_text()

    forbidden_snippets = [
        "pig refactor",
        "pig chat",
        "generate_code(",
        "explain_code(",
        "fix_code(",
        "add_tests(",
        "search_files(",
        ".pig-config.json",
        "OAuth Login",
        "subscription login",
    ]

    for snippet in forbidden_snippets:
        assert snippet not in readme

    assert "Read, write, edit files" not in readme
    assert "`edit_file` is not a built-in tool today" in readme
    assert "tool_permission_denied" in readme
    assert "`permission_denied` event" in readme
    assert "`permissionDenials` array" in readme
    assert "`prompt_result()`" in readme
    assert "exit with status 2" in readme


def test_parity_matrix_exists_and_is_self_contained() -> None:
    matrix_path = PACKAGE_ROOT / "docs" / "pi-parity-matrix.md"
    matrix = matrix_path.read_text()

    assert "does not require a local pi-mono checkout" in matrix
    for capability in [
        "CLI modes",
        "Tool permissions",
        "Session tree",
        "Settings",
        "Extensions",
        "Authentication",
        "SDK/runtime",
    ]:
        assert capability in matrix

    assert "| Session tree | Supported |" in matrix
    assert "prompt-based entry/action browser" in matrix
    assert "Full-screen key navigation is not part of this contract" in matrix
    assert "| Settings | Supported |" in matrix
    assert "auto_compact" in matrix
    assert "| Tool permissions | Supported |" in matrix
    assert "tool_permission_denied" in matrix
    assert "plain CLI routes emit stable text and exit 2" in matrix
    assert "`prompt_result()` exposes structured permission denials" in matrix
    assert "| Compaction | Supported contract |" in matrix
    assert "Semantic summarization is branch-local" in matrix
    assert "Canonical assistant `tool_calls`" in matrix
    assert "semantic branch summarization parity is still not complete" not in matrix


def test_package_exports_runtime_entrypoints() -> None:
    assert hasattr(pig_coding_agent, "CodingAgent")
    assert hasattr(pig_coding_agent, "AgentTurnResult")
    assert hasattr(pig_coding_agent, "create_agent_session")
