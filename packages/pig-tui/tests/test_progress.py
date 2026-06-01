"""Tests for progress helpers."""

from unittest.mock import patch

from pig_tui.progress import Spinner


@patch("pig_tui.progress.RichProgress")
def test_spinner_uses_message_and_exits_cleanly(mock_progress_cls):
    mock_progress = mock_progress_cls.return_value

    with Spinner("Working..."):
        pass

    mock_progress_cls.assert_called_once()
    mock_progress.add_task.assert_called_once_with("Working...")
    mock_progress.__enter__.assert_called_once()
    mock_progress.__exit__.assert_called_once()
