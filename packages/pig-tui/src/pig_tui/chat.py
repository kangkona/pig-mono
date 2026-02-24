"""Chat interface components."""

import sys
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .theme import Theme


class StreamWriter:
    """Context manager for streaming text output."""

    def __init__(self, console: Console, prefix: str, style: str):
        """Initialize stream writer."""
        self.console = console
        self.prefix = prefix
        self.style = style
        self.buffer = []

    def write(self, text: str) -> None:
        """Write text to stream."""
        self.buffer.append(text)
        # Print immediately for streaming effect
        self.console.print(text, style=self.style, end="")
        sys.stdout.flush()

    def __enter__(self):
        """Enter context."""
        self.console.print(self.prefix, style=self.style, end="")
        return self

    def __exit__(self, *args):
        """Exit context."""
        self.console.print()  # New line


class ChatUI:
    """Chat interface with message display."""

    def __init__(
        self,
        title: str = "Chat",
        theme: Optional[Theme] = None,
        show_timestamps: bool = False,
        markdown_mode: bool = True,
    ):
        """Initialize chat UI.

        Args:
            title: Chat title
            theme: Color theme
            show_timestamps: Show message timestamps
            markdown_mode: Render messages as markdown
        """
        self.title = title
        self.theme = theme or Theme.dark()
        self.show_timestamps = show_timestamps
        self.markdown_mode = markdown_mode
        self.console = Console()

    def _format_timestamp(self) -> str:
        """Get formatted timestamp."""
        if not self.show_timestamps:
            return ""
        return f"[{self.theme.timestamp_color}]{datetime.now().strftime('%H:%M:%S')}[/] "

    def user(self, message: str) -> None:
        """Display user message.

        Args:
            message: User message
        """
        timestamp = self._format_timestamp()
        prefix = f"{timestamp}[bold {self.theme.user_color}]User:[/] "
        
        if self.markdown_mode:
            self.console.print(prefix, end="")
            self.console.print(Markdown(message))
        else:
            self.console.print(f"{prefix}{message}")

    def assistant(self, message: str) -> None:
        """Display assistant message.

        Args:
            message: Assistant message
        """
        timestamp = self._format_timestamp()
        prefix = f"{timestamp}[bold {self.theme.assistant_color}]Assistant:[/] "
        
        if self.markdown_mode:
            self.console.print(prefix, end="")
            self.console.print(Markdown(message))
        else:
            self.console.print(f"{prefix}{message}")

    @contextmanager
    def assistant_stream(self):
        """Stream assistant response.

        Yields:
            StreamWriter for writing chunks
        """
        timestamp = self._format_timestamp()
        prefix = f"{timestamp}[bold {self.theme.assistant_color}]Assistant:[/] "
        
        writer = StreamWriter(self.console, prefix, self.theme.assistant_color)
        yield writer

    def system(self, message: str) -> None:
        """Display system message.

        Args:
            message: System message
        """
        timestamp = self._format_timestamp()
        self.console.print(
            f"{timestamp}[{self.theme.system_color}]System: {message}[/]"
        )

    def error(self, message: str) -> None:
        """Display error message.

        Args:
            message: Error message
        """
        timestamp = self._format_timestamp()
        self.console.print(
            f"{timestamp}[bold {self.theme.error_color}]Error: {message}[/]"
        )

    def panel(self, content: str, title: str = "") -> None:
        """Display content in a panel.

        Args:
            content: Panel content
            title: Panel title
        """
        panel = Panel(
            content,
            title=title,
            border_style=self.theme.border_color,
        )
        self.console.print(panel)

    def separator(self) -> None:
        """Print a separator line."""
        self.console.rule(style=self.theme.border_color)

    def clear(self) -> None:
        """Clear the chat."""
        self.console.clear()
