"""Progress indicators."""

from typing import Optional
from rich.progress import Progress as RichProgress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console


class Progress:
    """Progress bar for long-running tasks."""

    def __init__(self):
        """Initialize progress bar."""
        self.progress = RichProgress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        )

    def __enter__(self):
        """Enter context."""
        self.progress.__enter__()
        return self

    def __exit__(self, *args):
        """Exit context."""
        self.progress.__exit__(*args)

    def add_task(self, description: str, total: Optional[int] = 100):
        """Add a task to track.

        Args:
            description: Task description
            total: Total steps

        Returns:
            Task ID
        """
        return self.progress.add_task(description, total=total)

    def update(self, task_id, advance: int = 1, **kwargs):
        """Update task progress.

        Args:
            task_id: Task ID
            advance: Steps to advance
            **kwargs: Additional update parameters
        """
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """Spinner for indeterminate progress."""

    def __init__(self, message: str = "Loading..."):
        """Initialize spinner.

        Args:
            message: Message to display
        """
        self.message = message
        self.console = Console()
        self.progress = None

    def __enter__(self):
        """Enter context."""
        self.progress = RichProgress(
            SpinnerColumn(),
            TextColumn(self.message),
        )
        self.progress.__enter__()
        self.progress.add_task(self.message)
        return self

    def __exit__(self, *args):
        """Exit context."""
        if self.progress:
            self.progress.__exit__(*args)
