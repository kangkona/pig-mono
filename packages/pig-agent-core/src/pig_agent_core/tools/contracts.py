"""Provider-neutral contracts for constrained and deferred tool definitions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pig_agent_core.models import ToolModelCapabilities

StrictJsonMode = Literal["prefer", "require"]
GrammarType = Literal["regex", "lark"]


class ToolCapabilityError(ValueError):
    """Raised when a required tool constraint cannot be honored by a model."""


def prepare_tool_schema(
    schema: dict[str, Any],
    capabilities: ToolModelCapabilities,
    *,
    deferred: bool = False,
) -> dict[str, Any]:
    """Return a provider-ready copy of one tool schema.

    ``strict_json`` is pig's portable policy marker.  It becomes the standard
    OpenAI-compatible ``strict`` flag when supported.  ``prefer`` may degrade
    safely; ``require`` and grammar constraints fail closed.

    ``defer_loading`` is emitted only for models whose adapters advertise the
    capability.  Unsupported models receive ordinary complete definitions.
    """
    rendered = deepcopy(schema)
    function = rendered.get("function")
    if not isinstance(function, dict):
        raise ValueError("Tool schema must contain a function object")

    name = str(function.get("name") or "<unnamed>")
    strict_mode = function.pop("strict_json", None)
    if strict_mode is not None and strict_mode not in {"prefer", "require"}:
        raise ValueError(f"Tool '{name}' has invalid strict_json mode: {strict_mode!r}")
    if strict_mode and capabilities.supports_strict_tools:
        function["strict"] = True
    elif strict_mode == "require":
        raise ToolCapabilityError(
            f"Tool '{name}' requires strict JSON, but the selected model does not support it"
        )

    grammar = function.get("grammar")
    if grammar is not None:
        if not isinstance(grammar, dict):
            raise ValueError(f"Tool '{name}' grammar must be an object")
        grammar_type = grammar.get("type")
        value = grammar.get("value")
        if grammar_type not in {"regex", "lark"} or not isinstance(value, str) or not value:
            raise ValueError(
                f"Tool '{name}' grammar requires type 'regex' or 'lark' and a non-empty value"
            )
        if grammar_type not in capabilities.supported_grammar_tools:
            raise ToolCapabilityError(
                f"Tool '{name}' requires {grammar_type} grammar, "
                "but the selected model does not support it"
            )

    if deferred and capabilities.supports_deferred_tools:
        function["defer_loading"] = True
    else:
        function.pop("defer_loading", None)

    return rendered
