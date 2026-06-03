"""Concurrent key listener active while the agent is streaming.

While a turn runs, the normal line editor (prompt_toolkit) is not active, so
nothing would observe the keyboard. This listener fills that gap so the user
can:

- press **Esc** to abort the current turn (sets the cancellation event), and
- type a line + **Enter** to inject a steering message picked up before the
  next model call.

It is intentionally minimal and best-effort: it uses cbreak mode (so Ctrl-C
still raises SIGINT as the abort fallback) and degrades to a no-op when stdin
is not an interactive TTY (piped input, json/rpc modes, unsupported platforms).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable

_ESC = b"\x1b"
_ENTER = (b"\r", b"\n")
_BACKSPACE = (b"\x7f", b"\x08")


def _stdin_is_interactive() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except (ValueError, OSError):
        return False


class LiveInputListener:
    """Async context manager that watches the keyboard during a streaming turn.

    Args:
        cancel_event: set when the user presses Esc (turn abort).
        on_steering: called (on the event loop) with a typed line when the user
            presses Enter; typically enqueues a steering message.
        echo: write typed characters back to the terminal for visual feedback.
    """

    def __init__(
        self,
        cancel_event: asyncio.Event,
        on_steering: Callable[[str], None] | None = None,
        *,
        echo: bool = True,
    ) -> None:
        self._cancel = cancel_event
        self._on_steering = on_steering
        self._echo = echo
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = None
        self._stop = None
        self._line: list[str] = []
        # Platform backend, resolved on enter.
        self._fd: int | None = None
        self._old_termios = None
        self._active = False

    async def __aenter__(self) -> LiveInputListener:
        if not _stdin_is_interactive():
            return self  # no-op fallback (Ctrl-C still aborts via Stage-4 handler)

        self._loop = asyncio.get_running_loop()
        import threading

        self._stop = threading.Event()

        if sys.platform == "win32":
            started = self._start_windows()
        else:
            started = self._start_unix()

        if started:
            self._active = True
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
        return self

    async def __aexit__(self, *exc) -> None:
        if not self._active:
            return
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._restore()
        self._active = False

    # -- platform setup -----------------------------------------------------

    def _start_unix(self) -> bool:
        try:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old_termios = termios.tcgetattr(self._fd)
            # cbreak (not raw): keep ISIG so Ctrl-C/Ctrl-Z still work as signals.
            tty.setcbreak(self._fd)
            return True
        except Exception:
            self._fd = None
            self._old_termios = None
            return False

    def _start_windows(self) -> bool:
        try:
            import msvcrt  # noqa: F401

            return True
        except Exception:
            return False

    def _restore(self) -> None:
        if self._old_termios is not None and self._fd is not None:
            try:
                import termios

                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_termios)
            except Exception:
                pass
        self._old_termios = None
        self._fd = None

    # -- reader loop --------------------------------------------------------

    def _reader(self) -> None:
        if sys.platform == "win32":
            self._reader_windows()
        else:
            self._reader_unix()

    def _reader_unix(self) -> None:
        import os
        import select

        fd = self._fd
        assert fd is not None
        while self._stop is None or not self._stop.is_set():
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            try:
                ch = os.read(fd, 1)
            except OSError:
                break
            if not ch:
                break
            if ch == _ESC:
                # Distinguish a lone Esc (abort) from an escape sequence such as
                # an arrow key (Esc + "[A"): if more bytes are immediately
                # available, drain and ignore the sequence.
                more, _, _ = select.select([fd], [], [], 0.0)
                if more:
                    try:
                        os.read(fd, 8)  # discard the rest of the sequence
                    except OSError:
                        pass
                    continue
                self._fire_abort()
                continue
            self._handle_byte(ch)

    def _reader_windows(self) -> None:
        import msvcrt
        import time

        while self._stop is None or not self._stop.is_set():
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            ch = msvcrt.getwch()
            b = ch.encode("utf-8", errors="ignore")
            if b == _ESC:
                self._fire_abort()
                continue
            self._handle_byte(b)

    # -- key handling -------------------------------------------------------

    def _handle_byte(self, ch: bytes) -> None:
        if ch in _ENTER:
            line = "".join(self._line).strip()
            self._line.clear()
            if self._echo:
                sys.stdout.write("\n")
                sys.stdout.flush()
            if line and self._on_steering is not None:
                self._fire_steering(line)
            return
        if ch in _BACKSPACE:
            if self._line:
                self._line.pop()
                if self._echo:
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            return
        try:
            text = ch.decode("utf-8")
        except UnicodeDecodeError:
            return
        if not text.isprintable():
            return
        self._line.append(text)
        if self._echo:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _fire_abort(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._cancel.set)

    def _fire_steering(self, line: str) -> None:
        if self._loop is not None and self._on_steering is not None:
            self._loop.call_soon_threadsafe(self._on_steering, line)
