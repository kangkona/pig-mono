"""Chat interface components."""

import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from .rendering import normalize_terminal_output, print_markdown_safely
from .theme import Theme


class StreamWriter:
    """Context manager for streaming text output."""

    def __init__(self, console: Console, prefix: str, style: str):
        """Initialize stream writer."""
        self.console = console
        self.prefix = prefix
        self.style = style
        self.buffer: list[str] = []

    def write(self, text: str) -> None:
        """Write text to stream."""
        normalized = normalize_terminal_output(text)
        self.buffer.append(normalized)
        # Print immediately for streaming effect
        self.console.print(normalized, style=self.style, end="")
        sys.stdout.flush()

    def __enter__(self) -> "StreamWriter":
        """Enter context."""
        self.console.print(self.prefix, style=self.style, end="")
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context."""
        self.console.print()  # New line


class MarkdownStreamWriter:
    """Accumulates streamed text and live-renders it as Markdown.

    Re-rendering the whole Markdown on every token is what lets partial syntax
    (an unterminated ``**bold**`` or a ``###`` heading) resolve as more text
    arrives. Refreshes are throttled by the owning Live (a few times a second)
    so long, scrolling responses don't flicker.

    A spinner + elapsed-time status line sits below the content while the turn
    is in progress, so a long LLM/tool wait with no visible output still shows
    the agent is alive (call :meth:`tick` periodically to animate it).
    """

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self) -> None:
        self.text = ""
        self._live: Live | None = None
        self._started = time.monotonic()
        self._frame = 0
        self._done = False
        self._input = ""
        self._cursor = 0
        self._suggestions: list[str] = []

    def _renderable(self) -> Any:
        from rich.console import Group
        from rich.text import Text

        body = Markdown(self.text) if self.text else Text("")
        if self._done:
            return body
        spin = self._FRAMES[self._frame % len(self._FRAMES)]
        elapsed = int(time.monotonic() - self._started)
        status = Text(f"{spin} working… {elapsed}s", style="dim")
        # A persistent input affordance: the user can type to steer at any time;
        # echo it here (rendered inside Live) instead of to raw stdout. The
        # cursor position is rendered in place (reverse video) so editing
        # mid-line is visible.
        input_line = Text("You › ", style="bold cyan")
        cursor = max(0, min(self._cursor, len(self._input)))
        before, at, after = (
            self._input[:cursor],
            self._input[cursor : cursor + 1],
            self._input[cursor + 1 :],
        )
        input_line.append(before)
        if at:
            input_line.append(at, style="reverse")
            input_line.append(after)
        else:
            input_line.append("▌", style="reverse")  # cursor at end
        rows: list[Any] = [p for p in (body if self.text else None, status, input_line) if p]
        # Slash-command suggestions (when typing a "/command").
        if self._suggestions:
            shown = self._suggestions[:8]
            hint = "  ".join(shown)
            if len(self._suggestions) > len(shown):
                hint += f"  … (+{len(self._suggestions) - len(shown)})"
            rows.append(Text(f"  {hint}", style="dim cyan"))
        return Group(*rows)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._renderable())

    def write(self, text: str) -> None:
        self.text += normalize_terminal_output(text)
        self._refresh()

    def set_input(
        self, text: str, cursor: int | None = None, suggestions: list[str] | None = None
    ) -> None:
        """Update the live input affordance (text + cursor + command suggestions)."""
        self._input = text
        self._cursor = len(text) if cursor is None else cursor
        self._suggestions = suggestions or []
        self._refresh()

    def tick(self) -> None:
        """Advance the spinner / elapsed timer (called on a timer while busy)."""
        self._frame += 1
        self._refresh()

    def finalize(self) -> None:
        """Drop the status / input lines, leaving only the rendered content."""
        self._done = True
        self._refresh()


class ToolOutputWriter:
    """Streams incremental shell output as an indented block inside a Rich Live.

    Opened by :meth:`ChatUI.tool_stream` — model text and tool output are
    visually distinct (mirrors pi-mono's "tool execution component" concept).
    Each :meth:`write` call appends text and forces a Live refresh. On exit the
    block is finalized (border closed) and stays in the transcript.
    """

    def __init__(self, console: Console, tool_name: str, live: "Live | None") -> None:
        self._console = console
        self._tool_name = tool_name
        self._live = live
        self._lines: list[str] = []
        self._done = False

    def _renderable(self) -> Any:
        from rich.syntax import Syntax
        from rich.text import Text

        header = Text(f"▶ {self._tool_name}", style="bold yellow")
        content_text = "".join(self._lines) if self._lines else ""
        if content_text:
            body: Any = Syntax(content_text, "text", theme="ansi_dark", word_wrap=True)
        else:
            body = Text("  …", style="dim")
        return Panel(body, title=header, border_style="yellow dim", expand=False)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._renderable())

    def write(self, chunk: str) -> None:
        """Append *chunk* to the tool output block and refresh the Live display."""
        self._lines.append(normalize_terminal_output(chunk))
        self._refresh()

    def __enter__(self) -> "ToolOutputWriter":
        return self

    def __exit__(self, *args: Any) -> None:
        self._done = True
        # Flush to console when no Live context is active (non-interactive paths).
        if self._live is None and self._lines:
            self._console.print(
                f"[bold yellow]▶ {self._tool_name}[/]\n" + "".join(self._lines),
                style="dim",
            )


class ChatUI:
    """Chat interface with message display."""

    def __init__(
        self,
        title: str = "Chat",
        theme: Theme | None = None,
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
            print_markdown_safely(
                message,
                renderer=Markdown,
                printer=self.console.print,
            )
        else:
            self.console.print(f"{prefix}{normalize_terminal_output(message)}")

    def assistant(self, message: str) -> None:
        """Display assistant message.

        Args:
            message: Assistant message
        """
        timestamp = self._format_timestamp()
        prefix = f"{timestamp}[bold {self.theme.assistant_color}]Assistant:[/] "

        if self.markdown_mode:
            self.console.print(prefix, end="")
            print_markdown_safely(
                message,
                renderer=Markdown,
                printer=self.console.print,
            )
        else:
            self.console.print(f"{prefix}{normalize_terminal_output(message)}")

    @contextmanager
    def assistant_stream(self) -> Any:
        """Stream assistant response.

        Yields:
            StreamWriter for writing chunks
        """
        timestamp = self._format_timestamp()
        prefix = f"{timestamp}[bold {self.theme.assistant_color}]Assistant:[/] "

        writer = StreamWriter(self.console, prefix, self.theme.assistant_color)
        yield writer

    @contextmanager
    def assistant_stream_markdown(self, refresh_per_second: int = 8) -> Any:
        """Stream an assistant response, live-rendering it as Markdown.

        Prints the ``Assistant:`` prefix, then drives a throttled Rich ``Live``
        that re-renders the accumulated Markdown as tokens arrive. Yields a
        MarkdownStreamWriter; the rendered text remains on screen on exit.

        Yields:
            MarkdownStreamWriter for writing chunks
        """
        timestamp = self._format_timestamp()
        self.console.print(f"{timestamp}[bold {self.theme.assistant_color}]Assistant:[/]")

        writer = MarkdownStreamWriter()
        live = Live(
            writer._renderable(),
            console=self.console,
            refresh_per_second=refresh_per_second,
            vertical_overflow="visible",
        )
        writer._live = live
        live.start()
        try:
            yield writer
        finally:
            # Drop the status line and render the final, complete Markdown.
            writer.finalize()
            live.refresh()
            live.stop()

    @contextmanager
    def tool_stream(self, tool_name: str) -> Any:
        """Open an independent tool-output block during a streaming turn.

        Yields a :class:`ToolOutputWriter` whose :meth:`~ToolOutputWriter.write`
        method appends incremental text (e.g. live ``run_command`` stdout) to an
        indented block that is visually separate from the surrounding model text.

        Must be called while a ``Live`` context is already running (i.e. inside
        ``assistant_stream_markdown``). When called outside a Live (tests, JSON
        mode) it falls back to plain console printing.

        Example::

            with ui.assistant_stream_markdown() as md_writer:
                async for chunk in agent.respond_stream(prompt):
                    if isinstance(chunk, str):
                        md_writer.write(chunk)
                # tool output appears inline during execution:
                with ui.tool_stream("run_command") as tw:
                    await registry.execute(tool_call, on_update=tw.write)

        Args:
            tool_name: Name of the tool being executed (shown in block header).
        """
        writer = ToolOutputWriter(self.console, tool_name, live=None)
        yield writer

    def system(self, message: str) -> None:
        """Display system message.

        Args:
            message: System message
        """
        timestamp = self._format_timestamp()
        self.console.print(
            f"{timestamp}[{self.theme.system_color}]System: {normalize_terminal_output(message)}[/]"
        )

    def error(self, message: str) -> None:
        """Display error message.

        Args:
            message: Error message
        """
        timestamp = self._format_timestamp()
        self.console.print(
            f"{timestamp}[bold {self.theme.error_color}]Error: "
            f"{normalize_terminal_output(message)}[/]"
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
