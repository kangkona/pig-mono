# Project Context - Example AGENTS.md

This file provides project-specific context to the coding agent.

## Project: pig-mono

This is a Python monorepo for AI agent development, inspired by pi-mono.

## Conventions

### Code Style
- Use type hints for all function signatures
- Write docstrings for all public functions
- Follow PEP 8 style guide
- Use ruff for linting and formatting

### Project Structure
```
pig-mono/
├── packages/          # Monorepo packages
│   ├── pig-llm/        # LLM API
│   ├── pig-agent-core/ # Agent runtime
│   └── ...
├── tests/            # Integration tests
└── examples/         # Usage examples
```

### Testing
- All new features must have tests
- Maintain >80% coverage for core packages
- Use pytest for all tests
- Mock external API calls

### Documentation
- Every package has a README.md
- Use docstrings for inline documentation
- Keep examples up to date

## Common Tasks

### Adding a New Tool
```python
from pig_agent_core import tool

@tool(description="Tool description")
def my_tool(arg: str) -> str:
    '''Docstring here.'''
    return f"Result: {arg}"
```

### Running Tests
```bash
pytest packages/package-name/tests/
```

### Common Commands
- `./scripts/install-dev.sh` - Install all packages
- `./scripts/test.sh` - Run all tests
- `./scripts/lint.sh` - Check code quality

## Preferences

- Prefer composition over inheritance
- Keep functions small and focused
- Use Pydantic for data validation
- Avoid global state
- Write self-documenting code

## Notes

When suggesting changes:
- Always maintain backward compatibility
- Update tests when changing code
- Update documentation when adding features
- Follow existing patterns in the codebase
