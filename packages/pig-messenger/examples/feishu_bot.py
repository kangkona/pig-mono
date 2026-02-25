"""Feishu integration test using lark_oapi SDK long connection (WebSocket).

No webhook server or ngrok needed. The SDK maintains a WebSocket connection
to Feishu servers directly.

Prerequisites:
    pip install lark-oapi

    Feishu App Setup:
    1. Create app at https://open.feishu.cn/app
    2. Enable Bot capability (App Features → Bot)
    3. Add permissions: im:message, im:message:send_as_bot
    4. Event Subscriptions → choose "长连接" (Long Connection) mode
       (NOT the webhook/callback mode)
    5. Subscribe to: im.message.receive_v1
    6. Publish and approve the app
    7. Add bot to a test group or send it a DM

Usage:
    export FEISHU_APP_ID=cli_xxx
    export FEISHU_APP_SECRET=xxx

    python examples/feishu_bot.py
"""

import json
import os
import re

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)


def on_message(data: P2ImMessageReceiveV1):
    """Handle incoming message events."""
    event = data.event
    message = event.message
    sender = event.sender

    # Parse message content, strip @mention placeholders
    content = json.loads(message.content) if message.content else {}
    text = re.sub(r"@_user_\d+", "", content.get("text", "")).strip()

    print(f"\n[Received] sender={sender.sender_id.open_id}, chat={message.chat_id}")
    print(f"  type={message.message_type}, text={text}")

    # Echo reply using the SDK client
    reply_content = json.dumps({"text": f"Echo: {text}"})
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(message.chat_id)
            .msg_type("text")
            .content(reply_content)
            .build()
        )
        .build()
    )

    response = client.im.v1.message.create(request)
    if response.success():
        print(f"[Sent] Echo: {text} (msg_id={response.data.message_id})")
    else:
        print(f"[Error] code={response.code}, msg={response.msg}")


# Build event handler
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(on_message)
    .build()
)

# Build SDK client (for sending messages)
client = (
    lark.Client.builder()
    .app_id(os.environ["FEISHU_APP_ID"])
    .app_secret(os.environ["FEISHU_APP_SECRET"])
    .log_level(lark.LogLevel.INFO)
    .build()
)

if __name__ == "__main__":
    # Start WebSocket long connection
    ws_client = lark.ws.Client(
        app_id=os.environ["FEISHU_APP_ID"],
        app_secret=os.environ["FEISHU_APP_SECRET"],
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )

    print("Starting Feishu bot (WebSocket long connection)...")
    print("Send a message to the bot in Feishu to test.")
    ws_client.start()
