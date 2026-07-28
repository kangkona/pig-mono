"""Terminal UI library with rich formatting."""

from .chat import ChatUI
from .components import (
    ChoiceEditorContainer,
    ConfirmView,
    KeyValueList,
    SelectionActionContainer,
    SelectListView,
    TextBlock,
    TextEditorView,
    TreeBrowserContainer,
    TreeDetailView,
    TreeListView,
)
from .console import Console
from .core import (
    Component,
    Container,
    ContainerContent,
    Focusable,
    PanelContent,
    RenderableView,
    SelectionActionResult,
    SelectionEditResult,
    SelectOption,
    StatusMessage,
    TextEditorState,
    TreeBrowserResult,
    TreeBrowserState,
    TreeDetailState,
    TreeOption,
    TreePathState,
    TreeSummaryState,
    is_focusable,
)
from .keylistener import LiveInputListener
from .layout import LayoutManager, Overlay, StatusLine
from .presenter import ChatPresenter
from .progress import Progress, Spinner
from .prompt import InteractivePrompt, Prompt
from .rendering import hyperlink, safe_wrap, terminal_size, truncate_visible
from .runtime import (
    EditorSession,
    FocusContainer,
    FocusManager,
    OverlaySession,
    OverlayStack,
    PromptRuntime,
    PromptStep,
    SelectionActionSession,
    SelectionEditorSession,
    SelectionSession,
    ShellLoopResult,
    ShellLoopSession,
    StreamingTurnController,
    TerminalRuntime,
    TreeBrowserSession,
    TurnResult,
)
from .theme import Theme
from .views import (
    render_bullet_panel,
    render_info_panel,
    render_select_panel,
    render_status_message,
)

try:
    from .advanced import (
        AutoCompleter,
        FileCompleter,
        InteractiveTable,
        MultiSelect,
        PyCodeCompleter,
        prompt_with_autocomplete,
    )
except ImportError:
    AutoCompleter = None
    FileCompleter = None
    InteractiveTable = None
    MultiSelect = None
    PyCodeCompleter = None
    prompt_with_autocomplete = None

__version__ = "0.1.1"

__all__ = [
    "ChatUI",
    "Console",
    "RenderableView",
    "Component",
    "Container",
    "Focusable",
    "PanelContent",
    "ContainerContent",
    "StatusMessage",
    "SelectionActionResult",
    "SelectionEditResult",
    "SelectOption",
    "TreeBrowserState",
    "TreeDetailState",
    "TreeOption",
    "TreePathState",
    "TreeSummaryState",
    "TreeBrowserResult",
    "TextEditorState",
    "is_focusable",
    "LiveInputListener",
    "ChatPresenter",
    "EditorSession",
    "FocusContainer",
    "FocusManager",
    "OverlaySession",
    "OverlayStack",
    "PromptStep",
    "PromptRuntime",
    "SelectionActionSession",
    "ShellLoopResult",
    "ShellLoopSession",
    "SelectionEditorSession",
    "SelectionSession",
    "StreamingTurnController",
    "TerminalRuntime",
    "TreeBrowserSession",
    "TurnResult",
    "Prompt",
    "InteractivePrompt",
    "Progress",
    "Spinner",
    "Theme",
    "AutoCompleter",
    "FileCompleter",
    "PyCodeCompleter",
    "MultiSelect",
    "InteractiveTable",
    "prompt_with_autocomplete",
    "LayoutManager",
    "StatusLine",
    "Overlay",
    "TextBlock",
    "KeyValueList",
    "SelectionActionContainer",
    "SelectListView",
    "TextEditorView",
    "TreeBrowserContainer",
    "TreeDetailView",
    "TreeListView",
    "ChoiceEditorContainer",
    "ConfirmView",
    "render_info_panel",
    "render_select_panel",
    "render_bullet_panel",
    "render_status_message",
    "hyperlink",
    "safe_wrap",
    "terminal_size",
    "truncate_visible",
]
