"""Advanced TUI components."""

from pathlib import Path
from typing import List, Optional, Callable
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.validation import Validator, ValidationError
from rich.console import Console
from rich.table import Table

# Directories to skip during file completion
_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info", "htmlcov",
}


class AutoCompleter(Completer):
    """Autocomplete for prompts."""

    def __init__(self, choices: List[str]):
        """Initialize autocompleter.

        Args:
            choices: List of completion choices
        """
        self.choices = choices

    def get_completions(self, document, complete_event):
        """Get completions for current text.

        Args:
            document: Current document
            complete_event: Completion event

        Yields:
            Completion objects
        """
        word = document.get_word_before_cursor()

        for choice in self.choices:
            if choice.startswith(word):
                yield Completion(
                    choice,
                    start_position=-len(word),
                    display=choice,
                )


class FileCompleter(Completer):
    """File path autocomplete."""

    def __init__(self, base_path: str = "."):
        """Initialize file completer.

        Args:
            base_path: Base directory for file completion
        """
        from pathlib import Path
        self.base_path = Path(base_path)

    def get_completions(self, document, complete_event):
        """Get file path completions."""
        from pathlib import Path

        word = document.get_word_before_cursor()

        try:
            if "/" in word or "\\" in word:
                # Path completion
                path_part = Path(word)
                if path_part.is_absolute():
                    search_dir = path_part.parent if not path_part.is_dir() else path_part
                else:
                    search_dir = self.base_path / path_part.parent
            else:
                search_dir = self.base_path

            if search_dir.exists():
                for item in sorted(search_dir.iterdir()):
                    name = item.name
                    if name.startswith(word.split("/")[-1] if "/" in word else word):
                        display = f"{name}/" if item.is_dir() else name
                        yield Completion(
                            name,
                            start_position=-len(word.split("/")[-1] if "/" in word else word),
                            display=display,
                        )
        except Exception:
            pass


class PyCodeCompleter(Completer):
    """Context-aware completer for interactive coding agent.

    Handles:
    - /command tab completion
    - @file reference completion
    """

    def __init__(self, commands: List[str], workspace: str = "."):
        self.commands = sorted(commands)
        self.workspace = Path(workspace)

    def _iter_workspace_files(self, prefix: str = ""):
        """Yield relative file paths in workspace, skipping ignored dirs."""
        try:
            base = self.workspace / prefix if prefix else self.workspace
            if not base.exists():
                return
            for item in sorted(base.iterdir()):
                if item.name.startswith(".") or item.name in _IGNORE_DIRS:
                    continue
                rel = str(item.relative_to(self.workspace))
                if item.is_dir():
                    yield rel + "/"
                else:
                    yield rel
        except OSError:
            pass

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Slash command completion
        if text.startswith("/"):
            for cmd in self.commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
            return

        # @file reference completion
        at_pos = text.rfind("@")
        if at_pos >= 0:
            partial = text[at_pos + 1:]
            # Determine directory prefix for narrowing search
            if "/" in partial:
                dir_prefix = partial.rsplit("/", 1)[0]
                file_prefix = partial.rsplit("/", 1)[1]
            else:
                dir_prefix = ""
                file_prefix = partial

            for rel_path in self._iter_workspace_files(dir_prefix):
                name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
                full_rel = rel_path
                if full_rel.startswith(partial) or name.startswith(file_prefix):
                    yield Completion(
                        full_rel,
                        start_position=-len(partial),
                        display=full_rel,
                    )



class MultiSelect:
    """Multi-select checkbox list."""

    def __init__(self, title: str, choices: List[str]):
        """Initialize multi-select.

        Args:
            title: Selection title
            choices: List of choices
        """
        self.title = title
        self.choices = choices
        self.selected = set()

    def show(self) -> List[str]:
        """Show selection UI and get results.

        Returns:
            List of selected items
        """
        from rich.prompt import Prompt
        console = Console()

        console.print(f"\n[bold]{self.title}[/bold]")
        console.print("[dim]Enter numbers separated by spaces (e.g., 1 3 5)[/dim]\n")

        # Display choices
        for i, choice in enumerate(self.choices, 1):
            console.print(f"{i}. {choice}")

        console.print()

        # Get selection
        selection = Prompt.ask("Select items", default="")

        # Parse selection
        if not selection:
            return []

        try:
            indices = [int(x.strip()) - 1 for x in selection.split()]
            selected = [
                self.choices[i] for i in indices if 0 <= i < len(self.choices)
            ]
            return selected
        except ValueError:
            console.print("[red]Invalid selection[/red]")
            return []


class InteractiveTable:
    """Interactive table with selection."""

    def __init__(self, title: str):
        """Initialize interactive table.

        Args:
            title: Table title
        """
        self.title = title
        self.table = Table(title=title)
        self.rows = []

    def add_column(self, name: str, **kwargs):
        """Add a column.

        Args:
            name: Column name
            **kwargs: Rich Table column kwargs
        """
        self.table.add_column(name, **kwargs)

    def add_row(self, *values):
        """Add a row.

        Args:
            *values: Row values
        """
        self.rows.append(values)
        self.table.add_row(*[str(v) for v in values])

    def show(self) -> None:
        """Display the table."""
        console = Console()
        console.print(self.table)

    def select_row(self) -> Optional[int]:
        """Show table and let user select a row.

        Returns:
            Selected row index or None
        """
        from rich.prompt import Prompt
        console = Console()

        self.show()

        if not self.rows:
            return None

        try:
            selection = Prompt.ask(f"Select row (1-{len(self.rows)})")
            index = int(selection) - 1

            if 0 <= index < len(self.rows):
                return index
        except ValueError:
            pass

        return None


def prompt_with_autocomplete(
    question: str,
    choices: Optional[List[str]] = None,
    file_completion: bool = False,
    base_path: str = ".",
) -> str:
    """Prompt with autocomplete support.

    Args:
        question: Question to ask
        choices: List of choices for completion (if any)
        file_completion: Enable file path completion
        base_path: Base path for file completion

    Returns:
        User input
    """
    completer = None

    if file_completion:
        completer = FileCompleter(base_path)
    elif choices:
        completer = AutoCompleter(choices)

    result = pt_prompt(
        f"{question}: ",
        completer=completer,
    )

    return result
