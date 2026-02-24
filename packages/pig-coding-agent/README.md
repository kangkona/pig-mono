# pig-coding-agent

Interactive coding agent CLI with file operations and code generation.

## Features

- 💻 **Code Generation**: AI-powered code generation
- 📁 **File Operations**: Read, write, edit files
- 🔍 **Code Analysis**: Understand and analyze code
- 🛠️ **Refactoring**: Automated code refactoring
- 🐚 **Shell Integration**: Execute shell commands
- 💬 **Interactive Chat**: Conversational interface

## Installation

```bash
pip install pig-coding-agent
```

## Quick Start

### Start Interactive Session

```bash
# Start coding agent
pig-code

# With specific model
pig-code --model gpt-4

# In a specific directory
pig-code --path /path/to/project
```

### Command Line Usage

```bash
# Generate code
pig-code gen "Create a FastAPI hello world app"

# Analyze file
pig-code analyze main.py

# Refactor code
pig-code refactor main.py "Add type hints"

# Chat mode
pig-code chat
```

## Built-in Tools

The coding agent comes with these tools:

### File Operations

- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `list_files(directory)` - List directory contents
- `search_files(pattern)` - Search for files

### Code Operations

- `generate_code(description)` - Generate code from description
- `explain_code(code)` - Explain what code does
- `fix_code(code, error)` - Fix code errors
- `add_tests(code)` - Generate tests for code

### Shell Operations

- `run_command(command)` - Execute shell command
- `git_status()` - Get git status
- `git_diff()` - Get git diff

## Usage Examples

### Generate a Python Module

```bash
$ pig-code
> Create a Python module for handling JSON files with read/write functions

Agent will:
1. Generate the code
2. Write to file
3. Show you the result
```

### Analyze Codebase

```bash
$ pig-code analyze
> Analyze this codebase and suggest improvements

Agent will:
1. Read relevant files
2. Analyze structure
3. Provide recommendations
```

### Interactive Refactoring

```bash
$ pig-code
> Refactor main.py to use async/await

Agent will:
1. Read the file
2. Refactor the code
3. Show diff
4. Ask for confirmation
5. Write changes
```

## Configuration

Create `.pig-code-config.json`:

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_iterations": 10,
  "auto_confirm": false,
  "workspace": "./",
  "ignore_patterns": [
    "node_modules",
    ".git",
    "__pycache__"
  ]
}
```

## Chat Commands

Inside the agent:

```
/help       - Show help
/exit       - Exit agent
/clear      - Clear conversation
/files      - List files in workspace
/read PATH  - Read a file
/write PATH - Write to file
/run CMD    - Run shell command
/status     - Show agent status
```

## Safety Features

- File operation confirmations
- Command execution warnings
- Workspace boundaries
- Backup before overwrite
- Git integration for tracking changes

## Architecture

```
CodingAgent
├── Agent Core (pig-agent-core)
├── LLM Client (pig-llm)
├── TUI (pig-tui)
└── Built-in Tools
    ├── FileTools
    ├── CodeTools
    └── ShellTools
```

## Examples

See `examples/coding-agent/`:
- `generate_app.py` - Generate full application
- `refactor_demo.py` - Code refactoring
- `analysis_demo.py` - Code analysis

## License

MIT
