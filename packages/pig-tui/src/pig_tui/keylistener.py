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


def _longest_common_prefix(items: list[str]) -> str:
    if not items:
        return ""
    prefix = items[0]
    for item in items[1:]:
        while not item.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


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
        on_change: Callable[[str, int, list[str]], None] | None = None,
        completions: list[str] | None = None,
        echo: bool = True,
    ) -> None:
        self._cancel = cancel_event
        self._on_steering = on_steering
        self._on_change = on_change
        self._completions = completions or []
        self._echo = echo
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = None
        self._stop = None
        self._line: list[str] = []
        self._cursor = 0  # insertion index into _line
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
        import codecs
        import os
        import select

        # Decode bytes incrementally so multibyte (e.g. CJK) input is assembled
        # into complete characters instead of being dropped per byte.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")

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
                # A lone Esc aborts; Esc followed by more bytes is an escape
                # sequence (arrow keys / Home / End / Delete) — parse it for
                # cursor movement rather than discarding it.
                more, _, _ = select.select([fd], [], [], 0.0)
                if more:
                    try:
                        seq = os.read(fd, 8)
                    except OSError:
                        seq = b""
                    self._handle_escape_seq(seq.decode("ascii", errors="ignore"))
                    continue
                self._fire_abort()
                continue
            # Feed the byte to the incremental decoder; emit complete characters.
            for char in decoder.decode(ch):
                self._handle_char(char)

    def _reader_windows(self) -> None:
        import msvcrt
        import time

        # Windows scan-code (after \x00/\xe0) -> navigation action.
        nav = {"K": "left", "M": "right", "G": "home", "O": "end", "S": "delete"}
        while self._stop is None or not self._stop.is_set():
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            ch = msvcrt.getwch()  # already a (wide) character
            if ch == "\x1b":
                self._fire_abort()
                continue
            if ch in ("\x00", "\xe0"):  # special key: next char is the scan code
                code = msvcrt.getwch()
                action = nav.get(code)
                if action:
                    self._move_cursor(action)
                continue
            self._handle_char(ch)

    # -- key handling -------------------------------------------------------

    def _handle_char(self, char: str) -> None:
        if char in ("\r", "\n"):  # Enter — submit
            line = "".join(self._line).strip()
            self._line.clear()
            self._cursor = 0
            if line and self._on_steering is not None:
                self._fire_steering(line)
            self._fire_change()
            return
        if char in ("\x7f", "\x08"):  # Backspace — delete before cursor
            if self._cursor > 0:
                del self._line[self._cursor - 1]
                self._cursor -= 1
                self._fire_change()
            return
        if char == "\x01":  # Ctrl-A — home
            self._move_cursor("home")
            return
        if char == "\x05":  # Ctrl-E — end
            self._move_cursor("end")
            return
        if char == "\x15":  # Ctrl-U — clear the line
            if self._line:
                self._line.clear()
                self._cursor = 0
                self._fire_change()
            return
        if char == "\x17":  # Ctrl-W — delete the word before the cursor
            self._delete_word_before_cursor()
            return
        if char == "\t":  # Tab — complete a leading slash-command
            self._complete()
            return
        if not char.isprintable():
            return
        self._line.insert(self._cursor, char)  # insert at cursor
        self._cursor += 1
        self._fire_change()

    def _handle_escape_seq(self, seq: str) -> None:
        action = {
            "[D": "left",
            "OD": "left",
            "[C": "right",
            "OC": "right",
            "[H": "home",
            "OH": "home",
            "[1~": "home",
            "[F": "end",
            "OF": "end",
            "[4~": "end",
            "[3~": "delete",
        }.get(seq)
        if action:
            self._move_cursor(action)

    def _move_cursor(self, action: str) -> None:
        if action == "left":
            self._cursor = max(0, self._cursor - 1)
        elif action == "right":
            self._cursor = min(len(self._line), self._cursor + 1)
        elif action == "home":
            self._cursor = 0
        elif action == "end":
            self._cursor = len(self._line)
        elif action == "delete":  # forward delete (Del key)
            if self._cursor < len(self._line):
                del self._line[self._cursor]
        else:
            return
        self._fire_change()

    def _delete_word_before_cursor(self) -> None:
        i = self._cursor
        while i > 0 and self._line[i - 1].isspace():  # skip trailing spaces
            i -= 1
        while i > 0 and not self._line[i - 1].isspace():  # then the word
            i -= 1
        if i != self._cursor:
            del self._line[i : self._cursor]
            self._cursor = i
            self._fire_change()

    def matching_completions(self) -> list[str]:
        """Slash-commands matching the current line (only when it starts with '/')."""
        line = "".join(self._line)
        if not line.startswith("/") or " " in line:
            return []
        return [c for c in self._completions if c.startswith(line)]

    def _complete(self) -> None:
        """Tab-complete the current slash-command to the longest common prefix."""
        matches = self.matching_completions()
        if not matches:
            return
        if len(matches) == 1:
            completed = matches[0] + " "
        else:
            completed = _longest_common_prefix(matches)
        if completed and completed != "".join(self._line):
            self._line = list(completed)
            self._cursor = len(self._line)
            self._fire_change()

    def _fire_abort(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._cancel.set)

    def _fire_steering(self, line: str) -> None:
        if self._loop is not None and self._on_steering is not None:
            self._loop.call_soon_threadsafe(self._on_steering, line)

    def _fire_change(self) -> None:
        if self._loop is not None and self._on_change is not None:
            current = "".join(self._line)
            cursor = self._cursor
            suggestions = self.matching_completions()
            self._loop.call_soon_threadsafe(self._on_change, current, cursor, suggestions)
