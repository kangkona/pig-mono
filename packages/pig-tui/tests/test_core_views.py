"""Tests for framework-level pig-tui core abstractions and reusable views."""

from unittest.mock import Mock

from pig_tui.components import (
    ChoiceEditorContainer,
    ConfirmView,
    KeyValueList,
    SelectionActionContainer,
    SelectListView,
    TextBlock,
    TextEditorView,
    TreeBrowserContainer,
    TreeChromeView,
    TreeDetailView,
    TreeListView,
)
from pig_tui.core import (
    Container,
    Focusable,
    PanelContent,
    RenderableView,
    StatusMessage,
    TextEditorState,
    TreeBrowserState,
    TreeDetailState,
    TreeOption,
    TreePathState,
    TreeSummaryState,
    is_focusable,
)
from pig_tui.presenter import ChatPresenter
from pig_tui.views import (
    render_bullet_panel,
    render_info_panel,
    render_select_panel,
    render_status_message,
)


def test_text_block_is_renderable_view():
    block = TextBlock("hello")

    assert isinstance(block, RenderableView)
    assert block.render_lines(40) == ["hello"]


def test_key_value_list_renders_pairs_compactly():
    view = KeyValueList([("Model", "gpt-4"), ("Tools", "4")])

    lines = view.render_lines(80)

    assert any("Model" in line and "gpt-4" in line for line in lines)
    assert any("Tools" in line and "4" in line for line in lines)


def test_select_list_view_tracks_selection_and_renders_cursor():
    view = SelectListView(
        [
            ("session-a", "recent session"),
            ("session-b", "older session"),
        ]
    )
    view.move(1)

    lines = view.render_lines(80)

    assert lines[0].startswith("  ")
    assert lines[1].startswith("-> ")
    assert view.selected_value() == "session-b"


def test_select_list_view_is_focusable_component():
    view = SelectListView([("session-a", None)])
    assert isinstance(view, Focusable)
    assert is_focusable(view) is True

    view.focused = True
    assert view.render(80)[0].startswith("=> ")


def test_text_editor_view_is_focusable_component():
    view = TextEditorView(TextEditorState(title="Rename", value="session-a", note="Edit me"))

    assert isinstance(view, Focusable)
    assert is_focusable(view) is True

    view.focused = True
    lines = view.render(80)
    assert lines[0].startswith("=> ")
    assert "session-a" in lines[0]
    assert any("Edit me" in line for line in lines)


def test_confirm_view_is_focusable_component():
    view = ConfirmView("Allow delete?", default=False)

    assert isinstance(view, Focusable) is False
    assert is_focusable(view) is False

    lines = view.render(80)
    assert lines[0].startswith("   ")
    assert "Allow delete?" in lines[0]


def test_choice_editor_container_renders_selector_and_editor_sections():
    selector = SelectListView([("opt-a", "first"), ("opt-b", "second")])
    editor = TextEditorView(TextEditorState(title="Edit", value="value", note="note"))
    container = ChoiceEditorContainer(
        selector=selector,
        editor=editor,
    )

    sections = container.render_sections(80)

    assert len(sections) == 2
    assert "opt-a" in sections[0]
    assert "value" in sections[1]


def test_choice_editor_container_satisfies_container_protocol():
    selector = SelectListView([("opt-a", "first"), ("opt-b", "second")])
    editor = TextEditorView(TextEditorState(title="Edit", value="value", note="note"))
    container = ChoiceEditorContainer(
        selector=selector,
        editor=editor,
    )

    assert isinstance(container, Container)
    assert container.focus_index(1) is editor
    assert editor.focused is True


def test_selection_action_container_renders_selector_and_action_sections():
    selector = SelectListView([("entry-a", "current"), ("entry-b", "older")])
    actions = SelectListView([("Switch branch", None), ("Label entry", None)])
    container = SelectionActionContainer(
        selector=selector,
        actions=actions,
        action_title="Actions",
    )

    sections = container.render_sections(80)

    assert len(sections) == 2
    assert "entry-a" in sections[0]
    assert "Switch branch" in sections[1]


