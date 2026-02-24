# Testing Guide

## Overview

pig-mono has comprehensive test coverage across all packages with unit tests, integration tests, and CI/CD automation.

## Test Structure

```
pig-mono/
├── tests/                      # Integration tests
│   └── test_integration.py
├── packages/
│   ├── pig-llm/tests/           # pig-llm unit tests
│   │   ├── test_models.py
│   │   ├── test_config.py
│   │   └── test_client.py
│   ├── pig-agent-core/tests/   # pig-agent-core unit tests
│   │   ├── test_tools.py
│   │   ├── test_registry.py
│   │   └── test_agent.py
│   ├── pig-tui/tests/          # pig-tui unit tests
│   │   ├── test_theme.py
│   │   ├── test_console.py
│   │   └── test_chat.py
│   └── pig-web-ui/tests/       # pig-web-ui unit tests
│       ├── test_models.py
│       └── test_server.py
└── pytest.ini                  # Pytest configuration
```

## Running Tests

### All Tests

```bash
# Run all tests with coverage
./scripts/run-tests.sh

# Or manually
pytest

# With coverage report
pytest --cov=packages --cov-report=html
open htmlcov/index.html
```

### Specific Package

```bash
# Test specific package
pytest packages/pig-llm/tests/

# Test specific file
pytest packages/pig-llm/tests/test_models.py

# Test specific function
pytest packages/pig-llm/tests/test_models.py::test_message_creation
```

### Test Categories

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Test Coverage

### Current Coverage by Package

| Package | Tests | Coverage |
|---------|-------|----------|
| pig-llm | 12+ tests | ~85% |
| pig-agent-core | 15+ tests | ~80% |
| pig-tui | 10+ tests | ~75% |
| pig-web-ui | 8+ tests | ~70% |
| Integration | 5+ tests | N/A |

### Total: 50+ tests

## Writing Tests

### Unit Test Example

```python
# packages/pig-llm/tests/test_models.py

def test_message_creation():
    """Test message creation."""
    from pig_llm.models import Message
    
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
```

### Integration Test Example

```python
# tests/test_integration.py

def test_ai_to_agent_integration():
    """Test pig-llm integration with pig-agent-core."""
    from pig_llm import LLM
    from pig_agent_core import Agent
    
    llm = LLM(provider="openai", api_key="test")
    agent = Agent(llm=llm)
    
    assert agent.llm == llm
```

### Using Mocks

```python
from unittest.mock import Mock, patch

def test_with_mock_llm():
    """Test with mocked LLM."""
    mock_llm = Mock()
    mock_llm.complete = Mock(return_value=Mock(content="Test"))
    
    agent = Agent(llm=mock_llm)
    # Test agent behavior
```

### Fixtures

```python
import pytest

@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm

def test_with_fixture(mock_llm):
    """Test using fixture."""
    agent = Agent(llm=mock_llm)
    assert agent.llm == mock_llm
```

## Test Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests packages/*/tests
python_files = test_*.py
addopts = -v --cov=packages --cov-report=term-missing
markers =
    integration: Integration tests
    unit: Unit tests
    slow: Slow running tests
```

### Markers

Use markers to categorize tests:

```python
import pytest

@pytest.mark.unit
def test_unit():
    """Unit test."""
    pass

@pytest.mark.integration
def test_integration():
    """Integration test."""
    pass

@pytest.mark.slow
def test_slow():
    """Slow test."""
    pass
```

## Coverage Reports

### Generate Reports

```bash
# Terminal report
pytest --cov=packages --cov-report=term-missing

# HTML report
pytest --cov=packages --cov-report=html
# Open htmlcov/index.html

# XML report (for CI)
pytest --cov=packages --cov-report=xml
```

### Viewing Coverage

```bash
# Open HTML coverage report
open htmlcov/index.html

# Or use coverage command
coverage report
coverage html
```

## Continuous Integration

Tests run automatically on:
- Every push to main/develop
- Every pull request
- Multiple Python versions (3.10, 3.11, 3.12)
- Multiple OS (Linux, macOS, Windows)

See `.github/workflows/ci.yml` for details.

## Test Best Practices

### 1. Test Names

Use descriptive names:
```python
# Good
def test_agent_executes_tool_with_valid_input():
    ...

# Bad
def test_1():
    ...
```

### 2. Arrange-Act-Assert

Structure tests clearly:
```python
def test_tool_execution():
    # Arrange
    tool = Tool(func=my_func)
    
    # Act
    result = tool.execute(x=5)
    
    # Assert
    assert result == 10
```

### 3. One Assertion Per Test

```python
# Good
def test_message_role():
    msg = Message(role="user", content="Hi")
    assert msg.role == "user"

def test_message_content():
    msg = Message(role="user", content="Hi")
    assert msg.content == "Hi"

# Acceptable for related checks
def test_message_creation():
    msg = Message(role="user", content="Hi")
    assert msg.role == "user"
    assert msg.content == "Hi"
```

### 4. Use Fixtures for Setup

```python
@pytest.fixture
def sample_agent():
    """Create a sample agent."""
    return Agent(llm=Mock(), name="TestAgent")

def test_agent_name(sample_agent):
    assert sample_agent.name == "TestAgent"
```

### 5. Test Edge Cases

```python
def test_tool_with_invalid_args():
    """Test tool with invalid arguments."""
    tool = Tool(func=my_func)
    with pytest.raises(RuntimeError):
        tool.execute(invalid=123)
```

## Debugging Tests

### Run with Verbose Output

```bash
pytest -vv
```

### Show Print Statements

```bash
pytest -s
```

### Drop to Debugger on Failure

```bash
pytest --pdb
```

### Run Last Failed Tests

```bash
pytest --lf
```

### Run Only Failed Tests

```bash
pytest --failed-first
```

## Adding New Tests

### 1. Create Test File

```bash
touch packages/my-package/tests/test_my_module.py
```

### 2. Write Tests

```python
"""Tests for my module."""

def test_my_function():
    """Test my function."""
    from my_package import my_function
    
    result = my_function(42)
    assert result == expected
```

### 3. Run Tests

```bash
pytest packages/my-package/tests/test_my_module.py
```

## Test Dependencies

All test dependencies are in `[dev]` extras:

```bash
pip install -e ".[dev]"
```

Includes:
- pytest
- pytest-cov
- pytest-asyncio
- httpx (for testing web UI)

## Coverage Goals

Target coverage by package:
- Core packages (pig-llm, pig-agent-core): >80%
- UI packages (pig-tui, pig-web-ui): >70%
- Integration tests: Cover main workflows

## Troubleshooting

### Import Errors

```bash
# Make sure packages are installed
./scripts/install-dev.sh
```

### Coverage Not Working

```bash
# Reinstall with dev dependencies
pip install -e ".[dev]"
```

### Tests Pass Locally But Fail in CI

- Check Python version compatibility
- Check OS-specific behavior
- Review CI logs

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)

---

Happy testing! 🧪
