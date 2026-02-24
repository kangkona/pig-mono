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
| **Feishu (飞书)** | ✅ Ready | Enterprise (China) |

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
from pig_messenger.adapters import SlackAdapter, DiscordAdapter, TelegramAdapter

bot = MessengerBot(agent)
bot.add_platform(SlackAdapter(
    app_token=os.environ["SLACK_APP_TOKEN"],
    bot_token=os.environ["SLACK_BOT_TOKEN"],
))
bot.add_platform(DiscordAdapter(bot_token=os.environ["DISCORD_BOT_TOKEN"]))
bot.add_platform(TelegramAdapter(bot_token=os.environ["TELEGRAM_BOT_TOKEN"]))
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

1. Create app at https://discord.com/developers
2. Add bot with permissions: Read Messages, Send Messages, Attach Files
3. Get bot token

### Telegram

1. Talk to @BotFather, create new bot
2. Get token

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
Platform Adapter (Slack/Discord/Telegram)
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
# Unit tests (no Slack credentials needed)
pytest packages/pig-messenger/tests/test_slack_adapter.py -v
```

## License

MIT