def test_selection_action_container_satisfies_container_protocol():
    selector = SelectListView([("entry-a", "current")])
    actions = SelectListView([("Switch branch", None), ("Label entry", None)])
    container = SelectionActionContainer(
        selector=selector,
        actions=actions,
        action_title="Actions",
    )

    assert isinstance(container, Container)
    assert container.focus_index(1) is actions
    assert actions.focused is True


def test_tree_list_view_renders_depth_and_state_markers():
    view = TreeListView(
        [
            TreeOption("root", "root", "tip", depth=0, is_branch_point=True),
            TreeOption("child", "child", "current", depth=1, is_current=True, is_anchor=True),
        ]
    )
    view.focused = True
    view.select_index(1)

    lines = view.render(80)

    assert "root [branch]" in lines[0]
    assert "child [current anchor]" in lines[1]
    assert lines[1].startswith("=> ")


def test_tree_browser_container_renders_scope_anchor_and_actions():
    selector = TreeListView(
        [
            TreeOption("root", "root", "tip", depth=0, is_branch_point=True),
            TreeOption(
                "child",
                "child",
                "current",
                depth=1,
                is_current=True,
                is_anchor=True,
                detail_state=TreeDetailState(
                    role="assistant",
                    short_id="child123",
                    depth=1,
                    children_count=0,
                    label=None,
                    preview="child",
                    path_length=2,
                ),
            ),
        ]
    )
    actions = SelectListView([("Switch branch", None), ("Show siblings", None)])
    container = TreeBrowserContainer(
        selector=selector,
        actions=actions,
        action_title="Actions",
        state=TreeBrowserState(
            scope="siblings",
            anchor_entry_id="child-id",
            anchor_label="[assistant] child...",
            summary="2 entries visible | current tip: child123",
            breadcrumbs="root > child",
        ),
    )
    container.select_index(1)

    sections = container.render_sections(80)

    assert len(sections) == 3
    assert "Tree [siblings]" in sections[0]
    assert "Path: root > child" in sections[0]
    assert "Anchor: [assistant] child..." in sections[0]
    assert "Summary: 2 entries visible" in sections[0]
    assert "Switch branch" in sections[1]
    assert "Details" in sections[2]
    assert "Role: assistant" in sections[2]
    assert "ID: child123" in sections[2]
    assert "Path: 2" in sections[2]


def test_tree_browser_state_default_scope_is_all():
    state = TreeBrowserState()

    assert state.scope == "all"


def test_tree_browser_state_defaults_selected_to_current():
    state = TreeBrowserState(current_entry_id="current-1")

    assert state.current_entry_id == "current-1"
    assert state.selected_entry_id == "current-1"


def test_tree_browser_state_defaults_anchor_to_selected_for_scoped_browser():
    state = TreeBrowserState(scope="children", selected_entry_id="entry-1")

    assert state.anchor_entry_id == "entry-1"
    assert state.selected_entry_id == "entry-1"


def test_tree_browser_state_requires_anchor_for_scoped_browser():
    import pytest

    with pytest.raises(ValueError, match="anchor_entry_id"):
        TreeBrowserState(scope="children", selected_entry_id=None, current_entry_id=None)


def test_tree_browser_state_preserves_explicit_selected_entry():
    state = TreeBrowserState(
        scope="siblings",
        current_entry_id="current-1",
        selected_entry_id="selected-2",
        anchor_entry_id="anchor-3",
    )

    assert state.current_entry_id == "current-1"
    assert state.selected_entry_id == "selected-2"
    assert state.anchor_entry_id == "anchor-3"


def test_tree_browser_state_preserves_explicit_anchor_when_selected_changes():
    state = TreeBrowserState(
        scope="siblings",
        current_entry_id="current-1",
        selected_entry_id="selected-2",
        anchor_entry_id="anchor-3",
    )

    assert state.selected_entry_id == "selected-2"
    assert state.anchor_entry_id == "anchor-3"


