"""Platform-layer presenter built on top of ChatUI-compatible surfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .core import PanelContent, StatusMessage


class ChatLikeUI(Protocol):
    def panel(self, content: str, title: str = "") -> None: ...
    def system(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


class ChatPresenter:
    """Small platform adapter that separates view data from ChatUI calls."""

    def __init__(self, ui_provider: Callable[[], ChatLikeUI]) -> None:
        self._ui_provider = ui_provider

    @property
    def ui(self) -> ChatLikeUI:
        return self._ui_provider()

    def show_panel(self, panel: PanelContent) -> None:
        self.ui.panel(panel.content, title=panel.title)

    def show_status(self, status: StatusMessage) -> None:
        self.ui.system(f"[{status.kind}] {status.message}")

    def show_error(self, message: str) -> None:
        self.ui.error(message)
