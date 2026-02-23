# py-web-ui

Web UI components for AI chat interfaces with FastAPI backend.

## Features

- 🚀 **FastAPI Backend**: High-performance async web server
- 💬 **Chat Interface**: Ready-to-use chat UI
- ⚡ **SSE Streaming**: Server-Sent Events for real-time responses
- 🎨 **Modern UI**: Clean, responsive design
- 🔌 **Easy Integration**: Works with py-agent-core
- 📱 **Mobile Friendly**: Responsive design

## Installation

```bash
pip install py-web-ui
```

## Quick Start

### Simple Chat Server

```python
from py_web_ui import ChatServer
from py_ai import LLM

# Create server
server = ChatServer(
    llm=LLM(provider="openai"),
    title="My AI Assistant",
    port=8000,
)

# Run server
server.run()
```

Then open `http://localhost:8000` in your browser!

### With Agent and Tools

```python
from py_web_ui import ChatServer
from py_ai import LLM
from py_agent_core import Agent, tool

@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

# Create agent
agent = Agent(
    llm=LLM(),
    tools=[get_time],
    system_prompt="You are a helpful assistant.",
)

# Create server with agent
server = ChatServer(agent=agent, title="Time Assistant")
server.run()
```

### Custom Routes

```python
from py_web_ui import ChatServer
from fastapi import Request

server = ChatServer(llm=LLM())

@server.app.get("/custom")
async def custom_route():
    return {"message": "Custom endpoint"}

server.run()
```

## API Usage

### Chat Endpoint

```bash
# Send message (SSE streaming)
curl -N http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'

# Response streams as SSE:
# data: {"type": "start"}
# data: {"type": "token", "content": "Hi"}
# data: {"type": "token", "content": " there"}
# data: {"type": "done"}
```

### WebSocket Support

```python
from py_web_ui import ChatServer

server = ChatServer(llm=LLM(), use_websocket=True)
server.run()
```

```javascript
// Client-side
const ws = new WebSocket('ws://localhost:8000/ws');
ws.send(JSON.stringify({message: "Hello"}));
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data.content);
};
```

## Configuration

### Server Options

```python
server = ChatServer(
    llm=LLM(),
    title="My Assistant",
    port=8000,
    host="0.0.0.0",
    cors=True,
    api_prefix="/api",
    static_dir="./static",
)
```

### Environment Variables

```bash
export OPENAI_API_KEY=your-key
export WEB_UI_PORT=8000
export WEB_UI_HOST=0.0.0.0
```

## UI Customization

### Custom Theme

```python
theme = {
    "primary_color": "#007bff",
    "background_color": "#ffffff",
    "message_user_bg": "#007bff",
    "message_assistant_bg": "#f0f0f0",
}

server = ChatServer(llm=LLM(), theme=theme)
```

### Custom Templates

```python
server = ChatServer(
    llm=LLM(),
    template_dir="./my_templates",
)
```

Create `my_templates/chat.html`:
```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <!-- Your custom HTML -->
</head>
<body>
    <!-- Your custom chat UI -->
</body>
</html>
```

## CLI Usage

```bash
# Start server with default settings
py-webui

# Specify model and port
py-webui --model gpt-4 --port 8080

# With agent configuration
py-webui --agent-config agent.json
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install py-web-ui
CMD ["py-webui", "--host", "0.0.0.0"]
```

### Production

```bash
# Use gunicorn
gunicorn py_web_ui.app:create_app -k uvicorn.workers.UvicornWorker
```

## Components

### ChatServer

Main server class:

```python
from py_web_ui import ChatServer

server = ChatServer(
    llm=None,           # LLM instance
    agent=None,         # Or Agent instance
    title="Chat",       # Page title
    port=8000,         # Server port
    host="127.0.0.1",  # Server host
    cors=False,        # Enable CORS
)
```

### Endpoints

- `GET /` - Chat interface
- `POST /api/chat` - Send message (SSE stream)
- `GET /api/history` - Get chat history
- `DELETE /api/history` - Clear history
- `WS /ws` - WebSocket connection (if enabled)

## Examples

See `examples/web-ui/`:
- `basic_server.py` - Basic chat server
- `agent_server.py` - Server with agent and tools
- `custom_ui.py` - Custom UI example
- `websocket_demo.py` - WebSocket example

## Architecture

```
Browser
    ↓
FastAPI Server
    ↓
ChatServer
    ↓
Agent/LLM (py-agent-core/py-ai)
```

## License

MIT
