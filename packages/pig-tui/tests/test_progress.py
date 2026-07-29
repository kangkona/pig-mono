"""Tests for progress helpers."""

from typing import Any
from unittest.mock import patch

from pig_tui.progress import Spinner
from rich.progress import TaskID


@patch("pig_tui.progress.RichProgress")
def test_spinner_uses_message_and_exits_cleanly(mock_progress_cls: Any) -> None:
    mock_progress = mock_progress_cls.return_value

    with Spinner("Working..."):
        pass

    mock_progress_cls.assert_called_once()
    mock_progress.add_task.assert_called_once_with("Working...")
    mock_progress.__enter__.assert_called_once()
    mock_progress.__exit__.assert_called_once()


@patch("pig_tui.progress.RichProgress")
def test_spinner_exits_cleanly_when_body_raises(mock_progress_cls: Any) -> None:
    mock_progress = mock_progress_cls.return_value

    try:
        with Spinner("Working..."):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    mock_progress.__enter__.assert_called_once()
    mock_progress.__exit__.assert_called_once()


@patch("pig_tui.progress.RichProgress")
def test_progress_add_task_supports_indeterminate_total(mock_progress_cls: Any) -> None:
    mock_progress = mock_progress_cls.return_value
    expected_task_id = TaskID(1)
    mock_progress.add_task.return_value = expected_task_id

    from pig_tui.progress import Progress

    with Progress() as progress:
        task_id = progress.add_task("Waiting", total=None)

    assert task_id == expected_task_id
    mock_progress.add_task.assert_called_once_with("Waiting", total=None)
