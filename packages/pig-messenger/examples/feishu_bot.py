"""Feishu integration test using FeishuAdapter with SDK long connection.

No webhook server or ngrok needed. The adapter maintains a WebSocket
connection to Feishu servers directly via lark_oapi.

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

import os
from typing import Any

from pig_messenger.adapters.feishu import FeishuAdapter

adapter = FeishuAdapter(
    app_id=os.environ["FEISHU_APP_ID"],
    app_secret=os.environ["FEISHU_APP_SECRET"],
)


async def on_message(msg: Any) -> None:
    """Echo received messages back to the chat."""
    print(f"\n[Received] sender={msg.user_id}, chat={msg.channel_id}")
    print(f"  text={msg.text}, mention={msg.is_mention}")

    reply = f"Echo: {msg.text}"
    msg_id = await adapter.send_message(msg.channel_id, reply)
    print(f"[Sent] {reply} (msg_id={msg_id})")


adapter.set_message_handler(on_message)

if __name__ == "__main__":
    print("Starting Feishu bot (WebSocket long connection)...")
    print("Send a message to the bot in Feishu to test.")
    adapter.start()
