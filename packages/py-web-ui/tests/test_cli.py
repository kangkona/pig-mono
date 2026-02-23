"""Tests for web UI CLI."""

import os
import pytest
from unittest.mock import Mock, patch
from py_web_ui.cli import main


@pytest.fixture
def mock_env():
    """Mock environment with API key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        yield


def test_cli_imports():
    """Test CLI module imports."""
    from py_web_ui.cli import main, console
    assert callable(main)
    assert console is not None


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_defaults(mock_server_class, mock_llm_class, mock_env):
    """Test main with default settings."""
    # Setup mocks
    mock_llm = Mock()
    mock_llm.config = Mock(model="gpt-3.5-turbo")
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server.run = Mock()
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console'):
        main()
        
        # Verify LLM created
        mock_llm_class.assert_called_once()
        call_args = mock_llm_class.call_args
        assert call_args.kwargs['provider'] == 'openai'
        assert call_args.kwargs['api_key'] == 'test-key'
        
        # Verify server created and run
        mock_server_class.assert_called_once()
        mock_server.run.assert_called_once()


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_custom_model(mock_server_class, mock_llm_class, mock_env):
    """Test main with custom model."""
    mock_llm = Mock()
    mock_llm.config = Mock(model="gpt-4")
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console'):
        main(model="gpt-4")
        
        # Verify model was set
        call_args = mock_llm_class.call_args
        assert call_args.kwargs['model'] == 'gpt-4'


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_custom_port(mock_server_class, mock_llm_class, mock_env):
    """Test main with custom port."""
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console'):
        main(port=8080)
        
        # Verify server created with custom port
        call_args = mock_server_class.call_args
        assert call_args.kwargs['port'] == 8080


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_cors(mock_server_class, mock_llm_class, mock_env):
    """Test main with CORS enabled."""
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console'):
        main(cors=True)
        
        # Verify server created with CORS
        call_args = mock_server_class.call_args
        assert call_args.kwargs['cors'] is True


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_custom_title(mock_server_class, mock_llm_class, mock_env):
    """Test main with custom title."""
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console'):
        main(title="Custom Chat")
        
        # Verify server created with title
        call_args = mock_server_class.call_args
        assert call_args.kwargs['title'] == "Custom Chat"


def test_main_without_api_key():
    """Test main without API key."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SystemExit):
            with patch('py_web_ui.cli.console'):
                main()


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_with_different_provider(mock_server_class, mock_llm_class):
    """Test main with different provider."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        mock_llm = Mock()
        mock_llm_class.return_value = mock_llm
        
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('py_web_ui.cli.console'):
            main(provider="anthropic")
            
            # Verify correct provider
            call_args = mock_llm_class.call_args
            assert call_args.kwargs['provider'] == 'anthropic'


@patch('py_web_ui.cli.LLM')
@patch('py_web_ui.cli.ChatServer')
def test_main_keyboard_interrupt(mock_server_class, mock_llm_class, mock_env):
    """Test main handles keyboard interrupt."""
    mock_llm = Mock()
    mock_llm_class.return_value = mock_llm
    
    mock_server = Mock()
    mock_server.run = Mock(side_effect=KeyboardInterrupt)
    mock_server_class.return_value = mock_server
    
    with patch('py_web_ui.cli.console') as mock_console:
        main()
        
        # Should handle gracefully and print message
        mock_console.print.assert_called()


@patch('py_web_ui.cli.LLM')
def test_main_llm_creation_error(mock_llm_class, mock_env):
    """Test main handles LLM creation error."""
    mock_llm_class.side_effect = Exception("API error")
    
    with pytest.raises(SystemExit):
        with patch('py_web_ui.cli.console'):
            main()
