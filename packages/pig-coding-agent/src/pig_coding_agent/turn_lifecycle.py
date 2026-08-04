"""Coordinate active turns with session and tree transitions."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal


class ActiveTurnTransitionError(RuntimeError):
    """Raised when a state transition races an active agent turn."""


@dataclass(frozen=True)
class ActiveTurnToken:
    """Generation token used to finish the same lifecycle lease."""

    generation: int
    owner: object
    kind: Literal["turn", "transition"]


class ActiveTurnLifecycle:
    """Serialize turns and transitions through their full persistence boundaries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._kind: Literal["turn", "transition"] | None = None
        self._owner: object | None = None
        self._transition_depth = 0
        self._completion: threading.Event | None = None
        self._cancel: asyncio.Event | None = None
        self._cancel_loop: asyncio.AbstractEventLoop | None = None

    @staticmethod
    def _async_context() -> tuple[asyncio.Task[object] | None, asyncio.AbstractEventLoop | None]:
        try:
            return asyncio.current_task(), asyncio.get_running_loop()
        except RuntimeError:
            return None, None

    @classmethod
    def _current_owner(cls) -> object:
        task, _ = cls._async_context()
        return task if task is not None else threading.current_thread()

    @staticmethod
    def _request_cancel_snapshot(
        cancel: asyncio.Event | None,
        loop: asyncio.AbstractEventLoop | None,
    ) -> bool:
        if cancel is None:
            return False
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if loop is not None and loop.is_running() and current_loop is not loop:
            loop.call_soon_threadsafe(cancel.set)
        else:
            cancel.set()
        return True

    @property
    def is_active(self) -> bool:
        """Return whether a registered agent turn is running or flushing."""
        with self._lock:
            return self._kind == "turn"

    def begin(self, cancel: asyncio.Event | None = None) -> ActiveTurnToken:
        """Acquire the exclusive turn lease for the current task or thread."""
        task, loop = self._async_context()
        owner = task if task is not None else threading.current_thread()
        with self._lock:
            if self._kind is not None:
                if self._kind == "transition":
                    raise ActiveTurnTransitionError(
                        "Cannot start an agent turn while a session transition is in progress"
                    )
                raise RuntimeError("Another agent turn is already active")
            self._generation += 1
            token = ActiveTurnToken(self._generation, owner, "turn")
            self._kind = "turn"
            self._owner = owner
            self._completion = threading.Event()
            self._cancel = cancel
            self._cancel_loop = loop if cancel is not None else None
            return token

    def end(self, token: ActiveTurnToken) -> None:
        """Release the matching turn lease after final persistence."""
        with self._lock:
            if (
                self._kind != "turn"
                or self._generation != token.generation
                or self._owner is not token.owner
            ):
                return
            completion = self._completion
            self._kind = None
            self._owner = None
            self._completion = None
            self._cancel = None
            self._cancel_loop = None
        if completion is not None:
            completion.set()

    def _begin_transition(self, action: str) -> ActiveTurnToken:
        owner = self._current_owner()
        with self._lock:
            if self._kind is None:
                self._generation += 1
                token = ActiveTurnToken(self._generation, owner, "transition")
                self._kind = "transition"
                self._owner = owner
                self._transition_depth = 1
                return token
            if self._kind == "transition" and self._owner is owner:
                self._transition_depth += 1
                return ActiveTurnToken(self._generation, owner, "transition")
            cancel = self._cancel if self._kind == "turn" else None
            loop = self._cancel_loop if self._kind == "turn" else None
        cancellation_requested = self._request_cancel_snapshot(cancel, loop)
        guidance = (
            "cancellation was requested, retry after the turn finishes"
            if cancellation_requested
            else "retry after the turn finishes"
        )
        raise ActiveTurnTransitionError(
            f"Cannot {action} while an active turn is flushing; {guidance}"
        )

    def _end_transition(self, token: ActiveTurnToken) -> None:
        with self._lock:
            if (
                self._kind != "transition"
                or self._generation != token.generation
                or self._owner is not token.owner
            ):
                return
            self._transition_depth -= 1
            if self._transition_depth > 0:
                return
            self._kind = None
            self._owner = None
            self._transition_depth = 0

    @contextmanager
    def transition(self, action: str) -> Iterator[None]:
        """Hold an exclusive, re-entrant lease around transition side effects."""
        token = self._begin_transition(action)
        try:
            yield
        finally:
            self._end_transition(token)

    def require_idle(self, action: str = "change session state") -> None:
        """Probe the transition lease without leaving a race window."""
        with self.transition(action):
            return

    def request_cancel(self) -> bool:
        """Request cancellation for one captured turn generation only."""
        with self._lock:
            if self._kind != "turn":
                return False
            cancel = self._cancel
            loop = self._cancel_loop
        return self._request_cancel_snapshot(cancel, loop)

    async def cancel_and_wait(self) -> None:
        """Cancel one captured turn generation and await its persistence flush."""
        with self._lock:
            if self._kind != "turn":
                return
            owner = self._owner
            completion = self._completion
            cancel = self._cancel
            loop = self._cancel_loop
        if owner is None or completion is None:
            return
        self._request_cancel_snapshot(cancel, loop)
        if owner is self._current_owner():
            raise ActiveTurnTransitionError(
                "The active turn cannot wait for itself to finish flushing"
            )
        await asyncio.to_thread(completion.wait)
