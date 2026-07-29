"""Documentation guardrails for pig-tui."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_readme_describes_platform_layer_direction() -> None:
    readme = (PACKAGE_ROOT / "README.md").read_text()

    required_snippets = [
        "terminal UI platform layer",
        "High-level compatibility helpers",
        "Framework-level core",
        "Component",
        "Focusable",
        "RenderableView",
        "ChatPresenter",
        "OverlaySession",
        "begin_overlay_session()",
        "PromptStep",
        "run_shell_loop()",
        "confirm()",
        "select_option()",
        "SelectionSession",
        "EditorSession",
        "ShellLoopSession",
        "SelectionActionSession",
        "TreeBrowserSession",
        "TreeBrowserState",
        "TreePathState",
        "TreeSummaryState",
        "TreeDetailState",
        "TreeOption",
        "TreeBrowserResult",
        "TreeBrowserContainer",
        "TreeDetailView",
    ]

    for snippet in required_snippets:
        assert snippet in readme


def test_runtime_session_primitives_are_publicly_exported() -> None:
    import pig_tui

    for name in (
        "Component",
        "Focusable",
        "SelectionSession",
        "EditorSession",
        "SelectionEditorSession",
        "SelectionActionSession",
        "SelectionActionResult",
        "TreeBrowserState",
        "TreePathState",
        "TreeSummaryState",
        "TreeDetailState",
        "TreeOption",
        "TreeBrowserResult",
        "TreeBrowserSession",
        "TreeBrowserContainer",
        "TreeDetailView",
        "ShellLoopSession",
        "ShellLoopResult",
    ):
        assert hasattr(pig_tui, name)
