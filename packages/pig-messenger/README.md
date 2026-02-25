# pig-messenger

**Universal Multi-Platform Bot Framework**

One agent, multiple messaging platforms. Write once, deploy everywhere.

## Features

- **Multi-Platform**: Slack, Discord, Telegram, WhatsApp, Feishu
- **Plug-in Architecture**: Easy to add new platforms
- **Powered by pig-agent-core**: Full agent capabilities
- **Session Management**: Per-channel conversation history
- **File Handling**: Upload/download across platforms
- **Lazy Imports**: Only install deps for the platforms you use

## Supported Platforms

| Platform | Status | Use Case |
|----------|--------|----------|
| **Slack** | ✅ Tested | Enterprise (Global) |
| **Discord** | ✅ Ready | Developer Communities |
| **Telegram** | ✅ Ready | Personal & Groups |
| **WhatsApp** | ✅ Ready | Personal Communication |
| **Feishu (飞书)** | ✅ Tested | Enterprise (China) |

## Installation

```bash
# Base
pip install pig-messenger

# With Slack support
pip install pig-messenger[slack]

# With all platforms
pip install pig-messenger[all]
```

## Quick Start

### Slack Bot

```python
import os
from pig_messenger import MessengerBot
from pig_messenger.adapters import SlackAdapter
from pig_agent_core import Agent
from pig_llm import LLM

agent = Agent(
    llm=LLM(provider="openrouter", model="moonshotai/kimi-k2.5",
            api_key=os.environ["OPENROUTER_API_KEY"]),
)

bot = MessengerBot(agent)
bot.add_platform(SlackAdapter(
    app_token=os.environ["SLACK_APP_TOKEN"],  # xapp-...
    bot_token=os.environ["SLACK_BOT_TOKEN"],  # xoxb-...
))
bot.start()
```

### Multi-Platform Bot

```python
from pig_messenger.adapters import (
    SlackAdapter, DiscordAdapter, TelegramAdapter,
    WhatsAppAdapter, FeishuAdapter,
)

bot = MessengerBot(agent)
bot.add_platform(SlackAdapter(
    app_token=os.environ["SLACK_APP_TOKEN"],
    bot_token=os.environ["SLACK_BOT_TOKEN"],
))
bot.add_platform(DiscordAdapter(bot_token=os.environ["DISCORD_BOT_TOKEN"]))
bot.add_platform(TelegramAdapter(bot_token=os.environ["TELEGRAM_BOT_TOKEN"]))
bot.add_platform(WhatsAppAdapter(
    phone_number_id=os.environ["WHATSAPP_PHONE_NUMBER_ID"],
    access_token=os.environ["WHATSAPP_ACCESS_TOKEN"],
))
bot.add_platform(FeishuAdapter(
    app_id=os.environ["FEISHU_APP_ID"],
    app_secret=os.environ["FEISHU_APP_SECRET"],
))
bot.start()  # All platforms run in parallel
```

## Slack App Setup

1. Create app at https://api.slack.com/apps → Create New App → From scratch
2. **Socket Mode**: Settings → Socket Mode → Enable, generate App Token (`xapp-...`, scope: `connections:write`)
3. **Bot Permissions**: Features → OAuth & Permissions → Bot Token Scopes:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`
   - `files:read`
   - `files:write`
   - `users:read`
4. **Event Subscriptions**: Features → Event Subscriptions → Enable, subscribe to bot events:
   - `app_mention`
   - `message.im`
5. **Install**: Settings → Install App → Install to Workspace, get Bot Token (`xoxb-...`)
6. Invite bot to a channel: `/invite @your-bot-name`

### Discord

1. Create app at https://discord.com/developers/applications → New Application
2. **Bot**: Settings → Bot → Add Bot, enable "Message Content Intent"
3. **Permissions**: OAuth2 → URL Generator → Scopes: `bot`, Permissions: `Read Messages/View Channels`, `Send Messages`, `Attach Files`, `Read Message History`
4. Copy the generated URL, open in browser to invite bot to your server
5. Copy Bot Token from Bot settings page

```python
from pig_messenger.adapters import DiscordAdapter

bot.add_platform(DiscordAdapter(
    bot_token=os.environ["DISCORD_BOT_TOKEN"],
))
```

### Telegram

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`
2. Follow prompts to set bot name and username
3. Copy the bot token BotFather gives you

```python
from pig_messenger.adapters import TelegramAdapter

bot.add_platform(TelegramAdapter(
    bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
))
```

### WhatsApp

Requires a [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp/cloud-api) account.

1. Create app at https://developers.facebook.com → My Apps → Create App → Business
2. Add WhatsApp product to your app
3. In WhatsApp → API Setup, get your **Phone Number ID** and generate a **Temporary Access Token** (or create a permanent System User token)
4. Configure a webhook to receive incoming messages (subscribe to `messages` field)

