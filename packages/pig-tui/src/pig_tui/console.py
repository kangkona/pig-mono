"""Console output with rich formatting."""

from typing import Any
from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.json import JSON


class Console:
    """Enhanced console for rich terminal output."""

    def __init__(self, theme: str = "monokai"):
        """Initialize console.

        Args:
            theme: Syntax highlighting theme
        """
        self.console = RichConsole()
        self.theme = theme

    def print(self, *args, style: str = "", **kwargs) -> None:
        """Print with optional styling.

        Args:
            *args: Content to print
            style: Rich style string (e.g., "bold blue")
            **kwargs: Additional arguments for rich.print
        """
        self.console.print(*args, style=style, **kwargs)

    def markdown(self, text: str) -> None:
        """Render markdown text.

        Args:
            text: Markdown text to render
        """
        md = Markdown(text)
        self.console.print(md)

    def code(self, code: str, language: str = "python", line_numbers: bool = False) -> None:
        """Display syntax highlighted code.

        Args:
            code: Code to display
            language: Programming language
            line_numbers: Show line numbers
        """
        syntax = Syntax(
            code,
            language,
            theme=self.theme,
            line_numbers=line_numbers,
        )
        self.console.print(syntax)

    def json(self, data: Any) -> None:
        """Pretty print JSON data.

        Args:
            data: Data to print as JSON
        """
        json_obj = JSON.from_data(data)
        self.console.print(json_obj)

    def rule(self, title: str = "", style: str = ""):
        """Print a horizontal rule.

        Args:
            title: Optional title
            style: Rich style string
        """
        self.console.rule(title, style=style)

    def clear(self) -> None:
        """Clear the console."""
        self.console.clear()
