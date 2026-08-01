"""Tests for the streaming-time key listener."""

import asyncio
from unittest.mock import Mock, patch

import pytest
from pig_tui.keylistener import LiveInputListener


@pytest.mark.asyncio
async def test_listener_is_noop_when_stdin_not_a_tty() -> None:
    # Under pytest stdin is not an interactive TTY, so the listener must degrade
    # to a no-op (no raw mode, no thread) rather than corrupting the terminal.
    cancel = asyncio.Event()
    async with LiveInputListener(cancel) as listener:
        assert listener._active is False
        assert listener._thread is None
    assert not cancel.is_set()


def test_listener_suspend_and_resume_release_terminal_reader() -> None:
    listener = LiveInputListener(asyncio.Event())
    stop = Mock()
    thread = Mock()
    listener._stop = stop
    listener._thread = thread
    listener._active = True

    with patch.object(listener, "_restore") as restore:
        listener.suspend()

    stop.set.assert_called_once_with()
    thread.join.assert_called_once_with(timeout=1.0)
    restore.assert_called_once_with()
    assert listener._active is False
    assert listener._resume_after_suspend is True

    with patch.object(listener, "_activate") as activate:
        listener.resume()

    activate.assert_called_once_with()
    assert listener._resume_after_suspend is False


@pytest.mark.asyncio
async def test_esc_byte_sets_cancel_event() -> None:
    cancel = asyncio.Event()
    listener = LiveInputListener(cancel, echo=False)
    listener._loop = asyncio.get_running_loop()

    listener._fire_abort()  # what the reader calls when it reads a lone Esc
    await asyncio.sleep(0.01)

    assert cancel.is_set()


@pytest.mark.asyncio
async def test_typed_line_then_enter_fires_steering() -> None:
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in "do X":
        listener._handle_char(ch)
    listener._handle_char("\r")  # Enter submits the line
    await asyncio.sleep(0.01)

    assert received == ["do X"]
    assert not cancel.is_set()  # typing is steering, not abort


@pytest.mark.asyncio
async def test_backspace_edits_line_before_submit() -> None:
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in "hix":
        listener._handle_char(ch)
    listener._handle_char("\x7f")  # backspace removes the 'x'
    listener._handle_char("\r")
    await asyncio.sleep(0.01)

    assert received == ["hi"]


@pytest.mark.asyncio
async def test_blank_line_does_not_fire_steering() -> None:
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    listener._handle_char("\r")  # Enter on an empty line
    await asyncio.sleep(0.01)

    assert received == []


@pytest.mark.asyncio
async def test_on_change_emits_live_buffer() -> None:
    """Typing fires on_change with the current buffer (for live echo in the UI)."""
    seen: list[tuple[str, int]] = []
    listener = LiveInputListener(
        asyncio.Event(), on_change=lambda t, c, sg: seen.append((t, c)), echo=False
    )
    listener._loop = asyncio.get_running_loop()

    for ch in "hey":
        listener._handle_char(ch)
    listener._handle_char("\x7f")  # backspace
    await asyncio.sleep(0.01)

    assert seen[-1] == ("he", 2)


@pytest.mark.asyncio
async def test_enter_clears_buffer_via_on_change() -> None:
    received: list[str] = []
    changes: list[str] = []
    listener = LiveInputListener(
        asyncio.Event(),
        on_steering=received.append,
        on_change=lambda t, c, sg: changes.append(t),
        echo=False,
    )
    listener._loop = asyncio.get_running_loop()

    for ch in "go":
        listener._handle_char(ch)
    listener._handle_char("\r")
    await asyncio.sleep(0.01)

    assert received == ["go"]
    assert changes[-1] == ""  # buffer cleared after submit


@pytest.mark.asyncio
async def test_multibyte_cjk_input_is_decoded_and_buffered() -> None:
    """CJK input (multi-byte UTF-8) must assemble into whole characters."""
    import codecs

    received: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    # Feed the raw UTF-8 bytes of "中文" one byte at a time, as the reader does.
    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    for byte in "中文".encode():
        for char in decoder.decode(bytes([byte])):
            listener._handle_char(char)
    listener._handle_char("\r")  # Enter
    await asyncio.sleep(0.01)

    assert received == ["中文"]


