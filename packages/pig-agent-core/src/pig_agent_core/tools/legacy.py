"""Tool system for agents."""

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints, overload

from pydantic import BaseModel, create_model

ToolCallable = Callable[..., Any]


class Tool:
    """Represents a tool that an agent can use."""

    def __init__(
        self,
        func: ToolCallable,
        name: str | None = None,
        description: str | None = None,
        params_model: type[BaseModel] | None = None,
        strict_json: str | None = None,
        grammar: dict[str, str] | None = None,
        deferred: bool = False,
    ) -> None:
        """Initialize tool.

        Args:
            func: The function to execute
            name: Tool name (defaults to function name)
            description: Tool description for LLM
            params_model: Optional Pydantic model for parameters
            strict_json: Optional ``prefer`` or ``require`` strict-schema policy
            grammar: Optional ``{"type": "regex"|"lark", "value": ...}`` constraint
            deferred: Whether this definition may be loaded lazily by supporting models
        """
        self.func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self.params_model = params_model or self._create_params_model(func)
        if strict_json not in {None, "prefer", "require"}:
            raise ValueError("strict_json must be 'prefer', 'require', or None")
        self.strict_json = strict_json
        self.grammar = dict(grammar) if grammar is not None else None
        self.deferred = deferred

    def __set_name__(self, owner: type[Any], name: str) -> None:
        """Called when the Tool is assigned as a class attribute."""
        self._attr_name = name

    @overload
    def __get__(self, obj: None, objtype: type[Any] | None = None) -> "Tool": ...

    @overload
    def __get__(self, obj: Any, objtype: type[Any] | None = None) -> "Tool": ...

    def __get__(self, obj: Any | None, objtype: type[Any] | None = None) -> "Tool":
        """Descriptor protocol: bind self to the instance when accessed on an object."""
        if obj is None:
            return self
        # Return a bound copy of this Tool
        import functools

        bound = Tool(
            func=functools.partial(self.func, obj),
            name=self.name,
            description=self.description,
            params_model=self.params_model,
            strict_json=self.strict_json,
            grammar=self.grammar,
            deferred=self.deferred,
        )
        return bound

    def _create_params_model(self, func: ToolCallable) -> type[BaseModel]:
        """Create Pydantic model from function signature."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        fields: dict[str, Any] = {}
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = type_hints.get(param_name, Any)
            default = param.default if param.default != inspect.Parameter.empty else ...

            fields[param_name] = (param_type, default)

        return create_model(f"{self.name.title()}Params", **fields)

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI function calling schema."""
        function: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.params_model.model_json_schema(),
        }
        if self.strict_json is not None:
            function["strict_json"] = self.strict_json
        if self.grammar is not None:
            function["grammar"] = dict(self.grammar)
        if self.deferred:
            function["defer_loading"] = True
        return {
            "type": "function",
            "function": function,
        }

    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given arguments."""
        try:
            # Validate parameters
            validated = self.params_model(**kwargs)
            # Execute function
            return self.func(**validated.model_dump())
        except Exception as e:
            raise RuntimeError(f"Tool {self.name} failed: {e}") from e

    async def aexecute(self, **kwargs: Any) -> Any:
        """Async execute the tool."""
        if inspect.iscoroutinefunction(self.func):
            validated = self.params_model(**kwargs)
            return await self.func(**validated.model_dump())
        else:
            return self.execute(**kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Make tool callable."""
        return self.func(*args, **kwargs)


@overload
def tool(
    func: ToolCallable,
    *,
    name: str | None = None,
    description: str | None = None,
    params_model: type[BaseModel] | None = None,
    strict_json: str | None = None,
    grammar: dict[str, str] | None = None,
    deferred: bool = False,
) -> Tool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    params_model: type[BaseModel] | None = None,
    strict_json: str | None = None,
    grammar: dict[str, str] | None = None,
    deferred: bool = False,
) -> Callable[[ToolCallable], Tool]: ...


def tool(
    func: ToolCallable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    params_model: type[BaseModel] | None = None,
    strict_json: str | None = None,
    grammar: dict[str, str] | None = None,
    deferred: bool = False,
) -> Tool | Callable[[ToolCallable], Tool]:
    """Decorator to create a tool from a function.

    Usage:
        @tool
        def my_tool(arg: str) -> str:
            return f"Result: {arg}"

        @tool(name="custom", description="Custom tool")
        def another_tool(x: int, y: int = 10) -> int:
            return x + y
    """

    def decorator(f: ToolCallable) -> Tool:
        return Tool(
            func=f,
            name=name,
            description=description,
            params_model=params_model,
            strict_json=strict_json,
            grammar=grammar,
            deferred=deferred,
        )

    if func is None:
        # Called with arguments: @tool(name="...")
        return decorator
    else:
        # Called without arguments: @tool
        return decorator(func)
