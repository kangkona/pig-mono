"""Terminal UI library with rich formatting."""

from .chat import ChatUI
from .console import Console
from .keylistener import LiveInputListener
from .layout import LayoutManager, Overlay, StatusLine
from .progress import Progress, Spinner
from .prompt import InteractivePrompt, Prompt
from .rendering import hyperlink, safe_wrap, terminal_size, truncate_visible
from .theme import Theme

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

__version__ = "0.0.1"

__all__ = [
    "ChatUI",
    "Console",
    "LiveInputListener",
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
    "hyperlink",
    "safe_wrap",
    "terminal_size",
    "truncate_visible",
]
