"""Terminal UI library with rich formatting."""

from .advanced import (
    AutoCompleter,
    FileCompleter,
    InteractiveTable,
    MultiSelect,
    PyCodeCompleter,
    prompt_with_autocomplete,
)
from .chat import ChatUI
from .console import Console
from .layout import LayoutManager, Overlay, StatusLine
from .progress import Progress, Spinner
from .prompt import InteractivePrompt, Prompt
from .theme import Theme

__version__ = "0.0.1"

__all__ = [
    "ChatUI",
    "Console",
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
]