@pytest.mark.asyncio
async def test_cursor_insert_move_and_edit() -> None:
    """Arrow/Home/End move the cursor; typing inserts at the cursor."""
    submitted: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_steering=submitted.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in "helo":
        listener._handle_char(ch)
    # Move left once (between 'l' and 'o') and insert 'l' -> "hello"
    listener._move_cursor("left")
    listener._handle_char("l")
    listener._handle_char("\r")
    await asyncio.sleep(0.01)
    assert submitted == ["hello"]


@pytest.mark.asyncio
async def test_home_end_and_backspace_at_cursor() -> None:
    submitted: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_steering=submitted.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in "world":
        listener._handle_char(ch)
    listener._move_cursor("home")
    listener._handle_char("X")  # insert at start -> "Xworld"
    listener._move_cursor("end")
    listener._handle_char("\x7f")  # backspace at end -> "Xworl"
    listener._handle_char("\r")
    await asyncio.sleep(0.01)
    assert submitted == ["Xworl"]


@pytest.mark.asyncio
async def test_ctrl_u_clears_and_ctrl_w_deletes_word() -> None:
    submitted: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_steering=submitted.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in "add a feature":
        listener._handle_char(ch)
    listener._handle_char("\x17")  # Ctrl-W deletes "feature"
    listener._handle_char("\r")
    await asyncio.sleep(0.01)
    assert submitted == ["add a"]

    for ch in "throwaway":
        listener._handle_char(ch)
    listener._handle_char("\x15")  # Ctrl-U clears the line
    listener._handle_char("k")
    listener._handle_char("\r")
    await asyncio.sleep(0.01)
    assert submitted[-1] == "k"


@pytest.mark.asyncio
async def test_escape_sequence_moves_cursor_not_abort() -> None:
    cancel = asyncio.Event()
    changes: list[tuple[str, int]] = []
    listener = LiveInputListener(
        cancel, on_change=lambda t, c, sg: changes.append((t, c)), echo=False
    )
    listener._loop = asyncio.get_running_loop()

    for ch in "abc":
        listener._handle_char(ch)
    listener._handle_escape_seq("[D")  # Left arrow
    await asyncio.sleep(0.01)
    assert changes[-1] == ("abc", 2)  # cursor moved left, not aborted
    assert not cancel.is_set()


@pytest.mark.asyncio
async def test_slash_command_suggestions_emitted() -> None:
    cmds = ["/compact", "/clear", "/copy", "/cost", "/model"]
    changes: list[tuple[str, int, list[str]]] = []
    listener = LiveInputListener(
        asyncio.Event(), on_change=lambda t, c, sg: changes.append((t, c, sg)), completions=cmds
    )
    listener._loop = asyncio.get_running_loop()

    for ch in "/co":
        listener._handle_char(ch)
    await asyncio.sleep(0.01)
    assert set(changes[-1][2]) == {"/compact", "/copy", "/cost"}

    # Non-slash text yields no suggestions.
    for ch in "x":
        listener._handle_char(ch)  # now "/cox" -> no match
    await asyncio.sleep(0.01)
    assert changes[-1][2] == []


@pytest.mark.asyncio
async def test_tab_completes_unique_and_common_prefix() -> None:
    cmds = ["/compact", "/copy", "/cost", "/model"]
    submitted: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_steering=submitted.append, completions=cmds)
    listener._loop = asyncio.get_running_loop()

    # "/m" + Tab -> unique "/model " (with trailing space)
    for ch in "/m":
        listener._handle_char(ch)
    listener._complete()
    assert "".join(listener._line) == "/model "

    # "/co" + Tab is ambiguous (compact/copy/cost) -> stays at the common prefix.
    listener._line = list("/co")
    listener._cursor = 3
    listener._complete()
    assert "".join(listener._line) == "/co"  # common prefix, no unique completion
