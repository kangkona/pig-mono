"""Test streaming card updates on Feishu.

Sends a placeholder card, updates it several times to simulate LLM
streaming, then posts the final content.

Prerequisites:
    Same as feishu_bot.py — a Feishu app with Bot + im:message permissions.

Usage:
    export FEISHU_APP_ID=cli_xxx
    export FEISHU_APP_SECRET=xxx
    export FEISHU_TEST_CHAT_ID=oc_xxx   # a group chat the bot is in

    python examples/test_streaming_card.py
"""

import asyncio
import os
import time

from pig_messenger.adapters.feishu import FeishuAdapter

APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
CHAT_ID = os.environ["FEISHU_TEST_CHAT_ID"]


async def main():
    adapter = FeishuAdapter(app_id=APP_ID, app_secret=APP_SECRET)

    # 1. Send placeholder card
    print("[1/4] Sending placeholder card...")
    msg_id = await adapter.send_card(CHAT_ID, "⏳ 思考中...")
    print(f"  card message_id = {msg_id}")

    # 2. Simulate streaming chunks
    chunks = [
        "你好！我是 pig-messenger 的流式卡片测试。\n\n",
        "这段文字是**逐步生成**的，模拟 LLM 流式输出的效果。\n\n",
        "每隔 1 秒更新一次卡片内容，就像 ChatGPT 打字一样。\n\n",
        "最后一次更新会去掉「生成中」的提示。",
    ]

    accumulated = ""
    for i, chunk in enumerate(chunks, 1):
        accumulated += chunk
        print(f"[{i+1}/4] Updating card (chunk {i}/{len(chunks)})...")
        await adapter.update_card(msg_id, accumulated + "\n\n● 生成中...")
        time.sleep(1)

    # 3. Final update — clean text without indicator
    print("[4/4] Final update...")
    await adapter.update_card(msg_id, accumulated.rstrip())
    print("Done! Check the Feishu chat.")


if __name__ == "__main__":
    asyncio.run(main())
