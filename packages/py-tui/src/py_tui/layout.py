"""Layout system for terminal UI."""

from typing import List, Optional
from rich.console import Console, Group
from rich.layout import Layout as RichLayout
from rich.panel import Panel
from rich.live import Live


class LayoutManager:
    """Manage terminal layout with multiple regions."""

    def __init__(self):
        """Initialize layout manager."""
        self.layout = RichLayout()
        self.console = Console()

    def split_vertical(self, name: str, *regions: str) -> None:
        """Split layout vertically.

        Args:
            name: Layout region name
            *regions: Sub-region names
        """
        self.layout[name].split_column(*[RichLayout(name=r) for r in regions])

    def split_horizontal(self, name: str, *regions: str) -> None:
        """Split layout horizontally.

        Args:
            name: Layout region name
            *regions: Sub-region names
        """
        self.layout[name].split_row(*[RichLayout(name=r) for r in regions])

    def update(self, region: str, content) -> None:
        """Update a region with new content.

        Args:
            region: Region name
            content: Content to display
        """
        self.layout[region].update(content)

    def render(self) -> None:
        """Render the layout once."""
        self.console.print(self.layout)

    def live_update(self):
        """Create a live-updating context.

        Returns:
            Live context manager
        """
        return Live(self.layout, console=self.console, refresh_per_second=10)


class StatusLine:
    """Status line display."""

    def __init__(self):
        """Initialize status line."""
        self.items = {}

    def set(self, key: str, value: str) -> None:
        """Set a status item.

        Args:
            key: Item key
            value: Item value
        """
        self.items[key] = value

    def remove(self, key: str) -> None:
        """Remove a status item.

        Args:
            key: Item key
        """
        self.items.pop(key, None)

    def render(self) -> str:
        """Render status line.

        Returns:
            Formatted status line
        """
        if not self.items:
            return ""

        parts = [f"{k}: {v}" for k, v in self.items.items()]
        return " | ".join(parts)


class Overlay:
    """Overlay panel for temporary content."""

    def __init__(self, title: str = ""):
        """Initialize overlay.

        Args:
            title: Overlay title
        """
        self.title = title
        self.content = ""
        self.visible = False

    def show(self, content: str) -> None:
        """Show overlay with content.

        Args:
            content: Content to display
        """
        self.content = content
        self.visible = True

    def hide(self) -> None:
        """Hide overlay."""
        self.visible = False

    def render(self) -> Optional[Panel]:
        """Render overlay if visible.

        Returns:
            Panel or None
        """
        if not self.visible:
            return None

        return Panel(
            self.content,
            title=self.title,
            border_style="yellow",
        )
