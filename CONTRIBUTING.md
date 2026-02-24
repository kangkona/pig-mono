# Contributing to pig-mono

Thank you for your interest in contributing to pig-mono!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Install development dependencies: `pip install -e ".[dev]"`
4. Install packages: `./scripts/install-dev.sh`

## Development Workflow

### Making Changes

1. Create a new branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Run tests: `./scripts/test.sh`
4. Run linting: `./scripts/lint.sh`
5. Commit your changes: `git commit -m "Description"`
6. Push to your fork: `git push origin feature/your-feature`
7. Create a Pull Request

### Code Style

- Use `ruff` for linting and formatting
- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Write docstrings for all public functions and classes

### Testing

- Write tests for all new features
- Ensure all tests pass before submitting PR
- Aim for high test coverage

### Running Tests

```bash
# Run all tests
./scripts/test.sh

# Run specific test file
pytest tests/test_pig_llm.py

# Run with coverage
pytest --cov=packages --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format packages/

# Lint code
ruff check packages/

# Type check
mypy packages/
```

## Project Structure

```
pig-mono/
├── packages/          # Monorepo packages
│   ├── pig-llm/        # LLM API wrapper
│   ├── pig-agent-core/ # Agent runtime
│   └── ...
├── scripts/          # Build and utility scripts
├── tests/            # Integration tests
└── pyproject.toml    # Project configuration
```

## Adding a New Package

1. Create package directory: `packages/your-package/`
2. Add `pyproject.toml` with package metadata
3. Create `src/your_package/` for source code
4. Add README.md with usage examples
5. Add tests in `tests/test_your_package.py`

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help create a welcoming community

## Package-Specific Guidelines

### pig-llm (LLM API)
- New providers must implement the Provider interface
- Include both sync and async methods
- Add usage tracking
- Document model names and capabilities

### pig-agent-core (Agent Runtime)
- Maintain backward compatibility
- Extensions must be sandboxed
- Sessions must be serializable
- Events should be documented

### pig-messenger (Multi-Platform)
- New adapters must implement MessagePlatform
- Convert to UniversalMessage format
- Handle platform-specific features gracefully
- Test with actual platform APIs

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Create GitHub release
5. Publish to PyPI (if applicable)

## Questions?

- 💬 Open an issue for questions
- 🐛 Report bugs via GitHub Issues
- 💡 Suggest features via Discussions
- 📧 Contact maintainers for security issues

Feel free to contribute! Every improvement helps. 🙏
