"""Tests for CLI commands."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


@pytest.fixture
def mock_env():
    """Mock environment with API key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        yield


@pytest.fixture
def mock_llm():
    """Mock LLM instance."""
    llm = Mock()
    llm.config = Mock(model="test-model")
    return llm


@pytest.fixture
def mock_ctx():
    """Mock typer context."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    return ctx


def test_cli_imports():
    """Test CLI module imports."""
    from py_coding_agent.cli import app, main, gen, analyze
    assert app is not None
    assert callable(main)
    assert callable(gen)
    assert callable(analyze)


@patch('py_coding_agent.cli.LLM')
@patch('py_coding_agent.cli.CodingAgent')
def test_gen_command(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test gen command."""
    from py_coding_agent.cli import gen
    
    # Setup mocks
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    mock_llm_class.return_value = mock_llm
    
    mock_agent = Mock()
    mock_agent.run_once = Mock(return_value="# Generated code\nprint('hello')")
    mock_agent_class.return_value = mock_agent
    
    # Test without output file
    with patch('py_coding_agent.cli.console') as mock_console:
        gen(description="Create a hello world script", output=None, model=None)
        
        mock_llm_class.assert_called_once()
        mock_agent_class.assert_called_once()
        mock_agent.run_once.assert_called_once()
        mock_console.print.assert_called()


@patch('py_coding_agent.cli.LLM')
@patch('py_coding_agent.cli.CodingAgent')
def test_gen_command_with_output(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test gen command with output file."""
    from py_coding_agent.cli import gen
    
    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_agent = Mock()
    mock_agent.run_once = Mock(return_value="print('hello')")
    mock_agent_class.return_value = mock_agent
    
    # Test with output file
    output_file = tmp_path / "output.py"
    
    with patch('py_coding_agent.cli.console') as mock_console:
        gen(description="Create script", output=output_file, model=None)
        
        assert output_file.exists()
        assert output_file.read_text() == "print('hello')"
        mock_console.print.assert_called()


@patch('py_coding_agent.cli.LLM')
@patch('py_coding_agent.cli.CodingAgent')
def test_analyze_command(mock_agent_class, mock_llm_class, mock_env, tmp_path):
    """Test analyze command."""
    from py_coding_agent.cli import analyze
    
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    
    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_agent = Mock()
    mock_agent.run_once = Mock(return_value="Analysis: Simple print statement")
    mock_agent_class.return_value = mock_agent
    
    with patch('py_coding_agent.cli.console') as mock_console:
        analyze(path=test_file, model=None)
        
        mock_agent.run_once.assert_called_once()
        mock_console.print.assert_called()


def test_analyze_command_missing_file(mock_env):
    """Test analyze command with missing file."""
    from py_coding_agent.cli import analyze

    with pytest.raises((SystemExit, Exception)):
        with patch('py_coding_agent.cli.console'):
            analyze(path=Path("nonexistent.py"), model=None)


def test_main_without_api_key(mock_ctx):
    """Test main command without API key."""
    from py_coding_agent.cli import main

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises((SystemExit, Exception)):
            with patch('py_coding_agent.cli.console'):
                main(ctx=mock_ctx)


@patch('py_coding_agent.cli.LLM')
@patch('py_coding_agent.cli.CodingAgent')
def test_main_with_custom_model(mock_agent_class, mock_llm_class, mock_env, mock_ctx):
    """Test main with custom model."""
    from py_coding_agent.cli import main

    # Setup mocks
    mock_llm = Mock()
    mock_llm.config = Mock(model="gpt-4")
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_interactive = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with patch('py_coding_agent.cli.console') as mock_console:
        main(ctx=mock_ctx, model="gpt-4", provider="openai", workspace=Path("."), verbose=True)

        # Verify LLM created with correct model
        assert mock_llm_class.call_args.kwargs.get('model') == "gpt-4"


@patch('py_coding_agent.cli.LLM')
@patch('py_coding_agent.cli.CodingAgent')
def test_main_with_workspace(mock_agent_class, mock_llm_class, mock_env, mock_ctx, tmp_path):
    """Test main with custom workspace."""
    from py_coding_agent.cli import main

    # Setup mocks
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm

    mock_agent = Mock()
    mock_agent.run_interactive = Mock()
    mock_agent.session = None
    mock_agent.skill_manager = None
    mock_agent.extension_manager = None
    mock_agent_class.return_value = mock_agent

    with patch('py_coding_agent.cli.console'):
        main(ctx=mock_ctx, workspace=tmp_path, provider="openai")

        # Verify agent created with correct workspace
        assert mock_agent_class.call_args.kwargs.get('workspace') == str(tmp_path)
