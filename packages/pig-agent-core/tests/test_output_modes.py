"""Tests for output modes."""

import pytest
import json
from io import StringIO
from pig_agent_core.output_modes import JSONOutputMode, RPCMode, OutputModeManager


def test_json_output_creation():
    """Test creating JSON output mode."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    assert json_mode.output == output


def test_json_emit_event():
    """Test emitting JSON event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.emit_event("test", {"key": "value"})
    
    result = output.getvalue()
    assert result.strip()
    
    data = json.loads(result)
    assert data["type"] == "test"
    assert data["key"] == "value"
    assert "timestamp" in data


def test_json_message():
    """Test message event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.message("user", "Hello", extra="metadata")
    
    data = json.loads(output.getvalue())
    assert data["type"] == "message"
    assert data["role"] == "user"
    assert data["content"] == "Hello"


def test_json_tool_call_start():
    """Test tool call start event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.tool_call_start("my_tool", {"arg": "value"})
    
    data = json.loads(output.getvalue())
    assert data["type"] == "tool_call_start"
    assert data["tool"] == "my_tool"


def test_json_tool_call_end():
    """Test tool call end event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.tool_call_end("my_tool", "result", error=None)
    
    data = json.loads(output.getvalue())
    assert data["type"] == "tool_call_end"
    assert data["success"] is True


def test_json_token():
    """Test token event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.token("Hello")
    
    data = json.loads(output.getvalue())
    assert data["type"] == "token"
    assert data["content"] == "Hello"


def test_json_done():
    """Test done event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.done("Final content")
    
    data = json.loads(output.getvalue())
    assert data["type"] == "done"
    assert data["content"] == "Final content"


def test_json_error():
    """Test error event."""
    output = StringIO()
    json_mode = JSONOutputMode(output)
    
    json_mode.error("Something failed", code=500)
    
    data = json.loads(output.getvalue())
    assert data["type"] == "error"
    assert data["error"] == "Something failed"


def test_rpc_mode_creation():
    """Test creating RPC mode."""
    rpc = RPCMode()
    assert rpc.request_id == 0


def test_rpc_send_response():
    """Test sending RPC response."""
    import sys
    from io import StringIO
    
    output = StringIO()
    original_stdout = sys.stdout
    sys.stdout = output
    
    try:
        rpc = RPCMode()
        rpc.send_response(1, {"result": "success"})
        
        result = output.getvalue()
        data = json.loads(result)
        
        assert data["id"] == 1
        assert data["result"]["result"] == "success"
        assert data["error"] is None
    finally:
        sys.stdout = original_stdout


def test_rpc_send_error():
    """Test sending RPC error."""
    import sys
    from io import StringIO
    
    output = StringIO()
    original_stdout = sys.stdout
    sys.stdout = output
    
    try:
        rpc = RPCMode()
        rpc.send_error("Error message", request_id=1)
        
        result = output.getvalue()
        data = json.loads(result)
        
        assert data["id"] == 1
        assert data["error"] == "Error message"
        assert data["result"] is None
    finally:
        sys.stdout = original_stdout


def test_output_mode_manager():
    """Test output mode manager."""
    mgr = OutputModeManager("interactive")
    
    assert mgr.is_interactive()
    assert not mgr.is_json()
    assert not mgr.is_rpc()


def test_output_mode_manager_json():
    """Test JSON mode manager."""
    mgr = OutputModeManager("json")
    
    assert not mgr.is_interactive()
    assert mgr.is_json()
    assert not mgr.is_rpc()
    assert mgr.json_mode is not None


def test_output_mode_manager_rpc():
    """Test RPC mode manager."""
    mgr = OutputModeManager("rpc")
    
    assert not mgr.is_interactive()
    assert not mgr.is_json()
    assert mgr.is_rpc()
    assert mgr.rpc_mode is not None
