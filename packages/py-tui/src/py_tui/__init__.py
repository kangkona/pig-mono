"""Terminal UI library with rich formatting."""

from .chat import ChatUI
from .console import Console
from .prompt import Prompt, InteractivePrompt
from .progress import Progress, Spinner
from .theme import Theme
from .advanced import AutoCompleter, FileCompleter, PyCodeCompleter, MultiSelect, InteractiveTable, prompt_with_autocomplete
from .layout import LayoutManager, StatusLine, Overlay

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
