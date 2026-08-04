# pig-mono

> Python-native, embeddable agent runtime and application toolkit.

[![CI](https://github.com/kangkona/pig-mono/actions/workflows/ci.yml/badge.svg)](https://github.com/kangkona/pig-mono/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![PyPI: pig-coding-agent](https://img.shields.io/pypi/v/pig-coding-agent.svg)](https://pypi.org/project/pig-coding-agent/)

pig-mono is a Python monorepo for building LLM clients, agent loops, terminal
applications, web interfaces, and messaging integrations. Its architectural
direction is a reusable Python runtime with explicit policy boundaries and
verifiable run integrity.

The `0.2.0` release establishes the runtime baseline. It does not claim that the
later run-integrity roadmap is already complete.

## What 0.2.0 provides

- A provider/model runtime with credential resolution, capability metadata,
  refreshable model catalogs, and provider-scoped failure handling.
- Sync and async agent loops with streaming, cancellation, tool execution,
  steering messages, follow-up messages, and structured turn outcomes.
- Tree-backed sessions with branch-local tool activation and durable compaction
  checkpoints.
- Semantic compaction that keeps an exact recent tail and leaves durable session
  state unchanged when summarization or atomic persistence fails.
- Model-capability gates for deferred tools, strict JSON schemas, and grammar
  constraints.
- A Python embedding surface through `create_agent_session()`.
- Project-trust and side-effect permission boundaries. Non-interactive and SDK
  hosts deny side-effectful tools unless the host supplies an explicit policy.
- Reusable terminal interaction primitives, a coding-agent CLI, a web UI, and
  messaging adapters.
- Strict repository type checking and a release pipeline that verifies tag,
  package, import, dependency, and published-artifact facts.

## What is not yet provided

The current runtime does not yet provide a durable `Run` authority, an
append-only operation/evidence ledger, crash recovery with an explicit
`outcome_unknown` state, process isolation, transport-neutral async hosting,
MCP/ACP adapters, or governed multi-agent workers. These are sequenced in the
[runtime roadmap](docs/roadmap.md), with the accepted direction recorded in
[ADR-001](docs/decisions/ADR-001-python-runtime-and-run-integrity.md).

## Packages

The workspace metadata and all public packages in the `0.2.0` release use the
same version so a tag maps to one coherent source and dependency baseline.

| Package | Role |
| --- | --- |
| [`pig-llm`](packages/pig-llm) | Provider-neutral LLM client and provider/model runtime |
| [`pig-agent-core`](packages/pig-agent-core) | Agent loop, tools, sessions, compaction, resilience, and usage records |
| [`pig-tui`](packages/pig-tui) | Reusable terminal presentation and interaction runtime |
| [`pig-coding-agent`](packages/pig-coding-agent) | Interactive CLI and embeddable coding-agent session |
| [`pig-web-ui`](packages/pig-web-ui) | FastAPI-based chat application surface |
| [`pig-messenger`](packages/pig-messenger) | Messaging abstractions and optional platform adapters |

## Install

Install only the surfaces an application needs:

```bash
python -m pip install pig-llm pig-agent-core
python -m pip install pig-coding-agent
python -m pip install pig-web-ui
python -m pip install "pig-messenger[slack]"
```

For a source checkout:

```bash
git clone https://github.com/kangkona/pig-mono.git
cd pig-mono
uv sync --all-packages
```

## Use the coding agent

The interactive CLI asks for provider/model configuration when needed:

```bash
pig
```

It can also be configured explicitly:

```bash
export OPENAI_API_KEY=your-key
pig --provider openai --model gpt-4o-mini
```

Inside an interactive session:

```text
Review @src/main.py for bugs
/tree
/settings
/cost
!Stop and explain the current action
>>After that, add focused tests
```

Writes and shell commands require confirmation in an interactive terminal.
JSON, RPC, piped-input, and default SDK routes fail closed instead of silently
performing side effects.

## Embed a session in Python

```python
from pig_coding_agent import create_agent_session
from pig_llm import LLM

runtime = create_agent_session(
    workspace=".",
    llm=LLM(provider="openai", model="gpt-4o-mini"),
    project_trust=False,
)

try:
    result = runtime.prompt_result("Summarize the repository structure")
    print(result.content)
    print(result.outcome.value)
    print(result.permission_denials)
finally:
    runtime.close()
```

The default SDK permission policy denies writes and shell commands. A host must
pass an explicit `PermissionPolicy` to authorize or confirm those operations.

## Architecture boundaries

```text
Applications
├── pig-coding-agent
├── pig-web-ui
└── pig-messenger
        │
Runtime and presentation
├── pig-agent-core
└── pig-tui
        │
Model/provider boundary
└── pig-llm
```

- `pig-llm` owns provider construction, model metadata, credentials, and model
  capability facts.
- `pig-agent-core` owns agent/session/tool behavior. It does not yet own the
  durable `Run` ledger described in the roadmap.
- Application packages own host UX and policy decisions. SDK hosts must make
  trust and side-effect authority explicit.

## Development and verification

```bash
uv sync --all-packages

./scripts/lint.sh
./scripts/typecheck.sh
./scripts/run-tests.sh

python scripts/verify_release.py --tag v0.2.0
```

CI runs linting, formatting checks, strict typing, tests, and package builds on
Python 3.10–3.12 across Linux, macOS, and Windows. See the [testing guide](TESTING.md)
for the exact local commands.

## Documentation

- [Runtime roadmap](docs/roadmap.md)
- [Architecture decision: Python runtime and run integrity](docs/decisions/ADR-001-python-runtime-and-run-integrity.md)
- [Testing guide](TESTING.md)
- [Quick start](QUICKSTART.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