def test_tree_browser_state_derives_legacy_chrome_from_structured_state():
    state = TreeBrowserState(
        scope="siblings",
        selected_entry_id="entry-2",
        anchor_entry_id="entry-1",
        path_state=TreePathState(
            parts=("root", "child"),
            selected_label="[assistant] child...",
            anchor_label="[user] root...",
        ),
        summary_state=TreeSummaryState(
            visible_count=2,
            total_count=5,
            branch_count=2,
            current_path_length=3,
            current_entry_short_id="tip12345",
        ),
    )

    assert state.breadcrumbs == ("root", "child")
    assert state.anchor_label == "[user] root..."
    assert state.summary == "2 entries visible | total: 5 | current tip: tip12345"
    assert state.chrome_rows == (
        ("Path", "root > child"),
        ("Selected", "[assistant] child..."),
        ("Anchor", "[user] root..."),
        ("Visible", "2"),
        ("Total", "5"),
        ("Branches", "2"),
        ("Current path", "3"),
        ("Current tip", "tip12345"),
    )


def test_tree_option_derives_detail_rows_from_detail_state():
    option = TreeOption(
        value="child-1",
        label="child",
        detail_state=TreeDetailState(
            role="assistant",
            short_id="child123",
            depth=2,
            children_count=3,
            label="milestone",
            preview="preview text",
            path_length=4,
        ),
    )

    assert option.detail_rows == (
        ("Role", "assistant"),
        ("ID", "child123"),
        ("Depth", "2"),
        ("Children", "3"),
        ("Label", "milestone"),
        ("Preview", "preview text"),
        ("Path", "4"),
    )


def test_tree_option_detail_rows_are_derived_when_not_provided():
    option = TreeOption(
        value="child-1",
        label="child",
        detail_state=TreeDetailState(
            role="assistant",
            short_id="child123",
            depth=2,
            children_count=3,
            label="milestone",
            preview="preview text",
            path_length=4,
        ),
    )

    assert dict(option.detail_rows)["Preview"] == "preview text"
    assert dict(option.detail_rows)["Path"] == "4"


def test_tree_detail_state_rows_include_extra_rows():
    state = TreeDetailState(
        role="assistant",
        short_id="child123",
        depth=2,
        children_count=3,
        label="milestone",
        preview="preview text",
        path_length=4,
        extra_rows=(("TokenCost", "$0.0021"),),
    )

    assert state.rows[-1] == ("TokenCost", "$0.0021")


def test_tree_detail_view_renders_rows_and_empty_state():
    filled = TreeDetailView(
        state=TreeDetailState(
            role="assistant",
            short_id="abcd1234",
            depth=1,
            children_count=0,
            label=None,
            preview="child",
            path_length=2,
        )
    )
    empty = TreeDetailView()

    assert filled.render(80) == [
        "Role: assistant",
        "ID: abcd1234",
        "Depth: 1",
        "Children: 0",
        "Label: -",
        "Preview: child",
        "Path: 2",
    ]
    assert empty.render(80) == ["  (empty)"]


def test_tree_chrome_view_prefers_selected_entry_path_and_structured_summary():
    state = TreeBrowserState(
        scope="children",
        selected_entry_id="child",
        anchor_entry_id="root",
        path_state=TreePathState(
            parts=("[user] root...",),
            selected_label="[assistant] stale child...",
            anchor_label="[user] root...",
        ),
        summary_state=TreeSummaryState(
            visible_count=2,
            total_count=4,
            current_path_length=2,
            current_entry_short_id="child123",
        ),
    ).with_selected_entry(
        TreeOption(
            value="child",
            label="[assistant] fresh child...",
            detail_state=TreeDetailState(
                role="assistant",
                short_id="child123",
                depth=1,
                children_count=0,
                label=None,
                preview="fresh child",
                path_length=2,
                path_labels=("[user] root...", "[assistant] fresh child..."),
            ),
        )
    )
    view = TreeChromeView(state=state, active=True)

    lines = view.render(80)

    assert lines[0] == "Tree [children] [active]"
    assert any("Path: [user] root... > [assistant] fresh child..." in line for line in lines)
    assert any("Selected: [assistant] fresh child..." in line for line in lines)
    assert any("Anchor: [user] root..." in line for line in lines)
    assert any("Visible: 2" in line for line in lines)
    assert any("Current tip: child123" in line for line in lines)


def test_tree_list_view_selected_index_is_read_only_outside_select_index():
    import pytest

    view = TreeListView([TreeOption("child", "child")])

    with pytest.raises(AttributeError):
        view.selected_index = 1


