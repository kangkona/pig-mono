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
    """Create a FeishuAdapter in webhook mode with mocked httpx client."""
    adapter = FeishuAdapter(
        app_id=kwargs.get("app_id", "cli_test_app_id"),
        app_secret=kwargs.get("app_secret", "test_app_secret"),
        verification_token=kwargs.get("verification_token", "test_verify_token"),
        encrypt_key=kwargs.get("encrypt_key", "test_encrypt_key"),
        use_ws=False,
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


# ---------------------------------------------------------------------------
# SDK (WebSocket) mode
# ---------------------------------------------------------------------------


def _mock_lark_module():
    """Build a mock lark_oapi module tree sufficient for FeishuAdapter._init_sdk."""
    lark = MagicMock()
    # LogLevel enum
    lark.LogLevel.INFO = "INFO"
    # EventDispatcherHandler builder chain
    handler_builder = MagicMock()
    handler_builder.register_p2_im_message_receive_v1.return_value = handler_builder
    handler_builder.build.return_value = MagicMock(name="event_handler")
    lark.EventDispatcherHandler.builder.return_value = handler_builder
    # Client builder chain
    client_builder = MagicMock()
    client_builder.app_id.return_value = client_builder
    client_builder.app_secret.return_value = client_builder
    client_builder.build.return_value = MagicMock(name="lark_client")
    lark.Client.builder.return_value = client_builder
    # ws.Client
    lark.ws.Client.return_value = MagicMock(name="ws_client")
    return lark


class TestFeishuSDKMode:
    """Tests for use_ws=True (SDK long-connection mode)."""

    def _make_sdk_adapter(self):
        """Create adapter in SDK mode with mocked lark_oapi."""
        import sys

        mock_lark = _mock_lark_module()
        # Patch lark_oapi in sys.modules so the lazy import picks it up
        saved = sys.modules.get("lark_oapi")
        sys.modules["lark_oapi"] = mock_lark
        try:
            adapter = FeishuAdapter(
                app_id="cli_sdk_id",
                app_secret="sdk_secret",
                use_ws=True,
            )
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi", None)
            else:
                sys.modules["lark_oapi"] = saved
        return adapter, mock_lark

    def test_init_creates_ws_client(self):
        adapter, mock_lark = self._make_sdk_adapter()
        assert adapter._ws_client is not None
        assert adapter._lark_client is not None
        mock_lark.ws.Client.assert_called_once()

    def test_start_calls_ws_client_start(self):
        adapter, _ = self._make_sdk_adapter()
        adapter.start()
        adapter._ws_client.start.assert_called_once()

    def test_stop_calls_ws_client_disconnect(self):
        adapter, _ = self._make_sdk_adapter()
        adapter._ws_client._disconnect = AsyncMock()
        adapter.stop()
        adapter._ws_client._disconnect.assert_called_once()

    def test_stop_noop_when_no_ws_client(self):
        adapter, _ = self._make_sdk_adapter()
        adapter._ws_client = None
        adapter.stop()  # should not raise

    def test_send_message_sdk(self):
        adapter, _ = self._make_sdk_adapter()
        # Mock the SDK response
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.message_id = "om_sdk_001"
        adapter._lark_client.im.v1.message.create.return_value = mock_resp

        import sys

        mock_im = MagicMock()
        body_builder = MagicMock()
        body_builder.receive_id.return_value = body_builder
        body_builder.msg_type.return_value = body_builder
        body_builder.content.return_value = body_builder
        body_builder.build.return_value = MagicMock(name="body")
        mock_im.CreateMessageRequestBody.builder.return_value = body_builder

        req_builder = MagicMock()
        req_builder.receive_id_type.return_value = req_builder
        req_builder.request_body.return_value = req_builder
        req_builder.build.return_value = MagicMock(name="request")
        mock_im.CreateMessageRequest.builder.return_value = req_builder

        saved = sys.modules.get("lark_oapi.api.im.v1")
        sys.modules["lark_oapi.api.im.v1"] = mock_im
        try:
            msg_id = _run(adapter.send_message("oc_chat001", "hello sdk"))
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi.api.im.v1", None)
            else:
                sys.modules["lark_oapi.api.im.v1"] = saved

        assert msg_id == "om_sdk_001"
        adapter._lark_client.im.v1.message.create.assert_called_once()

    def test_send_message_sdk_failure_raises(self):
        adapter, _ = self._make_sdk_adapter()
        mock_resp = MagicMock()
        mock_resp.success.return_value = False
        mock_resp.code = 99999
        mock_resp.msg = "permission denied"
        adapter._lark_client.im.v1.message.create.return_value = mock_resp

        import sys

        mock_im = MagicMock()
        builder = MagicMock()
        builder.receive_id.return_value = builder
        builder.msg_type.return_value = builder
        builder.content.return_value = builder
        builder.build.return_value = MagicMock()
        mock_im.CreateMessageRequestBody.builder.return_value = builder

        req_builder = MagicMock()
        req_builder.receive_id_type.return_value = req_builder
        req_builder.request_body.return_value = req_builder
        req_builder.build.return_value = MagicMock()
        mock_im.CreateMessageRequest.builder.return_value = req_builder

        saved = sys.modules.get("lark_oapi.api.im.v1")
        sys.modules["lark_oapi.api.im.v1"] = mock_im
        try:
            with pytest.raises(RuntimeError, match="permission denied"):
                _run(adapter.send_message("oc_chat001", "fail"))
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi.api.im.v1", None)
            else:
                sys.modules["lark_oapi.api.im.v1"] = saved

    def test_on_sdk_message_emits(self):
        adapter, _ = self._make_sdk_adapter()
        captured = []

        async def handler(msg):
            captured.append(msg)

        adapter.set_message_handler(handler)

        # Build a mock P2ImMessageReceiveV1
        data = MagicMock()
        data.event.message.message_id = "om_sdk_msg"
        data.event.message.chat_id = "oc_sdk_chat"
        data.event.message.content = json.dumps({"text": "@_user_1 hi sdk"})
        data.event.message.mentions = None
        data.event.message.create_time = "1700000000000"
        data.event.sender.sender_id.open_id = "ou_sdk_sender"
        data.event.sender.sender_id.user_id = "sdk_alice"

        adapter._on_sdk_message(data)

        assert len(captured) == 1
        msg = captured[0]
        assert msg.text == "hi sdk"
        assert msg.channel_id == "oc_sdk_chat"
        assert msg.user_id == "ou_sdk_sender"
        assert msg.is_mention is False

    def test_on_sdk_message_with_mentions(self):
        adapter, _ = self._make_sdk_adapter()
        captured = []

        async def handler(msg):
            captured.append(msg)

        adapter.set_message_handler(handler)

        data = MagicMock()
        data.event.message.message_id = "om_sdk_m2"
        data.event.message.chat_id = "oc_sdk_chat2"
        data.event.message.content = json.dumps({"text": "@_user_1 review this"})
        data.event.message.mentions = [{"key": "@_all"}]
        data.event.message.create_time = "1700000001000"
        data.event.sender.sender_id.open_id = "ou_bob"
        data.event.sender.sender_id.user_id = "bob"

        adapter._on_sdk_message(data)

        assert len(captured) == 1
        assert captured[0].is_mention is True
        assert captured[0].text == "review this"


# ---------------------------------------------------------------------------
# Card messages
# ---------------------------------------------------------------------------


class TestBuildCardContent:
    def test_structure(self):
        adapter, _ = _make_adapter()
        card = adapter._build_card_content("hello **world**")
        assert card == {
            "elements": [{"tag": "markdown", "content": "hello **world**"}],
        }


class TestSendCard:
    def _setup(self):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"
        return adapter, client

    def test_send_card_http(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_card001"}})

        msg_id = asyncio.run(adapter.send_card("oc_chat001", "hello card"))

        assert msg_id == "om_card001"
        call_kwargs = client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["msg_type"] == "interactive"
        content = json.loads(payload["content"])
        assert content["elements"][0]["tag"] == "markdown"
        assert content["elements"][0]["content"] == "hello card"

    def test_send_card_http_open_id(self):
        adapter, client = self._setup()
        client.post.return_value = _mock_response({"data": {"message_id": "om_card002"}})

        asyncio.run(adapter.send_card("ou_user001", "hi"))

        call_kwargs = client.post.call_args
        assert call_kwargs[1]["params"]["receive_id_type"] == "open_id"


class TestUpdateCard:
    def _setup(self):
        adapter, client = _make_adapter()
        adapter.tenant_access_token = "t-token"
        return adapter, client

    def test_update_card_http(self):
        adapter, client = self._setup()
        client.patch.return_value = _mock_response({})

        asyncio.run(adapter.update_card("om_card001", "updated text"))

        client.patch.assert_called_once()
        call_args = client.patch.call_args
        assert "om_card001" in call_args[0][0]
        payload = call_args[1]["json"]
        content = json.loads(payload["content"])
        assert content["elements"][0]["content"] == "updated text"
        assert call_args[1]["headers"]["Authorization"] == "Bearer t-token"


class TestCardSDKMode:
    """Tests for card operations in SDK mode."""

    def _make_sdk_adapter(self):
        import sys

        mock_lark = _mock_lark_module()
        saved = sys.modules.get("lark_oapi")
        sys.modules["lark_oapi"] = mock_lark
        try:
            adapter = FeishuAdapter(
                app_id="cli_sdk_id",
                app_secret="sdk_secret",
                use_ws=True,
            )
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi", None)
            else:
                sys.modules["lark_oapi"] = saved
        return adapter, mock_lark

    def test_send_card_sdk(self):
        adapter, _ = self._make_sdk_adapter()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data.message_id = "om_sdk_card001"
        adapter._lark_client.im.v1.message.create.return_value = mock_resp

        import sys

        mock_im = MagicMock()
        body_builder = MagicMock()
        body_builder.receive_id.return_value = body_builder
        body_builder.msg_type.return_value = body_builder
        body_builder.content.return_value = body_builder
        body_builder.build.return_value = MagicMock(name="body")
        mock_im.CreateMessageRequestBody.builder.return_value = body_builder

        req_builder = MagicMock()
        req_builder.receive_id_type.return_value = req_builder
        req_builder.request_body.return_value = req_builder
        req_builder.build.return_value = MagicMock(name="request")
        mock_im.CreateMessageRequest.builder.return_value = req_builder

        saved = sys.modules.get("lark_oapi.api.im.v1")
        sys.modules["lark_oapi.api.im.v1"] = mock_im
        try:
            msg_id = asyncio.run(adapter.send_card("oc_chat001", "card text"))
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi.api.im.v1", None)
            else:
                sys.modules["lark_oapi.api.im.v1"] = saved

        assert msg_id == "om_sdk_card001"
        # Verify msg_type was set to "interactive"
        body_builder.msg_type.assert_called_with("interactive")

    def test_update_card_sdk(self):
        adapter, _ = self._make_sdk_adapter()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        adapter._lark_client.im.v1.message.patch.return_value = mock_resp

        import sys

        mock_im = MagicMock()
        patch_body_builder = MagicMock()
        patch_body_builder.content.return_value = patch_body_builder
        patch_body_builder.build.return_value = MagicMock(name="patch_body")
        mock_im.PatchMessageRequestBody.builder.return_value = patch_body_builder

        patch_req_builder = MagicMock()
        patch_req_builder.message_id.return_value = patch_req_builder
        patch_req_builder.request_body.return_value = patch_req_builder
        patch_req_builder.build.return_value = MagicMock(name="patch_request")
        mock_im.PatchMessageRequest.builder.return_value = patch_req_builder

        saved = sys.modules.get("lark_oapi.api.im.v1")
        sys.modules["lark_oapi.api.im.v1"] = mock_im
        try:
            asyncio.run(adapter.update_card("om_card001", "updated"))
        finally:
            if saved is None:
                sys.modules.pop("lark_oapi.api.im.v1", None)
            else:
                sys.modules["lark_oapi.api.im.v1"] = saved

        adapter._lark_client.im.v1.message.patch.assert_called_once()
        patch_req_builder.message_id.assert_called_with("om_card001")
