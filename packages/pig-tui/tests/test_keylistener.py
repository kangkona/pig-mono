"""Tests for the streaming-time key listener."""

import asyncio

import pytest
from pig_tui.keylistener import LiveInputListener


@pytest.mark.asyncio
async def test_listener_is_noop_when_stdin_not_a_tty():
    # Under pytest stdin is not an interactive TTY, so the listener must degrade
    # to a no-op (no raw mode, no thread) rather than corrupting the terminal.
    cancel = asyncio.Event()
    async with LiveInputListener(cancel) as listener:
        assert listener._active is False
        assert listener._thread is None
    assert not cancel.is_set()


@pytest.mark.asyncio
async def test_esc_byte_sets_cancel_event():
    cancel = asyncio.Event()
    listener = LiveInputListener(cancel, echo=False)
    listener._loop = asyncio.get_running_loop()

    listener._fire_abort()  # what the reader calls when it reads a lone Esc
    await asyncio.sleep(0.01)

    assert cancel.is_set()


@pytest.mark.asyncio
async def test_typed_line_then_enter_fires_steering():
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in b"do X":
        listener._handle_byte(bytes([ch]))
    listener._handle_byte(b"\r")  # Enter submits the line
    await asyncio.sleep(0.01)

    assert received == ["do X"]
    assert not cancel.is_set()  # typing is steering, not abort


@pytest.mark.asyncio
async def test_backspace_edits_line_before_submit():
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in b"hix":
        listener._handle_byte(bytes([ch]))
    listener._handle_byte(b"\x7f")  # backspace removes the 'x'
    listener._handle_byte(b"\r")
    await asyncio.sleep(0.01)

    assert received == ["hi"]


@pytest.mark.asyncio
async def test_blank_line_does_not_fire_steering():
    cancel = asyncio.Event()
    received: list[str] = []
    listener = LiveInputListener(cancel, on_steering=received.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    listener._handle_byte(b"\r")  # Enter on an empty line
    await asyncio.sleep(0.01)

    assert received == []


@pytest.mark.asyncio
async def test_on_change_emits_live_buffer():
    """Typing fires on_change with the current buffer (for live echo in the UI)."""
    seen: list[str] = []
    listener = LiveInputListener(asyncio.Event(), on_change=seen.append, echo=False)
    listener._loop = asyncio.get_running_loop()

    for ch in b"hey":
        listener._handle_byte(bytes([ch]))
    listener._handle_byte(b"\x7f")  # backspace
    await asyncio.sleep(0.01)

    assert seen[-1] == "he"


@pytest.mark.asyncio
async def test_enter_clears_buffer_via_on_change():
    received: list[str] = []
    changes: list[str] = []
    listener = LiveInputListener(
        asyncio.Event(), on_steering=received.append, on_change=changes.append, echo=False
    )
    listener._loop = asyncio.get_running_loop()

    for ch in b"go":
        listener._handle_byte(bytes([ch]))
    listener._handle_byte(b"\r")
    await asyncio.sleep(0.01)

    assert received == ["go"]
    assert changes[-1] == ""  # buffer cleared after submit