```python
from pig_messenger.adapters import WhatsAppAdapter

adapter = WhatsAppAdapter(
    phone_number_id=os.environ["WHATSAPP_PHONE_NUMBER_ID"],
    access_token=os.environ["WHATSAPP_ACCESS_TOKEN"],
    verify_token="your-verify-token",  # For webhook verification
)
bot.add_platform(adapter)
```

> **Note**: WhatsApp requires you to run your own webhook server (e.g. FastAPI/Flask) and call `adapter.handle_webhook(payload)` when receiving events. Message history retrieval is not supported by the WhatsApp Business API.

### Feishu (飞书)

1. Go to [飞书开放平台](https://open.feishu.cn/app) → Create Custom App
2. **Enable Bot**: App Features → Bot → Enable bot capability (required before adding messaging permissions)
3. In **Credentials & Basic Info**, get your **App ID** and **App Secret**
4. **Permissions**: Add `im:message`, `im:message:send_as_bot`, `im:resource`, `im:chat:readonly` (required for group chats)
5. **Event Subscriptions**: Choose **长连接 (Long Connection)** mode (recommended, no webhook needed), subscribe to `im.message.receive_v1`
6. Publish the app version and have admin approve it
7. Add the bot to a group chat or send it a direct message to start

**Option A: SDK Long Connection (recommended)**

No webhook server or ngrok needed. Install `lark-oapi` and use the built-in WebSocket client:

```bash
pip install lark-oapi
```

```python
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

def on_message(data: P2ImMessageReceiveV1):
    print(data.event.message.content)

event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(on_message)
    .build()
)

ws_client = lark.ws.Client(
    app_id="cli_xxx",
    app_secret="xxx",
    event_handler=event_handler,
    log_level=lark.LogLevel.INFO,
)
ws_client.start()
```

See [examples/feishu_bot.py](examples/feishu_bot.py) for a complete echo bot example.

**Option B: Webhook Callback**

If you prefer the webhook approach, set up a FastAPI/Flask server and configure the callback URL in Feishu Admin. See [examples/feishu_webhook_server.py](examples/feishu_webhook_server.py).

```python
from pig_messenger.adapters import FeishuAdapter

adapter = FeishuAdapter(
    app_id=os.environ["FEISHU_APP_ID"],
    app_secret=os.environ["FEISHU_APP_SECRET"],
    verification_token=os.environ.get("FEISHU_VERIFY_TOKEN"),
    encrypt_key=os.environ.get("FEISHU_ENCRYPT_KEY"),
)
bot.add_platform(adapter)
```

## Advanced Usage

### Custom Tools for Bot

```python
@tool(description="Search company knowledge base")
def search_kb(query: str) -> str:
    # Your implementation
    return f"Results for: {query}"

agent = Agent(
    llm=LLM(),
    tools=[search_kb, ...],
)

bot = MessengerBot(agent)
```

### Per-Platform Configuration

```python
# Different settings per platform
slack = SlackAdapter(...)
discord = DiscordAdapter(...)

bot.add_platform(slack)
bot.add_platform(discord)

# Each platform maintains separate sessions
# slack:C123 → session 1
# discord:987654 → session 2
```

### Session Access

```python
# Access sessions programmatically
sessions = bot.session_manager.list_sessions()

for key, session in sessions.items():
    print(f"{key}: {len(session.tree.entries)} messages")
```

## Architecture

```
User Message (any platform)
    ↓
Platform Adapter (Slack/Discord/Telegram/WhatsApp/Feishu)
    ↓
UniversalMessage (standardized format)
    ↓
MessengerBot (routing)
    ↓
Agent (pig-agent-core)
    ↓
Response
    ↓
Platform Adapter (send back)
    ↓
User sees response
```

## Custom Adapter

Create your own platform adapter:

```python
from pig_messenger import MessagePlatform, UniversalMessage

class MyPlatformAdapter(MessagePlatform):
    def __init__(self, api_key):
        super().__init__("myplatform")
        self.api_key = api_key

    async def send_message(self, channel_id, text, **kwargs):
        # Your implementation
        pass

    async def get_history(self, channel_id, limit):
        # Your implementation
        return []

    def start(self):
        # Start listening
        pass

    def stop(self):
        # Cleanup
        pass

# Use it
bot.add_platform(MyPlatformAdapter(api_key="..."))
```

## Testing

```bash
# Unit tests (no credentials needed)
pytest packages/pig-messenger/tests/test_slack_adapter.py -v
pytest packages/pig-messenger/tests/test_feishu_adapter.py -v
```

## License

MIT
