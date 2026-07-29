"""Progress indicators."""

from types import TracebackType
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, SpinnerColumn, TaskID, TaskProgressColumn, TextColumn
from rich.progress import Progress as RichProgress
from typing_extensions import Self


class Progress:
    """Progress bar for long-running tasks."""

    def __init__(self) -> None:
        """Initialize progress bar."""
        self.progress = RichProgress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        )

    def __enter__(self) -> Self:
        """Enter context."""
        self.progress.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit context."""
        self.progress.__exit__(exc_type, exc_value, traceback)

    def add_task(self, description: str, total: float | None = 100) -> TaskID:
        """Add a task to track.

        Args:
            description: Task description
            total: Total steps

        Returns:
            Task ID
        """
        return self.progress.add_task(description, total=total)

    def update(self, task_id: TaskID, advance: float = 1, **kwargs: Any) -> None:
        """Update task progress.

        Args:
            task_id: Task ID
            advance: Steps to advance
            **kwargs: Additional update parameters
        """
        self.progress.update(task_id, advance=advance, **kwargs)


class Spinner:
    """Spinner for indeterminate progress."""

    def __init__(self, message: str = "Loading...") -> None:
        """Initialize spinner.

        Args:
            message: Message to display
        """
        self.message = message
        self.console = Console()
        self.progress: RichProgress | None = None

    def __enter__(self) -> Self:
        """Enter context."""
        self.progress = RichProgress(
            SpinnerColumn(),
            TextColumn(self.message),
        )
        progress = self.progress
        progress.__enter__()
        progress.add_task(self.message)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit context."""
        if self.progress:
            self.progress.__exit__(exc_type, exc_value, traceback)
