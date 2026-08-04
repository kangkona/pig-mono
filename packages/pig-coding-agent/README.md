# pig-coding-agent

[![PyPI version](https://badge.fury.io/py/pig-coding-agent.svg)](https://badge.fury.io/py/pig-coding-agent)
[![Python](https://img.shields.io/pypi/pyversions/pig-coding-agent.svg)](https://pypi.org/project/pig-coding-agent/)

Interactive coding agent CLI with file operations, session/runtime orchestration,
and a terminal UI built on the `pig-tui` platform layer.

## Features

- 💻 **Code Generation**: AI-powered code generation
- 📁 **File Operations**: Read and write files inside the workspace
- 🔍 **Code Analysis**: Understand and analyze code
- 🛠️ **Refactoring**: Automated code refactoring
- 🐚 **Shell Integration**: Execute shell commands
- 💬 **Interactive Chat**: Conversational interface
- 🔄 **Resilience**: Automatic API key rotation and fallback (NEW in v0.0.4)
- 💰 **Cost Tracking**: Track LLM and tool usage costs (NEW in v0.0.4)

## Architecture

`pig-coding-agent` is now structured so that:

- application semantics and orchestration stay in `pig-coding-agent`
- reusable terminal presentation primitives live in `pig-tui`
- the interactive shell lifecycle now lives in a dedicated `InteractiveMode`
- slash-command dispatch now splits across `InteractionRuntime`, `InteractionDispatcher`,
  and `InteractionRoutes`
- imperative command handlers live in `InteractionCommands`
- selector/editor/session/tree/settings flows live in `InteractionFlows`
- user-facing panel/status/result reporting lives in `InteractionViews`
- session/tree/settings/export/copy-style application actions live in `AppActions`

That means session/status/tree/skills/extensions/prompts displays increasingly
flow through `pig-tui` platform abstractions instead of being assembled inline
inside the agent runtime, and the main `CodingAgent` class is increasingly an
application assembly/orchestration surface rather than the place where the
interactive loop itself lives.

## Installation

```bash
pip install pig-coding-agent "pig-llm[openai]"
```

Replace `openai` with the `pig-llm` provider extra you use. Provider SDKs are
optional so installing the coding-agent package alone does not pull every SDK.

## Quick Start

### Embed with durable run integrity

The synchronous Python SDK keeps durable run recording opt-in. Pass a SQLite
path when the host needs replayable provider/tool attempt evidence and a
verifiable terminal result:

```python
from pathlib import Path

from pig_coding_agent import create_agent_session
from pig_coding_agent.permissions import PermissionPolicy
from pig_llm import LLM

runtime = create_agent_session(
    workspace=Path.cwd(),
    llm=LLM(provider="openai"),
    project_trust=True,
    permission_policy=PermissionPolicy.unattended(),
    run_ledger_path=Path(".agents/runs.sqlite3"),
    run_owner_id="my-python-host",
)

try:
    result = runtime.prompt_result("Explain this repository")
    run_id = runtime.last_run_id
    if run_id is not None and runtime.run_store is not None:
        verified = runtime.run_store.verify(run_id)
        print(verified.run.status.value, result.content)
finally:
    runtime.close()
```

The ledger stores prompt, target, argument, result, and error digests rather than
their raw values. Provider calls and tool effects fail closed when their durable
boundary cannot be recorded. Leaving out `run_ledger_path` preserves the
existing in-process SDK behavior and creates no ledger.

### Start Interactive Session

```bash
# Start coding agent
pig

# With specific model
pig --model gpt-4

# In a specific directory
pig --path /path/to/project
```

### Command Line Usage

```bash
# Generate code
pig gen "Create a FastAPI hello world app"

# Analyze file
pig analyze main.py
```

## Built-in Tools

The coding agent comes with these tools:

### File Operations

- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `list_files(directory)` - List directory contents
- `grep_files(pattern, path)` - Search for text in files
- `find_files(pattern, path)` - Find files by glob pattern
- `ls_detailed(path)` - List files with metadata

### Shell Operations

- `run_command(command)` - Execute shell command

## Usage Examples

### Generate a Python Module

```bash
$ pig
> Create a Python module for handling JSON files with read/write functions

Agent will:
1. Generate the code
2. Write to file
3. Show you the result
```

### Analyze Codebase

```bash
$ pig analyze .

Agent will:
1. Read relevant files
2. Analyze structure
3. Provide recommendations
```

### Interactive Editing

```bash
$ pig
> Refactor main.py to use async/await

Agent will:
1. Read the file
2. Propose a change
3. Request confirmation before writing files or running shell commands
4. Apply the approved change
```

## Configuration

Create `.agents/config.json`:

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "temperature": 0.7,
  "auto_compact": true,
  "auto_compact_threshold": 0.85,
  "enable_extensions": true,
  "enable_skills": true
}
```

Project-local configuration, instructions, prompts, skills, package roots, and
extensions are loaded only after the canonical workspace is trusted. Interactive
TTY runs can remember that decision. JSON/RPC, piped input, and the SDK fail
closed unless the host supplies an explicit trust decision; global resources
under `~/.agents` and `~/.pi/agent` remain independent of project trust.
An explicit `/settings` edit may create a new project config in an untrusted
workspace, but it will not parse or merge a pre-existing untrusted config.

## Chat Commands

Inside the agent:

```
/help       - Show help
/exit       - Exit agent
/clear      - Clear conversation
/files      - List files in workspace
/status     - Show agent status
/resilience - Show resilience status (API keys, rotation)
/cost       - Show cost tracking summary
/usage      - Show usage statistics
```

## Resilience Features (v0.0.4)

The agent now supports automatic resilience for production stability:

### API Key Rotation

Set multiple API keys for automatic rotation on rate limits:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_API_KEY_2=sk-...
export OPENAI_API_KEY_3=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_API_KEY_2=sk-ant-...
```

The agent will automatically:
- Rotate to next available key on rate limits
- Apply per-failure-type cooldowns (AUTH=5min, RATE_LIMIT=1min, etc.)
- Fall back to alternative models on context overflow

### Check Resilience Status

```bash
$ pig
> /resilience

Resilience Status
─────────────────
Total API keys: 5
Available: 4
In cooldown: 1

Profiles:
1. openai (key #0): ✓
2. openai (key #2): ✓
3. openai (key #3): ✗ (cooldown)
4. anthropic (key #0): ✓
5. anthropic (key #2): ✓
```

### Disable Resilience

```bash
pig --no-resilience
```

## Cost Tracking (v0.0.4)

Track LLM and tool usage costs automatically:

### View Cost Summary

```bash
$ pig
> /cost

Usage Summary
─────────────
Total LLM calls: 42
Total tool calls: 156
Total tokens: 125,430 in + 38,920 out
Total cost: $2.4580

By Model:
  gpt-4: 15 calls, 45,230 in + 12,450 out, $1.8900
  gpt-3.5-turbo: 27 calls, 80,200 in + 26,470 out, $0.5680

By Tool:
  read_file: 45 calls
  write_file: 23 calls
  run_command: 88 calls
```

### Usage Data Location

Cost data is saved to `.agents/usage.json` in your workspace.

### Disable Cost Tracking

```bash
pig --no-cost-tracking
```

## Safety Features

- Project-local `.agents`/`.pi` settings, instructions, prompts, skills,
  packages, and extensions are gated by a separate workspace trust decision.
  The decision is keyed by the canonical workspace path and remembered in
  `~/.agents/project-trust.json`. Unknown workspaces fail closed in JSON/RPC,
  piped, and SDK usage. Interactive CLI sessions ask once; `--approve` and
  `--no-approve` provide explicit per-run overrides.
- Global resources under `~/.agents` and `~/.pi/agent` remain available even
  when project-local resources are denied.
- Interactive `pig` sessions require confirmation before `write_file`,
  `run_command`, or an extension-provided `edit_file` can run.
- JSON/RPC modes, piped stdin, `pig gen`, and `pig analyze` install the same
  fail-closed unattended policy. Denials use the stable code
  `tool_permission_denied` and the message
  `Permission denied: side-effectful tools are disabled in unattended mode`.
- JSON emits a `permission_denied` event, RPC `complete` returns a
  `permissionDenials` array, and direct RPC `bash` returns the denial in
  `result.error`. Piped stdin, `pig gen`, and `pig analyze` print the stable
  `tool_permission_denied: ...` text and exit with status 2.
- The embeddable SDK also defaults to that deny policy. A host must explicitly
  pass `PermissionPolicy.confirm_all(...)` or `PermissionPolicy.allow_all()` to
  enable side effects. `prompt()` returns the stable denial text, while
  `prompt_result()` also exposes the machine-readable `permission_denials`.
- `pig gen --output FILE` is an explicit CLI write to the requested file; model
  tool calls remain denied during the generation turn, and a denied turn does
  not create the output file.
- File-tool paths remain constrained to the configured workspace.

`edit_file` is not a built-in tool today. The permission boundary reserves that
name so an extension cannot introduce an unconfirmed edit path. Registry/SDK
tool failures carry a `permission_denial` metadata object with `code`,
`message`, `action`, and `target`.

## Architecture

```
CodingAgent
├── Agent Core (pig-agent-core)
├── LLM Client (pig-llm)
├── TUI (pig-tui)
└── Built-in Tools
    ├── FileTools
    └── ShellTools
```

## Examples

The package currently focuses on the interactive CLI, session handling, and embeddable runtime API.

## License

MIT