def test_tree_browser_container_focus_index_two_returns_detail_view():
    selector = TreeListView(
        [
            TreeOption(
                "child",
                "child",
                "current",
                depth=1,
                is_current=True,
                is_anchor=True,
                detail_state=TreeDetailState(
                    role="assistant",
                    short_id="child123",
                    depth=1,
                    children_count=0,
                    label=None,
                    preview="child",
                    path_length=2,
                ),
            ),
        ]
    )
    actions = SelectListView([("Switch branch", None)])
    container = TreeBrowserContainer(
        selector=selector,
        actions=actions,
        action_title="Actions",
        state=TreeBrowserState(scope="all"),
    )

    current = container.focus_index(2)
    sections = container.render_sections(80)

    assert isinstance(current, TreeDetailView)
    assert actions.focused is False
    assert "Details [active]" in sections[2]


def test_tree_browser_container_select_index_syncs_detail_and_chrome():
    selector = TreeListView(
        [
            TreeOption(
                "child-a",
                "child-a",
                depth=1,
                detail_state=TreeDetailState(
                    role="assistant",
                    short_id="child111",
                    depth=1,
                    children_count=0,
                    label=None,
                    preview="child a",
                    path_length=2,
                    path_labels=("root", "child-a"),
                ),
            ),
            TreeOption(
                "child-b",
                "child-b",
                depth=1,
                detail_state=TreeDetailState(
                    role="assistant",
                    short_id="child222",
                    depth=1,
                    children_count=1,
                    label="milestone",
                    preview="child b",
                    path_length=2,
                    path_labels=("root", "child-b"),
                ),
            ),
        ]
    )
    actions = SelectListView([("Switch branch", None)])
    container = TreeBrowserContainer(
        selector=selector,
        actions=actions,
        action_title="Actions",
        state=TreeBrowserState(
            scope="children",
            selected_entry_id="child-a",
            anchor_entry_id="root",
            path_state=TreePathState(parts=("root",), anchor_label="root"),
        ),
    )

    selected = container.select_index(1)
    sections = container.render_sections(80)

    assert selected is not None
    assert selected.value == "child-b"
    assert container.detail.state is not None
    assert container.detail.state.short_id == "child222"
    assert "ID: child222" in sections[2]
    assert "Path: root > child-b" in sections[0]


def test_tree_browser_container_does_not_expose_public_sync_detail_helper():
    container = TreeBrowserContainer(
        selector=TreeListView([TreeOption("child", "child")]),
        actions=SelectListView([("Switch branch", None)]),
        state=TreeBrowserState(scope="all"),
    )

    assert hasattr(container, "_sync_detail") is True
    assert hasattr(container, "sync_detail") is False


def test_render_info_panel_returns_string_for_chatui_panel():
    panel = render_info_panel(
        "Session",
        [("ID", "abc123"), ("Entries", "4")],
    )

    assert "Session" in panel.title
    assert "ID" in panel.content
    assert "abc123" in panel.content


def test_render_status_message_formats_prefix():
    msg = render_status_message("ok", "Started new session")

    assert msg == "[ok] Started new session"


def test_render_select_panel_composes_list_footer_and_note():
    panel = render_select_panel(
        "Sessions",
        [("session-a", "recent"), ("session-b", "older")],
        footer_rows=[("Dir", "/tmp/sessions")],
        note="Use /resume to switch",
    )

    assert "session-a" in panel.content
    assert "Dir" in panel.content
    assert "/resume" in panel.content


def test_render_bullet_panel_formats_items():
    panel = render_bullet_panel("Skills", ["code-review", "debugging"], note="Use /skill:name")

    assert "• code-review" in panel.content
    assert "• debugging" in panel.content
    assert "/skill:name" in panel.content


def test_chat_presenter_renders_panel_and_status_via_ui_provider():
    ui = Mock()
    presenter = ChatPresenter(lambda: ui)

    presenter.show_panel(PanelContent(title="Session", content="ID : abc"))
    presenter.show_status(StatusMessage(kind="info", message="Ready"))

    ui.panel.assert_called_once_with("ID : abc", title="Session")
    ui.system.assert_called_once_with("[info] Ready")
