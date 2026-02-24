"""Shared fixtures for py-messenger tests."""

import pytest


@pytest.fixture
def slack_event_mention():
    """A Slack app_mention event."""
    return {
        "type": "app_mention",
        "user": "U_USER1",
        "text": "<@U_BOT> review this code",
        "ts": "1700000000.000100",
        "channel": "C_GENERAL",
        "event_ts": "1700000000.000100",
    }


@pytest.fixture
def slack_event_dm():
    """A Slack DM event."""
    return {
        "type": "message",
        "user": "U_USER1",
        "text": "hello bot",
        "ts": "1700000001.000200",
        "channel": "D_DM_CHAN",
        "channel_type": "im",
    }


@pytest.fixture
def slack_event_with_file():
    """A Slack message with file attachment."""
    return {
        "type": "message",
        "user": "U_USER1",
        "text": "<@U_BOT> check this file",
        "ts": "1700000002.000300",
        "channel": "C_GENERAL",
        "channel_type": "channel",
        "files": [
            {
                "id": "F_FILE1",
                "name": "main.py",
                "mimetype": "text/x-python",
                "size": 1024,
                "url_private": "https://files.slack.com/files-pri/T_TEAM/main.py",
            }
        ],
    }


@pytest.fixture
def slack_event_thread():
    """A Slack threaded message."""
    return {
        "type": "message",
        "user": "U_USER1",
        "text": "<@U_BOT> follow up",
        "ts": "1700000003.000400",
        "channel": "C_GENERAL",
        "channel_type": "channel",
        "thread_ts": "1700000000.000100",
    }
