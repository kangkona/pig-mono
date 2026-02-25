"""Feishu integration test server.

A minimal FastAPI webhook server for testing the Feishu adapter locally.
Use with ngrok to expose the local server to the internet.

Usage:
    # 1. Start ngrok
    ngrok http 9000

    # 2. Set env vars and run
    export FEISHU_APP_ID=cli_xxx
    export FEISHU_APP_SECRET=xxx
    export FEISHU_VERIFY_TOKEN=xxx        # from Event Subscriptions page
    export FEISHU_ENCRYPT_KEY=xxx          # optional, from Event Subscriptions page

    python examples/feishu_webhook_server.py
"""

import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pig_messenger.adapters.feishu import FeishuAdapter

app = FastAPI()

adapter = FeishuAdapter(
    app_id=os.environ["FEISHU_APP_ID"],
    app_secret=os.environ["FEISHU_APP_SECRET"],
    verification_token=os.environ.get("FEISHU_VERIFY_TOKEN"),
    encrypt_key=os.environ.get("FEISHU_ENCRYPT_KEY"),
)


async def on_message(msg):
    """Handle incoming messages — echo back."""
    print(f"\n[Received] {msg.username}: {msg.text}")
    print(f"  channel={msg.channel_id}, mention={msg.is_mention}")

    # Echo reply
    reply = f"Echo: {msg.text}"
    msg_id = await adapter.send_message(msg.channel_id, reply)
    print(f"[Sent] {reply} (msg_id={msg_id})")


adapter.set_message_handler(on_message)


@app.post("/webhook/event")
async def handle_event(request: Request):
    """Handle Feishu event callbacks."""
    payload = await request.json()

    # URL verification challenge (first-time setup)
    if "challenge" in payload:
        print(f"[Verification] challenge={payload['challenge']}")
        return JSONResponse({"challenge": payload["challenge"]})

    # Verify token if configured
    if adapter.verification_token:
        token = payload.get("token", "")
        if token != adapter.verification_token:
            print(f"[Warning] Invalid token: {token}")
            return JSONResponse({"error": "invalid token"}, status_code=403)

    print(f"[Event] type={payload.get('header', {}).get('event_type', 'unknown')}")

    # Handle v2 event format
    header = payload.get("header", {})
    event = payload.get("event", {})

    if header.get("event_type") == "im.message.receive_v1":
        # v2 format: extract message from event
        message = event.get("message", {})
        sender = event.get("sender", {})

        feishu_event = {
            "type": "message",
            "message": message,
            "sender": sender,
            "create_time": str(int(float(message.get("create_time", "0")) * 1000))
            if "." in message.get("create_time", "0")
            else message.get("create_time", "0"),
        }
        adapter.handle_event({"event": feishu_event})

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    print("=" * 50)
    print("Feishu Integration Test Server")
    print("=" * 50)
    print(f"App ID: {adapter.app_id}")
    print(f"Verify Token: {'set' if adapter.verification_token else 'not set'}")
    print()
    print("Endpoints:")
    print("  POST /webhook/event  - Feishu event callback")
    print()
    print("Steps:")
    print("  1. Run: ngrok http 9000")
    print("  2. Copy ngrok URL (e.g. https://xxxx.ngrok-free.app)")
    print("  3. Set callback URL in Feishu Admin:")
    print("     https://xxxx.ngrok-free.app/webhook/event")
    print("  4. Send a message to the bot in Feishu")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=9000)
