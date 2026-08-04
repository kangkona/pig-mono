"""Regression tests for JSON-RPC request validation."""

import json
import sys
from io import StringIO
from typing import Any

import pytest
from pig_agent_core.output_modes import RPCMode


@pytest.mark.parametrize(
    ("invalid_request", "expected_error", "expected_id"),
    [
        (["not", "an", "object"], "expected an object", None),
        ({"id": "1", "method": "ping"}, "id must be an integer", None),
        ({"id": 2, "method": 3}, "method must be a string", 2),
        ({"id": 3, "method": "ping", "params": []}, "params must be an object", 3),
    ],
)
def test_rpc_server_rejects_invalid_request_shapes_and_continues(
    invalid_request: object,
    expected_error: str,
    expected_id: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed requests produce protocol errors without terminating the server."""
    valid_request = {"id": 9, "method": "ping", "params": {"value": "ok"}}
    input_stream = StringIO(f"{json.dumps(invalid_request)}\n{json.dumps(valid_request)}\n")
    output_stream = StringIO()
    monkeypatch.setattr(sys, "stdin", input_stream)
    monkeypatch.setattr(sys, "stdout", output_stream)

    handled: list[tuple[str, dict[str, Any]]] = []

    def handler(method: str, params: dict[str, Any]) -> dict[str, Any]:
        handled.append((method, params))
        return {"handled": True}

    RPCMode().run_server(handler)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["id"] == expected_id
    assert expected_error in responses[0]["error"]
    assert responses[1] == {"id": 9, "result": {"handled": True}, "error": None}
    assert handled == [("ping", {"value": "ok"})]
