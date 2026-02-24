# pig-tui

Terminal UI library with rich formatting and interactive components.

## Features

- 🎨 **Rich Formatting**: Colors, styles, markdown rendering
- 💬 **Chat Interface**: Ready-to-use chat UI components
- ⚡ **Streaming Support**: Real-time text streaming
- 🎯 **Interactive Input**: Advanced prompt with autocomplete
- 📊 **Progress Indicators**: Spinners, progress bars
- 🔄 **Differential Rendering**: Efficient screen updates

## Installation

```bash
pip install pig-tui
```

## Quick Start

### Simple Chat Interface

```python
from pig_tui import ChatUI

# Create chat UI
chat = ChatUI(title="My AI Assistant")

# Display messages
chat.user("Hello!")
chat.assistant("Hi! How can I help you?")

# Stream response
with chat.assistant_stream() as stream:
    for chunk in generate_response():
        stream.write(chunk)
```

### Markdown Rendering

```python
from pig_tui import Console

console = Console()
console.markdown("""
# Hello World

This is **bold** and this is *italic*.

- Item 1
- Item 2

\`\`\`python
def hello():
    print("Hello!")
\`\`\`
""")
```

### Progress Indicators

```python
from pig_tui import Progress, Spinner

# Progress bar
with Progress() as progress:
    task = progress.add_task("Processing...", total=100)
    for i in range(100):
        progress.update(task, advance=1)

# Spinner
with Spinner("Loading...") as spinner:
    do_long_task()
```

### Interactive Input

```python
from pig_tui import Prompt

prompt = Prompt()

# Simple input
name = prompt.ask("What's your name?")

# With validation
age = prompt.ask("Your age?", validate=lambda x: x.isdigit())

# With autocomplete
color = prompt.ask(
    "Favorite color?",
    choices=["red", "blue", "green"]
)
```

## Components

### ChatUI

Full-featured chat interface:

```python
from pig_tui import ChatUI

chat = ChatUI(
    title="Assistant",
    theme="dark",  # or "light"
    show_timestamps=True,
)

# User message
chat.user("Hello")

# Assistant message
chat.assistant("Hi there!")

# System message
chat.system("Model: gpt-4")

# Stream assistant response
with chat.assistant_stream() as stream:
    stream.write("Streaming ")
    stream.write("response...")

# Error message
chat.error("Something went wrong")
```

### Console

Rich console output:

```python
from pig_tui import Console

console = Console()

# Print with style
console.print("Hello", style="bold blue")

# Markdown
console.markdown("# Title")

# JSON pretty print
console.json({"key": "value"})

# Code syntax highlighting
console.code('print("hello")', language="python")

# Table
from rich.table import Table
table = Table()
table.add_column("Name")
table.add_column("Value")
table.add_row("foo", "bar")
console.print(table)
```

### Prompt

Interactive prompts:

```python
from pig_tui import Prompt

prompt = Prompt()

# Text input
name = prompt.ask("Name:")

# Password
password = prompt.ask("Password:", password=True)

# Confirm
confirmed = prompt.confirm("Continue?")

# Choice
option = prompt.choice("Select:", ["A", "B", "C"])

# Multiple choice
selected = prompt.multi_choice("Select multiple:", ["A", "B", "C"])
```

## Theming

```python
from pig_tui import ChatUI, Theme

# Custom theme
theme = Theme(
    user_color="cyan",
    assistant_color="green",
    system_color="yellow",
    error_color="red",
)

chat = ChatUI(theme=theme)
```

## Examples

See `examples/tui/` directory:
- `chat_demo.py` - Chat interface demo
- `streaming_demo.py` - Streaming text demo
- `prompt_demo.py` - Interactive prompts
- `progress_demo.py` - Progress indicators

## License

MIT
