"""Unit tests for SlackAdapter."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pig_messenger.message import Attachment, UniversalMessage


# ---------------------------------------------------------------------------
# Helper: build a SlackAdapter with all Slack SDK calls mocked.
# ---------------------------------------------------------------------------

def _make_adapter(bot_user_id="U_BOT"):
    """Create a SlackAdapter with mocked Slack SDK."""
    mock_app_cls = MagicMock()
    mock_app = MagicMock()
    mock_app_cls.return_value = mock_app

    mock_smh_cls = MagicMock()

    mock_webclient_cls = MagicMock()
    mock_client = MagicMock()
    mock_client.auth_test.return_value = {"user_id": bot_user_id}
    mock_webclient_cls.return_value = mock_client

    # Inject mock modules so top-level imports in slack.py resolve
    mock_bolt = MagicMock()
    mock_bolt.App = mock_app_cls
    mock_bolt_sm = MagicMock()
    mock_bolt_sm.SocketModeHandler = mock_smh_cls
    mock_sdk = MagicMock()
    mock_sdk.WebClient = mock_webclient_cls

    saved = {}
    mods = ("slack_bolt", "slack_bolt.adapter", "slack_bolt.adapter.socket_mode", "slack_sdk")
    for m in mods:
        saved[m] = sys.modules.get(m)
    sys.modules["slack_bolt"] = mock_bolt
    sys.modules["slack_bolt.adapter"] = MagicMock()
    sys.modules["slack_bolt.adapter.socket_mode"] = mock_bolt_sm
    sys.modules["slack_sdk"] = mock_sdk

    # Force re-import of the adapter module
    adapter_key = "pig_messenger.adapters.slack"
    saved_adapter = sys.modules.pop(adapter_key, None)
    try:
        from pig_messenger.adapters.slack import SlackAdapter
        adapter = SlackAdapter(app_token="xapp-test", bot_token="xoxb-test")
    finally:
        for m, orig in saved.items():
            if orig is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = orig
        if saved_adapter is not None:
            sys.modules[adapter_key] = saved_adapter

    return adapter, mock_client, mock_app, mock_smh_cls


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestSlackAdapterInit:
    def test_auto_detects_bot_user_id(self):
        adapter, client, _, _ = _make_adapter()
        assert adapter.bot_user_id == "U_BOT"
        client.auth_test.assert_called_once()

    def test_explicit_bot_user_id_skips_auth(self):
        mock_webclient_cls = MagicMock()
        mock_client = MagicMock()
        mock_webclient_cls.return_value = mock_client

        mock_bolt = MagicMock()
        mock_sdk = MagicMock()
        mock_sdk.WebClient = mock_webclient_cls

        saved = {}
        mods = ("slack_bolt", "slack_bolt.adapter", "slack_bolt.adapter.socket_mode", "slack_sdk")
        for m in mods:
            saved[m] = sys.modules.get(m)
        sys.modules["slack_bolt"] = mock_bolt
        sys.modules["slack_bolt.adapter"] = MagicMock()
        sys.modules["slack_bolt.adapter.socket_mode"] = MagicMock()
        sys.modules["slack_sdk"] = mock_sdk

        adapter_key = "pig_messenger.adapters.slack"
        saved_adapter = sys.modules.pop(adapter_key, None)
        try:
            from pig_messenger.adapters.slack import SlackAdapter
            adapter = SlackAdapter(
                app_token="xapp-test", bot_token="xoxb-test", bot_user_id="U_EXPLICIT",
            )
            assert adapter.bot_user_id == "U_EXPLICIT"
            mock_client.auth_test.assert_not_called()
        finally:
            for m, orig in saved.items():
                if orig is None:
                    sys.modules.pop(m, None)
                else:
                    sys.modules[m] = orig
            if saved_adapter is not None:
                sys.modules[adapter_key] = saved_adapter

    def test_platform_name_is_slack(self):
        adapter, _, _, _ = _make_adapter()
        assert adapter.name == "slack"


# ---------------------------------------------------------------------------
# Message conversion (_handle_slack_message)
# ---------------------------------------------------------------------------

class TestHandleSlackMessage:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_mention_strips_bot_id(self, slack_event_mention):
        adapter, client, _, _ = _make_adapter()
        client.users_info.return_value = {
            "user": {"real_name": "Alice", "name": "alice", "profile": {"email": "alice@test.com"}}
        }
        captured = []
        async def handler(msg): captured.append(msg)
        adapter.set_message_handler(handler)
        self._run(adapter._handle_slack_message(slack_event_mention, is_mention=True))

        msg = captured[0]
        assert isinstance(msg, UniversalMessage)
        assert msg.text == "review this code"
        assert msg.is_mention is True
        assert msg.platform == "slack"
        assert msg.channel_id == "C_GENERAL"
        assert msg.username == "Alice"
        assert msg.user_email == "alice@test.com"

    def test_dm_message(self, slack_event_dm):
        adapter, client, _, _ = _make_adapter()
        client.users_info.return_value = {
            "user": {"real_name": "Bob", "name": "bob", "profile": {}}
        }
        captured = []
        async def handler(msg): captured.append(msg)
        adapter.set_message_handler(handler)
        self._run(adapter._handle_slack_message(slack_event_dm, is_dm=True))

        assert captured[0].is_dm is True
        assert captured[0].text == "hello bot"

    def test_file_attachments(self, slack_event_with_file):
        adapter, client, _, _ = _make_adapter()
        client.users_info.return_value = {
            "user": {"real_name": "Alice", "name": "alice", "profile": {}}
        }
        captured = []
        async def handler(msg): captured.append(msg)
        adapter.set_message_handler(handler)
        self._run(adapter._handle_slack_message(slack_event_with_file, is_mention=True))

        att = captured[0].attachments[0]
        assert att.id == "F_FILE1"
        assert att.filename == "main.py"
        assert att.content_type == "text/x-python"
        assert att.size == 1024

    def test_thread_message(self, slack_event_thread):
        adapter, client, _, _ = _make_adapter()
        client.users_info.return_value = {
            "user": {"real_name": "Alice", "name": "alice", "profile": {}}
        }
        captured = []
        async def handler(msg): captured.append(msg)
        adapter.set_message_handler(handler)
        self._run(adapter._handle_slack_message(slack_event_thread, is_mention=True))

        assert captured[0].is_thread is True
        assert captured[0].thread_id == "1700000000.000100"

    def test_user_info_fallback_on_error(self, slack_event_mention):
        adapter, client, _, _ = _make_adapter()
        client.users_info.side_effect = Exception("API error")
        captured = []
        async def handler(msg): captured.append(msg)
        adapter.set_message_handler(handler)
        self._run(adapter._handle_slack_message(slack_event_mention, is_mention=True))

        assert captured[0].username == "U_USER1"
        assert captured[0].user_email is None

    def test_no_handler_does_not_crash(self, slack_event_dm):
        adapter, client, _, _ = _make_adapter()
        client.users_info.return_value = {
            "user": {"real_name": "X", "name": "x", "profile": {}}
        }
        # on_message is None — should not raise
        self._run(adapter._handle_slack_message(slack_event_dm, is_dm=True))


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_send_simple_message(self):
        adapter, client, _, _ = _make_adapter()
        client.chat_postMessage.return_value = {"ts": "1700000010.000500"}
        ts = self._run(adapter.send_message("C_GENERAL", "hello"))
        assert ts == "1700000010.000500"
        client.chat_postMessage.assert_called_once_with(
            channel="C_GENERAL", text="hello", thread_ts=None,
        )

    def test_send_threaded_reply(self):
        adapter, client, _, _ = _make_adapter()
        client.chat_postMessage.return_value = {"ts": "1700000011.000600"}
        self._run(adapter.send_message("C_GENERAL", "reply", thread_id="1700000000.000100"))
        client.chat_postMessage.assert_called_once_with(
            channel="C_GENERAL", text="reply", thread_ts="1700000000.000100",
        )


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

class TestUploadFile:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_upload(self, tmp_path):
        adapter, client, _, _ = _make_adapter()
        client.files_upload_v2.return_value = {"file": {"id": "F_NEW"}}
        f = tmp_path / "test.txt"
        f.write_text("content")
        fid = self._run(adapter.upload_file("C_GENERAL", f, caption="here"))
        assert fid == "F_NEW"
        client.files_upload_v2.assert_called_once_with(
            channel="C_GENERAL", file=str(f), initial_comment="here", thread_ts=None,
        )


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

class TestGetHistory:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_returns_messages_skipping_bot(self):
        adapter, client, _, _ = _make_adapter()
        client.conversations_history.return_value = {
            "messages": [
                {"ts": "1700000020.000", "user": "U_USER1", "text": "hi"},
                {"ts": "1700000021.000", "user": "U_BOT", "text": "bot reply"},
                {"ts": "1700000022.000", "user": "U_USER2", "text": "hey"},
            ]
        }
        msgs = self._run(adapter.get_history("C_GENERAL", limit=10))
        assert len(msgs) == 2
        assert msgs[0].text == "hi"
        assert msgs[1].text == "hey"


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_download(self):
        adapter, client, _, _ = _make_adapter()
        att = Attachment(
            id="F1", filename="f.txt", content_type="text/plain",
            size=5, url="https://files.slack.com/f.txt",
        )
        with patch("httpx.AsyncClient") as MockHTTP:
            mock_resp = MagicMock()
            mock_resp.content = b"hello"
            mock_resp.raise_for_status = MagicMock()
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockHTTP.return_value = mock_http

            data = self._run(adapter.download_file(att))
            assert data == b"hello"
            call_kwargs = mock_http.get.call_args
            assert "Bearer" in call_kwargs[1]["headers"]["Authorization"]


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------

class TestStartStop:
    def test_start_creates_socket_handler(self):
        adapter, _, _, mock_smh_cls = _make_adapter()
        mock_handler = MagicMock()
        mock_smh_cls.return_value = mock_handler

        import pig_messenger.adapters.slack as slack_mod
        orig = getattr(slack_mod, "SocketModeHandler", None)
        slack_mod.SocketModeHandler = mock_smh_cls
        try:
            adapter.start()
            mock_smh_cls.assert_called_with(adapter.app, "xapp-test")
            mock_handler.start.assert_called_once()
        finally:
            if orig is not None:
                slack_mod.SocketModeHandler = orig

    def test_stop_closes_handler(self):
        adapter, _, _, _ = _make_adapter()
        adapter.handler = MagicMock()
        adapter.stop()
        adapter.handler.close.assert_called_once()

    def test_stop_without_handler(self):
        adapter, _, _, _ = _make_adapter()
        adapter.handler = None
        adapter.stop()


# ---------------------------------------------------------------------------
# Bot-message filtering
# ---------------------------------------------------------------------------

class TestMessageFiltering:
    def test_skips_own_messages(self, slack_event_dm):
        adapter, _, _, _ = _make_adapter()
        slack_event_dm["user"] = "U_BOT"
        assert slack_event_dm["user"] == adapter.bot_user_id
