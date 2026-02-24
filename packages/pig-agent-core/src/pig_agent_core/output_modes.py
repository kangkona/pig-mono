"""Output modes for different integration scenarios."""

import json
import sys
from typing import Any, Optional
from datetime import datetime


class JSONOutputMode:
    """JSON output mode for structured events."""

    def __init__(self, output_file=None):
        """Initialize JSON output mode.

        Args:
            output_file: Output file (defaults to stdout)
        """
        self.output = output_file or sys.stdout

    def emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a JSON event.

        Args:
            event_type: Event type
            data: Event data
        """
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        }

        json_line = json.dumps(event)
        self.output.write(json_line + "\n")
        self.output.flush()

    def message(self, role: str, content: str, **metadata) -> None:
        """Emit a message event.

        Args:
            role: Message role
            content: Message content
            **metadata: Additional metadata
        """
        self.emit_event(
            "message", {"role": role, "content": content, "metadata": metadata}
        )

    def tool_call_start(self, tool_name: str, arguments: dict) -> None:
        """Emit tool call start event.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
        """
        self.emit_event("tool_call_start", {"tool": tool_name, "args": arguments})

    def tool_call_end(self, tool_name: str, result: Any, error: Optional[str] = None) -> None:
        """Emit tool call end event.

        Args:
            tool_name: Tool name
            result: Tool result
            error: Error message if failed
        """
        self.emit_event(
            "tool_call_end",
            {"tool": tool_name, "result": str(result), "error": error, "success": error is None},
        )

    def token(self, content: str) -> None:
        """Emit a token event (for streaming).

        Args:
            content: Token content
        """
        self.emit_event("token", {"content": content})

    def done(self, final_content: Optional[str] = None) -> None:
        """Emit completion event.

        Args:
            final_content: Final response content
        """
        self.emit_event("done", {"content": final_content} if final_content else {})

    def error(self, error: str, **metadata) -> None:
        """Emit an error event.

        Args:
            error: Error message
            **metadata: Additional error metadata
        """
        self.emit_event("error", {"error": error, "metadata": metadata})


class RPCMode:
    """RPC mode for stdin/stdout process integration."""

    def __init__(self):
        """Initialize RPC mode."""
        self.request_id = 0

    def read_request(self) -> Optional[dict]:
        """Read a request from stdin.

        Returns:
            Request object or None on EOF
        """
        try:
            line = sys.stdin.readline()
            if not line:
                return None

            return json.loads(line)
        except json.JSONDecodeError as e:
            self.send_error(f"Invalid JSON: {e}")
            return None
        except Exception as e:
            self.send_error(f"Error reading request: {e}")
            return None

    def send_response(self, request_id: int, result: Any) -> None:
        """Send a response to stdout.

        Args:
            request_id: Request ID
            result: Response result
        """
        response = {"id": request_id, "result": result, "error": None}

        json_line = json.dumps(response)
        sys.stdout.write(json_line + "\n")
        sys.stdout.flush()

    def send_error(self, error: str, request_id: Optional[int] = None) -> None:
        """Send an error response.

        Args:
            error: Error message
            request_id: Request ID (if applicable)
        """
        response = {"id": request_id, "result": None, "error": error}

        json_line = json.dumps(response)
        sys.stdout.write(json_line + "\n")
        sys.stdout.flush()

    def send_event(self, event_type: str, data: dict) -> None:
        """Send an event notification.

        Args:
            event_type: Event type
            data: Event data
        """
        event = {"event": event_type, "data": data}

        json_line = json.dumps(event)
        sys.stdout.write(json_line + "\n")
        sys.stdout.flush()

    def run_server(self, handler) -> None:
        """Run RPC server loop.

        Args:
            handler: Function to handle requests
                    Should accept (method, params) and return result
        """
        while True:
            request = self.read_request()

            if request is None:
                break

            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            try:
                result = handler(method, params)
                self.send_response(request_id, result)
            except Exception as e:
                self.send_error(str(e), request_id)


class OutputModeManager:
    """Manages different output modes."""

    def __init__(self, mode: str = "interactive"):
        """Initialize output mode manager.

        Args:
            mode: Output mode (interactive, json, rpc)
        """
        self.mode = mode

        if mode == "json":
            self.json_mode = JSONOutputMode()
        elif mode == "rpc":
            self.rpc_mode = RPCMode()
        else:
            self.json_mode = None
            self.rpc_mode = None

    def is_json(self) -> bool:
        """Check if in JSON mode."""
        return self.mode == "json"

    def is_rpc(self) -> bool:
        """Check if in RPC mode."""
        return self.mode == "rpc"

    def is_interactive(self) -> bool:
        """Check if in interactive mode."""
        return self.mode == "interactive"
