# pig-messenger

Universal messenger abstraction library for building multi-platform bots with production-grade features.

## Features

- **Universal Abstractions**: Single API for Telegram, Slack, Discord, WhatsApp
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
pip install pig-messenger[redis]  # For distributed state
pip install pig-messenger[telegram]  # For Telegram adapter
pip install pig-messenger[slack]  # For Slack adapter
```

## Quick Start

```python
from pig_messenger import MessengerManager, MessengerRegistry
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

- **Telegram**: Draft streaming, file uploads, 4096 char limit
- **Slack**: Block Kit, reactions, markdown conversion, 3500 char limit
- **Discord**: Threads, reactions, embeds, 2000 char limit
- **WhatsApp**: Twilio-based, 1600 char limit

## Streaming Strategies

MessengerThread automatically selects the best streaming strategy:

1. **Draft Streaming** (Telegram): Native draft frames with final commit
2. **Edit Streaming** (Slack, Discord): Post initial, edit at intervals, auto-split on overflow
3. **Batch Fallback**: Collect all chunks, split, post sequentially

## License

MIT
