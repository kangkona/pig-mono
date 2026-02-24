"""Tool system for agents."""

import inspect
import json
from typing import Any, Callable, Optional, Type, get_type_hints
from pydantic import BaseModel, create_model


class Tool:
    """Represents a tool that an agent can use."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        params_model: Optional[Type[BaseModel]] = None,
    ):
        """Initialize tool.

        Args:
            func: The function to execute
            name: Tool name (defaults to function name)
            description: Tool description for LLM
            params_model: Optional Pydantic model for parameters
        """
        self.func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self.params_model = params_model or self._create_params_model(func)

    def __set_name__(self, owner, name):
        """Called when the Tool is assigned as a class attribute."""
        self._attr_name = name

    def __get__(self, obj, objtype=None):
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
        )
        return bound

    def _create_params_model(self, func: Callable) -> Type[BaseModel]:
        """Create Pydantic model from function signature."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        fields = {}
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
                
            param_type = type_hints.get(param_name, Any)
            default = param.default if param.default != inspect.Parameter.empty else ...
            
            fields[param_name] = (param_type, default)
        
        return create_model(
            f"{self.name.title()}Params",
            **fields
        )

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.params_model.model_json_schema(),
            }
        }

    def execute(self, **kwargs) -> Any:
        """Execute the tool with given arguments."""
        try:
            # Validate parameters
            validated = self.params_model(**kwargs)
            # Execute function
            return self.func(**validated.model_dump())
        except Exception as e:
            raise RuntimeError(f"Tool {self.name} failed: {e}") from e

    async def aexecute(self, **kwargs) -> Any:
        """Async execute the tool."""
        if inspect.iscoroutinefunction(self.func):
            validated = self.params_model(**kwargs)
            return await self.func(**validated.model_dump())
        else:
            return self.execute(**kwargs)

    def __call__(self, *args, **kwargs) -> Any:
        """Make tool callable."""
        return self.func(*args, **kwargs)


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    params_model: Optional[Type[BaseModel]] = None,
) -> Callable:
    """Decorator to create a tool from a function.

    Usage:
        @tool
        def my_tool(arg: str) -> str:
            return f"Result: {arg}"

        @tool(name="custom", description="Custom tool")
        def another_tool(x: int, y: int = 10) -> int:
            return x + y
    """
    def decorator(f: Callable) -> Tool:
        return Tool(
            func=f,
            name=name,
            description=description,
            params_model=params_model,
        )

    if func is None:
        # Called with arguments: @tool(name="...")
        return decorator
    else:
        # Called without arguments: @tool
        return decorator(func)
