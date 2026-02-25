"""Unit tests for FeishuAdapter."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pig_messenger.adapters.feishu import FeishuAdapter
from pig_messenger.message import Attachment, UniversalMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(**kwargs):
    """Create a FeishuAdapter with mocked httpx client."""
    adapter = FeishuAdapter(
        app_id=kwargs.get("app_id", "cli_test_app_id"),
        app_secret=kwargs.get("app_secret", "test_app_secret"),
        verification_token=kwargs.get("verification_token", "test_verify_token"),
        encrypt_key=kwargs.get("encrypt_key", "test_encrypt_key"),
    )
    mock_client = AsyncMock()
    adapter.client = mock_client
    return adapter, mock_client


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_response(data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.content = b"file-bytes"
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def feishu_event_text():
    """A Feishu text message event."""
    return {
        "type": "message",
        "sender": {
            "sender_id": {
                "open_id": "ou_sender123",
                "user_id": "alice",
            },
        },
        "message": {
            "message_id": "om_msg001",
            "chat_id": "oc_chat001",
            "content": json.dumps({"text": "hello bot"}),
            "mentions": None,
        },
        "create_time": "1700000000000",
    }


@pytest.fixture
def feishu_event_mention():
    """A Feishu message event with @mention."""
    return {
        "type": "message",
        "sender": {
            "sender_id": {
                "open_id": "ou_sender456",
                "user_id": "bob",
            },
        },
        "message": {
            "message_id": "om_msg002",
            "chat_id": "oc_chat002",
            "content": json.dumps({"text": "@_user_1 review this code"}),
            "mentions": [{"key": "@_all", "id": {"open_id": "ou_bot"}}],
        },
        "create_time": "1700000001000",
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestFeishuAdapterInit:
    def test_platform_name(self):
        adapter, _ = _make_adapter()
        assert adapter.name == "feishu"

    def test_stores_credentials(self):
        adapter, _ = _make_adapter(app_id="my_id", app_secret="my_secret")
        assert adapter.app_id == "my_id"
        assert adapter.app_secret == "my_secret"

    def test_token_initially_none(self):
        adapter, _ = _make_adapter()
        assert adapter.tenant_access_token is None


# ---------------------------------------------------------------------------
# Tenant Access Token
# ---------------------------------------------------------------------------


class TestGetTenantAccessToken:
    def test_fetches_token(self):
        adapter, client = _make_adapter()
        client.post.return_value = _mock_response({"tenant_access_token": "t-token123"})

        token = _run(adapter._get_tenant_access_token())

        assert token == "t-token123"
        assert adapter.tenant_access_token == "t-token123"
        client.post.assert_called_once()
        call_kwargs = client.post.call_args
        assert "auth/v3/tenant_access_token/internal" in call_kwargs[0][0]

    def test_caches_token(self):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "cached-token"

        token = _run(adapter._get_tenant_access_token())

        assert token == "cached-token"
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


class TestSendMessage:
    def _setup(self):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"
        return adapter, client

    def test_send_to_chat_id(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_resp001"}})

        msg_id = _run(adapter.send_message("oc_chat001", "hello"))

        assert msg_id == "om_resp001"
        call_kwargs = client.post.call_args
        assert call_kwargs[1]["params"]["receive_id_type"] == "chat_id"
        payload = call_kwargs[1]["json"]
        assert payload["receive_id"] == "oc_chat001"
        assert payload["msg_type"] == "text"
        assert json.loads(payload["content"]) == {"text": "hello"}
        assert "root_id" not in payload

    def test_send_to_open_id(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_resp002"}})

        _run(adapter.send_message("ou_user001", "hi"))

        call_kwargs = client.post.call_args
        assert call_kwargs[1]["params"]["receive_id_type"] == "open_id"

    def test_send_with_thread_id(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_resp003"}})

        _run(adapter.send_message("oc_chat001", "reply", thread_id="om_parent"))

        payload = client.post.call_args[1]["json"]
        assert payload["root_id"] == "om_parent"

    def test_auth_header(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_resp004"}})

        _run(adapter.send_message("oc_chat001", "test"))

        headers = client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer t-token"


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------


class TestUploadFile:
    def test_upload_sends_file_then_message(self, tmp_path):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"

        upload_resp = _mock_response({"data": {"file_key": "fk_abc123"}})
        send_resp = _mock_response({"data": {"message_id": "om_file001"}})
        client.post.side_effect = [upload_resp, send_resp]

        f = tmp_path / "test.txt"
        f.write_text("content")

        msg_id = _run(adapter.upload_file("oc_chat001", f))

        assert msg_id == "om_file001"
        assert client.post.call_count == 2

        # Second call should be the file message
        send_call = client.post.call_args_list[1]
        payload = send_call[1]["json"]
        assert payload["msg_type"] == "file"
        assert json.loads(payload["content"]) == {"file_key": "fk_abc123"}

    def test_upload_with_caption(self, tmp_path):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"

        upload_resp = _mock_response({"data": {"file_key": "fk_abc"}})
        send_file_resp = _mock_response({"data": {"message_id": "om_file002"}})
        send_caption_resp = _mock_response({"data": {"message_id": "om_cap001"}})
        client.post.side_effect = [upload_resp, send_file_resp, send_caption_resp]

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"pdf-content")

        _run(adapter.upload_file("oc_chat001", f, caption="check this"))

        # 3 calls: upload file, send file msg, send caption msg
        assert client.post.call_count == 3


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_returns_empty(self):
        adapter, _ = _make_adapter()
        result = _run(adapter.get_history("oc_chat001"))
        assert result == []


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    def test_download(self):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"

        resp = _mock_response({})
        resp.content = b"downloaded-bytes"
        client.get.return_value = resp

        att = Attachment(
            id="file_key_123",
            filename="report.pdf",
            content_type="application/pdf",
            size=2048,
        )

        data = _run(adapter.download_file(att))

        assert data == b"downloaded-bytes"
        client.get.assert_called_once()
        call_args = client.get.call_args
        assert "file_key_123" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer t-token"


# ---------------------------------------------------------------------------
# Event handling / message conversion
# ---------------------------------------------------------------------------


class TestHandleEvent:
    def test_convert_text_message(self, feishu_event_text):
        adapter, _ = _make_adapter()
        msg = adapter._convert_feishu_message(feishu_event_text)

        assert isinstance(msg, UniversalMessage)
        assert msg.id == "om_msg001"
        assert msg.platform == "feishu"
        assert msg.channel_id == "oc_chat001"
        assert msg.user_id == "ou_sender123"
        assert msg.username == "alice"
        assert msg.text == "hello bot"
        assert msg.is_mention is False

    def test_convert_mention_message(self, feishu_event_mention):
        adapter, _ = _make_adapter()
        msg = adapter._convert_feishu_message(feishu_event_mention)

        assert msg.text == "review this code"
        assert msg.is_mention is True
        assert msg.channel_id == "oc_chat002"

    def test_handle_event_emits_message(self, feishu_event_text):
        adapter, _ = _make_adapter()
        captured = []

        async def handler(msg):
            captured.append(msg)

        adapter.set_message_handler(handler)

        # handle_event uses asyncio.create_task, need a running loop
        async def run():
            adapter.handle_event({"event": feishu_event_text})
            await asyncio.sleep(0.05)

        _run(run())
        assert len(captured) == 1
        assert captured[0].text == "hello bot"

    def test_handle_event_ignores_non_message(self):
        adapter, _ = _make_adapter()
        captured = []

        async def handler(msg):
            captured.append(msg)

        adapter.set_message_handler(handler)

        adapter.handle_event({"event": {"type": "url_verification"}})
        assert len(captured) == 0

    def test_empty_content_fallback(self):
        adapter, _ = _make_adapter()
        event = {
            "type": "message",
            "sender": {"sender_id": {"open_id": "ou_x", "user_id": "x"}},
            "message": {"message_id": "om_x", "chat_id": "oc_x"},
            "create_time": "0",
        }
        msg = adapter._convert_feishu_message(event)
        assert msg.text == ""


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start(self, capsys):
        adapter, _ = _make_adapter()
        adapter.start()
        out = capsys.readouterr().out
        assert "Feishu adapter ready" in out

    def test_stop_no_error(self):
        adapter, _ = _make_adapter()
        adapter.stop()  # should not raise
