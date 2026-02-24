"""Interactive prompts."""

from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.prompt import Prompt as RichPrompt, Confirm


class Prompt:
    """Interactive prompt for user input."""

    def __init__(self):
        """Initialize prompt."""
        self.console = Console()

    def ask(
        self,
        question: str,
        default: Optional[str] = None,
        password: bool = False,
        choices: Optional[list[str]] = None,
    ) -> str:
        """Ask for user input.

        Args:
            question: Question to ask
            default: Default value
            password: Hide input (for passwords)
            choices: List of valid choices

        Returns:
            User input
        """
        return RichPrompt.ask(
            question,
            default=default,
            password=password,
            choices=choices,
            console=self.console,
        )

    def confirm(self, question: str, default: bool = False) -> bool:
        """Ask for yes/no confirmation.

        Args:
            question: Question to ask
            default: Default answer

        Returns:
            User confirmation
        """
        return Confirm.ask(question, default=default, console=self.console)

    def choice(self, question: str, choices: list[str]) -> str:
        """Ask user to choose from options.

        Args:
            question: Question to ask
            choices: List of choices

        Returns:
            Selected choice
        """
        return RichPrompt.ask(question, choices=choices, console=self.console)


class InteractivePrompt:
    """Interactive prompt with tab completion and persistent history.

    Uses prompt_toolkit for:
    - /command tab completion
    - @file reference completion
    - Up/down arrow history (persisted to disk)
    """

    def __init__(
        self,
        commands: List[str],
        workspace: str = ".",
        history_file: Optional[str] = None,
    ):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory, InMemoryHistory
        from .advanced import PyCodeCompleter

        self.completer = PyCodeCompleter(commands=commands, workspace=workspace)

        if history_file:
            history_path = Path(history_file)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history = FileHistory(str(history_path))
        else:
            history = InMemoryHistory()

        self.session = PromptSession(
            completer=self.completer,
            history=history,
            complete_while_typing=False,
        )

    def ask(self, prompt_text: str = "You> ") -> str:
        """Get user input with completion and history.

        Args:
            prompt_text: Prompt string shown to user

        Returns:
            User input string
        """
        return self.session.prompt(prompt_text)
