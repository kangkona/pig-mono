# pig-messenger

Universal messenger abstraction library for building multi-platform bots with production-grade features.

English | [简体中文](./README.zh-CN.md)

## Features

- **Universal Abstractions**: Single API for Telegram, Slack, Discord, WhatsApp, Feishu
- **Streaming Support**: 3-strategy streaming (draft/edit/batch) for real-time responses
- **Distributed State**: Redis-backed state management with agent locking and follow-up queues
- **Production Ready**: Retry logic, error handling, graceful shutdown
- **Type Safe**: Full type hints and dataclass-based models

## Installation

```bash
pip install pig-messenger
```

Optional dependencies:
```bash
pip install pig-messenger[redis]       # For distributed state
pip install pig-messenger[encryption]  # For credential encryption
pip install pig-messenger[telegram]    # For Telegram adapter
pip install pig-messenger[slack]       # For Slack adapter
pip install pig-messenger[discord]     # For Discord adapter
pip install pig-messenger[whatsapp]    # For WhatsApp adapter
pip install pig-messenger[feishu]      # For Feishu adapter
pip install pig-messenger[all]         # All adapters
```

## Quick Start

```python
from pig_messenger import MessengerManager, MessengerRegistry, MessengerType
from pig_messenger.adapters.telegram import TelegramMessengerAdapter

# Register adapter
@MessengerRegistry.register(MessengerType.TELEGRAM)
class MyTelegramAdapter(TelegramMessengerAdapter):
    pass

# Create manager
def agent_factory(message, thread):
    return f"Echo: {message.text}"

manager = MessengerManager(agent_factory=agent_factory)

# Handle events
await manager.handle_event(
    MessengerType.TELEGRAM,
    raw_event,
    adapter=adapter
)
```

## Architecture

### Core Components

- **BaseMessengerAdapter**: Abstract base for platform adapters
- **MessengerThread**: Unified interface for sending messages with streaming
- **MessengerManager**: Orchestrates message lifecycle with agent execution
- **MessengerState**: Redis-backed distributed state management
- **MessengerRegistry**: Decorator-based adapter registration

### Platform Adapters

| Platform | Features | Char Limit |
|----------|----------|------------|
| **Telegram** | Draft streaming, file uploads | 4096 |
| **Slack** | Block Kit, reactions, markdown conversion | 3500 |
| **Discord** | Threads, reactions, embeds | 2000 |
| **WhatsApp** | Twilio-based | 1600 |
| **Feishu** | Card messages, streaming updates | Custom |

## Streaming Strategies

MessengerThread automatically selects the best streaming strategy:

1. **Draft Streaming** (Telegram): Native draft frames with final commit
2. **Edit Streaming** (Slack, Discord): Post initial, edit at intervals, auto-split on overflow
3. **Batch Fallback**: Collect all chunks, split, post sequentially

## Configuration Examples

### Telegram

```python
from pig_messenger.adapters.telegram import TelegramMessengerAdapter, TelegramConfig

config = TelegramConfig.from_env()  # Load from environment
adapter = TelegramMessengerAdapter(config=config)
```

Environment variables:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
```

### Slack

```python
from pig_messenger.adapters.slack import SlackMessengerAdapter, SlackConfig

config = SlackConfig(
    bot_token="xoxb-...",
    signing_secret="..."
)
adapter = SlackMessengerAdapter(config=config)
```

### Discord

```python
from pig_messenger.adapters.discord import DiscordMessengerAdapter, DiscordConfig

config = DiscordConfig(
    bot_token="your_bot_token",
    intents=["guilds", "messages"]
)
adapter = DiscordMessengerAdapter(config=config)
```

### Feishu

```python
from pig_messenger.adapters.feishu import FeishuAdapter

adapter = FeishuAdapter(
    app_id="cli_xxx",
    app_secret="xxx"
)
```

## Distributed State Management

```python
from pig_messenger import MessengerState
import redis.asyncio as redis

# Create Redis connection
redis_client = redis.Redis(host='localhost', port=6379)

# Initialize state management
state = MessengerState(redis_client=redis_client)

# Use in manager
manager = MessengerManager(
    agent_factory=agent_factory,
    state=state
)
```

## Advanced Features

### Streaming Responses

```python
async def streaming_agent(message, thread):
    async def generate_chunks():
        yield "Thinking"
        yield "..."
        yield "\n\nThis is a streaming response!"

    # Automatically selects best strategy
    await thread.stream(generate_chunks())
```

### File Uploads

```python
# Upload from URL
await thread.post_file(
    url="https://example.com/file.pdf",
    filename="document.pdf"
)

# Upload from content
await thread.post_file_content(
    content=file_bytes,
    filename="image.png",
    content_type="image/png"
)
```

### Structured Messages (Slack Block Kit)

```python
blocks = [
    {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Hello World*"}
    }
]
await thread.post_blocks(blocks, text_fallback="Hello World")
```

### Error Handling and Retries

The manager automatically retries transient errors (429, 502, 503, 504) with exponential backoff:

```python
manager = MessengerManager(
    agent_factory=agent_factory,
    max_retries=3,  # Default: 3
    retry_delay=1.0  # Default: 1.0 second
)
```

## Development

```bash
# Install dev dependencies
pip install pig-messenger[dev]

# Run tests
pytest tests/

# Type checking
mypy src/pig_messenger/

# Code formatting
ruff format src/
```

## License

MIT

## Links

- [GitHub Repository](https://github.com/kangkona/pig-mono)
- [Issue Tracker](https://github.com/kangkona/pig-mono/issues)
