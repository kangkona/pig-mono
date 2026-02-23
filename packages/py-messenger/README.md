# py-messenger

**Universal Multi-Platform Bot Framework** 🌍

One agent, multiple messaging platforms. Write once, deploy everywhere.

## Features

- 🌍 **Multi-Platform**: Slack, Discord, Telegram, WhatsApp, Feishu, and more
- 🔌 **Plug-in Architecture**: Easy to add new platforms
- 🤖 **Powered by py-agent-core**: Full agent capabilities
- 💾 **Session Management**: Per-channel conversation history
- 📁 **File Handling**: Upload/download across platforms
- 🎯 **Unified API**: Same code for all platforms

## Supported Platforms

| Platform | Status | Use Case |
|----------|--------|----------|
| **Slack** | ✅ Ready | Enterprise (Global) |
| **Discord** | ✅ Ready | Developer Communities |
| **Telegram** | ✅ Ready | Personal & Groups |
| **WhatsApp** | ✅ Ready | Personal Communication |
| **Feishu (飞书)** | ✅ Ready | Enterprise (China) |
| Matrix | 🔜 Coming | Open Federation |
| WeChat | 🔜 Future | China Social |

## Installation

```bash
# Base
pip install py-messenger

# With Slack support
pip install py-messenger[slack]

# With all platforms
pip install py-messenger[all]
```

## Quick Start

### Single Platform (Slack)

```python
from py_messenger import MessengerBot
from py_messenger.adapters import SlackAdapter
from py_agent_core import Agent, tool
from py_ai import LLM

# Create your agent
@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

agent = Agent(
    llm=LLM(provider="openai"),
    tools=[get_time],
    system_prompt="You are a helpful assistant."
)

# Create bot
bot = MessengerBot(agent)

# Add Slack
slack = SlackAdapter(
    app_token="xapp-...",
    bot_token="xoxb-..."
)
bot.add_platform(slack)

# Start!
bot.start()
```

### Multi-Platform Bot

```python
# Same agent, multiple platforms!

bot = MessengerBot(agent)

# Add Slack
bot.add_platform(SlackAdapter(
    app_token="xapp-...",
    bot_token="xoxb-..."
))

# Add Discord
bot.add_platform(DiscordAdapter(
    bot_token="your-discord-token"
))

# Add Telegram
bot.add_platform(TelegramAdapter(
    bot_token="your-telegram-token"
))

# Start all platforms at once!
bot.start()
```

## Platform Setup

### Slack

1. Create app at https://api.slack.com/apps
2. Enable Socket Mode
3. Add Bot Token Scopes:
   - `app_mentions:read`
   - `chat:write`
   - `files:read`
   - `files:write`
4. Get app token (xapp-...) and bot token (xoxb-...)

```python
from py_messenger.adapters import SlackAdapter

slack = SlackAdapter(
    app_token="xapp-1-...",
    bot_token="xoxb-..."
)
```

### Discord

1. Create app at https://discord.com/developers
2. Add bot with permissions:
   - Read Messages
   - Send Messages
   - Attach Files
3. Get bot token

```python
from py_messenger.adapters import DiscordAdapter

discord = DiscordAdapter(bot_token="your-token")
```

### Telegram

1. Talk to @BotFather
2. Create new bot
3. Get token

```python
from py_messenger.adapters import TelegramAdapter

telegram = TelegramAdapter(bot_token="your-token")
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
Platform Adapter (Slack/Discord/Telegram)
    ↓
UniversalMessage (standardized format)
    ↓
MessengerBot (routing)
    ↓
Agent (py-agent-core)
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
from py_messenger import MessagePlatform, UniversalMessage

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

## CLI Usage

```bash
# Start with config file
py-messenger --config config.yml

# config.yml:
# platforms:
#   - type: slack
#     app_token: xapp-...
#     bot_token: xoxb-...
#   - type: discord
#     bot_token: ...
```

## Examples

See `examples/` directory:
- `slack_bot.py` - Slack bot
- `discord_bot.py` - Discord bot
- `multi_platform.py` - Multi-platform bot
- `custom_adapter.py` - Custom adapter example

## Comparison

### vs pi-mom

| Feature | pi-mom | py-messenger |
|---------|--------|--------------|
| Platforms | Slack only | **5+ platforms** |
| Extensibility | Fixed | **Plug-in based** |
| Session | Per-channel | **Per-platform+channel** |
| Code reuse | N/A | **High** |

### Advantages

- ✅ Write once, deploy everywhere
- ✅ Easy to add new platforms
- ✅ Unified session management
- ✅ Same agent capabilities everywhere
- ✅ Future-proof architecture

## License

MIT
