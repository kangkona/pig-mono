"""Enhanced tool registry with lazy loading and execution management."""

import asyncio
import inspect
import json
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pig_agent_core.models import ToolModelCapabilities

from .audit import ToolAuditLog
from .base import CancelledError, ToolResult
from .contracts import prepare_tool_schema
from .metrics import ToolMetricsCollector
from .schemas import PARALLEL_SAFE_TOOLS, TOOL_PERMISSIONS


class RegistrationError(Exception):
    """Raised when tool registration validation fails."""

    pass


class ToolRegistry:
    """Registry for managing agent tools with lazy loading and execution control.

    Features:
    - Core tools always loaded
    - Dynamic tool discovery and activation
    - Timeout and retry support
    - Thread-safe operations
    - Tool fallback mapping
    - Write-tool confirmation gate
    - Parallel/sequential execution strategies
    - Schema/handler/budget consistency validation
    """

    def __init__(
        self,
        audit_log: ToolAuditLog | None = None,
        metrics: ToolMetricsCollector | None = None,
    ) -> None:
        """Initialize tool registry.

        Args:
            audit_log: Optional audit log. When provided, each ``execute()``
                call records an entry (tool name, user, success/failure,
                duration). Defaults to None (no auditing).
            metrics: Optional metrics collector. When provided, each
                ``execute()`` call records call count, success rate, and
                duration statistics. Defaults to None (no metrics).
        """
        self._handlers: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._core_tools: set[str] = set()
        self._discovered: set[str] = set()
        self._lock = threading.RLock()
        self._timeouts: dict[str, float] = {}  # tool_name -> timeout_seconds
        self._retries: dict[str, int] = {}  # tool_name -> max_retries
        self._fallbacks: dict[str, list[str]] = {}  # tool_name -> [fallback_tool_names]
        self._confirmed_tools: set[str] = set()  # Write tools that have been confirmed
        self._audit_log: ToolAuditLog | None = audit_log
        self._metrics: ToolMetricsCollector | None = metrics

    def register(
        self,
        name: str,
        handler: Callable,
        schema: dict[str, Any],
        *,
        is_core: bool = False,
        timeout: float = 30.0,
        max_retries: int = 0,
        fallback_tools: list[str] | None = None,
        validate: bool = True,
    ) -> None:
        """Register a tool with its handler and schema.

        Args:
            name: Tool name
            handler: Callable that executes the tool
            schema: OpenAI function calling schema
            is_core: Whether this is a core tool (always loaded)
            timeout: Execution timeout in seconds
            max_retries: Maximum number of retry attempts on failure
            fallback_tools: List of fallback tool names to try if this tool fails
            validate: Whether to validate schema/handler/budget consistency

        Raises:
            RegistrationError: If validation fails
        """
        # Validate consistency if requested
        if validate:
            self._validate_registration(name, handler, schema, timeout, max_retries)

        with self._lock:
            self._handlers[name] = handler
            self._schemas[name] = schema
            self._timeouts[name] = timeout
            self._retries[name] = max_retries

            if fallback_tools:
                self._fallbacks[name] = fallback_tools

            if is_core:
                self._core_tools.add(name)

    def _validate_registration(
        self,
        name: str,
        handler: Callable,
        schema: dict[str, Any],
        timeout: float,
        max_retries: int,
    ) -> None:
        """Validate tool registration consistency.

        Args:
            name: Tool name
            handler: Tool handler
            schema: Tool schema
            timeout: Timeout value
            max_retries: Max retries value

        Raises:
            RegistrationError: If validation fails
        """
        # Validate handler is callable
        if not callable(handler):
            raise RegistrationError(f"Handler for '{name}' must be callable")

        # Validate schema structure
        if not isinstance(schema, dict):
            raise RegistrationError(f"Schema for '{name}' must be a dict")

        if "function" not in schema:
            raise RegistrationError(f"Schema for '{name}' missing 'function' key")

        func_schema = schema["function"]
        if "name" not in func_schema:
            raise RegistrationError(f"Schema for '{name}' missing 'function.name'")

        if func_schema["name"] != name:
            raise RegistrationError(
                f"Schema name '{func_schema['name']}' does not match tool name '{name}'"
            )

        # Validate timeout and retries
        if timeout <= 0:
            raise RegistrationError(f"Timeout for '{name}' must be positive")

        if max_retries < 0:
            raise RegistrationError(f"Max retries for '{name}' must be non-negative")

    def unregister(self, name: str) -> None:
        """Unregister a tool by name.

        Args:
            name: Tool name to unregister
        """
        with self._lock:
            self._handlers.pop(name, None)
            self._schemas.pop(name, None)
            self._core_tools.discard(name)
            self._discovered.discard(name)
            self._timeouts.pop(name, None)
            self._retries.pop(name, None)
            self._fallbacks.pop(name, None)
            self._confirmed_tools.discard(name)

    def register_package(
        self,
        schemas: list[dict[str, Any]],
        handlers: dict[str, Callable],
        *,
        is_core: bool = True,
        timeout: float = 30.0,
        max_retries: int = 0,
    ) -> list[str]:
        """Register multiple tools from a package at once.

        Convenience method for registering all tools from TOOL_SCHEMAS and HANDLERS.

        Args:
            schemas: List of OpenAI function calling schemas
            handlers: Dict mapping tool names to handler functions
            is_core: Whether these are core tools (always loaded)
            timeout: Default execution timeout in seconds
            max_retries: Default maximum number of retry attempts

        Returns:
            List of registered tool names

        Example:
            from pig_agent_core.tools import TOOL_SCHEMAS, HANDLERS
            registry = ToolRegistry()
            registered = registry.register_package(TOOL_SCHEMAS, HANDLERS)
        """
        registered = []
        for schema in schemas:
            tool_name = schema.get("function", {}).get("name")
            if not tool_name:
                continue

            handler = handlers.get(tool_name)
            if not handler:
                continue

            self.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=is_core,
                timeout=timeout,
                max_retries=max_retries,
            )
            registered.append(tool_name)

        return registered

    def get_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI schemas for active tools (core + discovered).

        Returns:
            List of tool schemas for LLM function calling
        """
        with self._lock:
            # Always include core tools
            active_names = self._core_tools | self._discovered
            return [self._schemas[name] for name in sorted(active_names) if name in self._schemas]

    def get_provider_schemas(
        self,
        capabilities: ToolModelCapabilities,
        *,
        available_tool_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Build a stable, capability-gated tool definition list for a provider.

        When deferred loading is supported, registered definitions that are not
        yet available at the selected transcript point are marked for deferred
        loading. Otherwise only transcript-available definitions are sent.

        ``available_tool_names`` should come from
        :meth:`Session.available_tool_names_at` during replay/branching.  When
        omitted, the registry's legacy global active set is used.
        """
        with self._lock:
            available = (
                set(available_tool_names)
                if available_tool_names is not None
                else self._core_tools | self._discovered
            )
            names = (
                set(self._schemas)
                if capabilities.supports_deferred_tools
                else available & set(self._schemas)
            )
            return [
                prepare_tool_schema(
                    self._schemas[name],
                    capabilities,
                    deferred=name not in available,
                )
                for name in sorted(names)
            ]

    def activate_tools(self, names: list[str]) -> list[str]:
        """Activate deferred tools by name (lazy loading).

        Args:
            names: List of tool names to activate

        Returns:
            List of newly activated tool names
        """
        with self._lock:
            new = [
                n
                for n in names
                if n not in self._core_tools and n not in self._discovered and n in self._schemas
            ]
            self._discovered.update(new)
            return new

    def confirm_tool(self, name: str) -> None:
        """Confirm a write tool for execution (bypasses confirmation gate).

        Args:
            name: Tool name to confirm
        """
        with self._lock:
            self._confirmed_tools.add(name)

    def is_tool_confirmed(self, name: str) -> bool:
        """Check if a write tool has been confirmed.

        Args:
            name: Tool name to check

        Returns:
            True if tool is confirmed or not a write tool
        """
        # Non-write tools don't need confirmation
        permission = TOOL_PERMISSIONS.get(name, "none")
        if permission != "write":
            return True

        with self._lock:
            return name in self._confirmed_tools

    def requires_confirmation(self, name: str) -> bool:
        """Check if a tool requires confirmation before execution.

        Args:
            name: Tool name to check

        Returns:
            True if tool is a write tool and not yet confirmed
        """
        permission = TOOL_PERMISSIONS.get(name, "none")
        if permission != "write":
            return False

        with self._lock:
            return name not in self._confirmed_tools

    def get_fallback_tools(self, name: str) -> list[str]:
        """Get fallback tools for a given tool.

        Args:
            name: Tool name

        Returns:
            List of fallback tool names (empty if none configured)
        """
        with self._lock:
            return self._fallbacks.get(name, []).copy()

    def set_fallback_tools(self, name: str, fallback_tools: list[str]) -> None:
        """Set fallback tools for a given tool.

        Args:
            name: Tool name
            fallback_tools: List of fallback tool names
        """
        with self._lock:
            if fallback_tools:
                self._fallbacks[name] = fallback_tools
            else:
                self._fallbacks.pop(name, None)

    async def execute(
        self,
        tool_call: Any,
        user_id: str,
        meta: dict[str, Any],
        cancel: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        """Execute a tool with timeout, retry, and fallback support.

        Args:
            tool_call: Tool call object with function.name and function.arguments
            user_id: User ID for context
            meta: Additional metadata
            cancel: Optional cancellation event
            on_update: Optional callback for streaming incremental tool output.
                Injected into ``meta["on_update"]`` so context-aware handlers
                (4-arg signature) can retrieve it and forward to their I/O layer.

        Returns:
            ToolResult with execution outcome
        """
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            args = {}

        # Inject on_update into meta so context-aware handlers can stream output.
        if on_update is not None:
            meta = {**meta, "on_update": on_update}

        # Check cancellation before execution
        if cancel and cancel.is_set():
            return ToolResult(ok=False, error="Cancelled before execution")

        # Check confirmation gate for write tools
        if self.requires_confirmation(name):
            return ToolResult(
                ok=False,
                error=f"Tool '{name}' requires confirmation before execution (write permission)",
                meta={"requires_confirmation": True, "tool_name": name},
            )

        # Try primary tool
        _t0 = time.monotonic()
        result = await self._execute_tool(name, args, user_id, meta, cancel)
        _duration = time.monotonic() - _t0

        # If primary tool failed, try fallbacks
        if not result.ok:
            fallbacks = self.get_fallback_tools(name)
            for fallback_name in fallbacks:
                if cancel and cancel.is_set():
                    return ToolResult(ok=False, error="Cancelled during fallback execution")

                # Try fallback tool
                fallback_result = await self._execute_tool(
                    fallback_name, args, user_id, meta, cancel
                )
                if fallback_result.ok:
                    # Add metadata about fallback usage
                    fallback_result.meta["fallback_from"] = name
                    fallback_result.meta["fallback_to"] = fallback_name
                    result = fallback_result
                    break

        # Record audit and metrics for the final outcome.
        if self._audit_log is not None:
            self._audit_log.log(
                tool_name=name,
                user_id=user_id,
                args=args,
                success=result.ok,
                error=result.error,
                duration=_duration,
            )
        if self._metrics is not None:
            self._metrics.record(
                tool_name=name,
                user_id=user_id,
                success=result.ok,
                duration=_duration,
            )

        return result

    def execute_sync(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        user_id: str = "default",
        meta: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Execute a tool synchronously for the legacy Agent.run() path."""
        args = args or {}
        meta = meta or {}

        if self.requires_confirmation(name):
            return ToolResult(
                ok=False,
                error=f"Tool '{name}' requires confirmation before execution (write permission)",
                meta={"requires_confirmation": True, "tool_name": name},
            )

        handler = self._handlers.get(name)
        if not handler:
            return ToolResult(ok=False, error=f"Tool '{name}' not found")

        activated_on_call = self._activate_deferred_tool(name)

        try:
            signature = inspect.signature(handler)
            params = list(signature.parameters)
            uses_ctx = params[:4] == ["args", "user_id", "meta", "cancel"]
            if asyncio.iscoroutinefunction(handler):
                # Async tool invoked from the synchronous run() path: drive the
                # coroutine to completion on a private loop.
                coro = handler(args, user_id, meta, None) if uses_ctx else handler(**args)
                value = asyncio.run(coro)
            elif uses_ctx:
                value = handler(args, user_id, meta, None)
            else:
                value = handler(**args)
            if isinstance(value, ToolResult):
                return self._with_activation_anchor(name, value, activated_on_call)
            return self._with_activation_anchor(
                name,
                ToolResult(ok=True, data=value),
                activated_on_call,
            )
        except Exception as exc:
            return self._with_activation_anchor(
                name,
                ToolResult(ok=False, error=str(exc)),
                activated_on_call,
            )

    def _activate_deferred_tool(self, name: str) -> bool:
        """Activate a registered non-core tool called directly by a provider."""
        with self._lock:
            if name in self._core_tools or name in self._discovered or name not in self._schemas:
                return False
            self._discovered.add(name)
            return True

    @staticmethod
    def _with_activation_anchor(
        name: str,
        result: ToolResult,
        activated_on_call: bool,
    ) -> ToolResult:
        """Attach a durable activation fact to the direct call's result."""
        if activated_on_call and name not in result.added_tool_names:
            result.added_tool_names.append(name)
        return result

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        user_id: str,
        meta: dict[str, Any],
        cancel: asyncio.Event | None,
    ) -> ToolResult:
        """Execute a single tool with timeout and retry.

        Args:
            name: Tool name
            args: Tool arguments
            user_id: User ID
            meta: Metadata
            cancel: Cancellation event

        Returns:
            ToolResult from execution
        """
        # A provider may call a deferred definition directly after native tool
        # search. Preserve that transition on the transcript, not only in this
        # registry instance.
        activated_on_call = self._activate_deferred_tool(name)

        def with_activation(result: ToolResult) -> ToolResult:
            return self._with_activation_anchor(name, result, activated_on_call)

        # Get handler
        handler = self._handlers.get(name)
        if not handler:
            return ToolResult(ok=False, error=f"Tool '{name}' not found")

        # Get timeout and retry config
        timeout = self._timeouts.get(name, 30.0)
        max_retries = self._retries.get(name, 0)

        # Execute with retry logic
        last_error = None
        for attempt in range(max_retries + 1):
            if cancel and cancel.is_set():
                return with_activation(ToolResult(ok=False, error="Cancelled during execution"))

            try:
                # Execute with timeout, racing against cancellation so an
                # in-flight tool (e.g. a running shell command) is killed the
                # moment the turn is aborted — not just between tools.
                result = await self._run_with_cancel(
                    self._execute_handler(handler, args, user_id, meta, cancel),
                    timeout,
                    cancel,
                )
                if isinstance(result, ToolResult):
                    return with_activation(result)
                return with_activation(ToolResult(ok=True, data=result))
            except asyncio.TimeoutError:
                last_error = f"Tool execution timed out after {timeout}s"
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
            except CancelledError:
                return with_activation(ToolResult(ok=False, error="Cancelled by user"))
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

        return with_activation(ToolResult(ok=False, error=last_error or "Unknown error"))

    async def _run_with_cancel(
        self,
        coro: Awaitable[Any],
        timeout: float,
        cancel: asyncio.Event | None,
    ) -> Any:
        """Await ``coro`` (with timeout); if ``cancel`` fires first, cancel the task.

        Strict no-op wrapper when ``cancel`` is None — preserves the exact
        ``asyncio.wait_for`` behavior for json/rpc/sync paths. When a cancel
        event is provided and is set while the handler runs, the handler task is
        cancelled (propagating ``CancelledError`` into the handler so it can kill
        any subprocess) and ``CancelledError`` is raised to the caller.
        """
        if cancel is None:
            return await asyncio.wait_for(coro, timeout=timeout)

        handler_task = asyncio.ensure_future(asyncio.wait_for(coro, timeout=timeout))
        cancel_task = asyncio.ensure_future(cancel.wait())
        done, _ = await asyncio.wait(
            {handler_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if handler_task in done:
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass
            return handler_task.result()  # re-raises TimeoutError/handler errors

        # Cancellation won the race: stop the in-flight handler. Awaiting the
        # cancelled task raises asyncio.CancelledError (a BaseException), so catch
        # it explicitly; then surface the registry's own CancelledError so
        # _execute_tool returns a clean "Cancelled by user" result.
        handler_task.cancel()
        try:
            await handler_task
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
        raise CancelledError()

    async def _execute_handler(
        self,
        handler: Callable,
        args: dict[str, Any],
        user_id: str,
        meta: dict[str, Any],
        cancel: asyncio.Event | None,
    ) -> ToolResult:
        """Execute a tool handler with proper async handling.

        Args:
            handler: Tool handler function
            args: Tool arguments
            user_id: User ID
            meta: Metadata
            cancel: Cancellation event

        Returns:
            ToolResult from handler execution
        """
        signature = inspect.signature(handler)
        params = list(signature.parameters)

        # Check if handler is async
        if asyncio.iscoroutinefunction(handler):
            if params[:4] == ["args", "user_id", "meta", "cancel"]:
                return await handler(args, user_id, meta, cancel)
            return await handler(**args)
        else:
            # Run sync handler in executor
            loop = asyncio.get_event_loop()
            if params[:4] == ["args", "user_id", "meta", "cancel"]:
                return await loop.run_in_executor(None, handler, args, user_id, meta, cancel)
            return await loop.run_in_executor(None, lambda: handler(**args))

    async def execute_batch(
        self,
        tool_calls: list[Any],
        user_id: str,
        meta: dict[str, Any],
        cancel: asyncio.Event | None = None,
    ) -> list[ToolResult]:
        """Execute multiple tool calls with automatic parallel/sequential strategy.

        Read-only tools (in PARALLEL_SAFE_TOOLS) execute in parallel.
        Write tools execute sequentially to prevent race conditions.

        Args:
            tool_calls: List of tool call objects
            user_id: User ID for context
            meta: Additional metadata
            cancel: Optional cancellation event

        Returns:
            List of ToolResults in same order as tool_calls
        """
        if not tool_calls:
            return []

        # Separate parallel-safe and sequential tools
        parallel_indices = []
        sequential_indices = []

        for i, tool_call in enumerate(tool_calls):
            name = tool_call.function.name
            if name in PARALLEL_SAFE_TOOLS:
                parallel_indices.append(i)
            else:
                sequential_indices.append(i)

        # Initialize results list
        results: list[ToolResult | None] = [None] * len(tool_calls)

        # Execute parallel-safe tools concurrently
        if parallel_indices:
            parallel_tasks = [
                self.execute(tool_calls[i], user_id, meta, cancel) for i in parallel_indices
            ]
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

            for idx, result in zip(parallel_indices, parallel_results, strict=False):
                if isinstance(result, Exception):
                    results[idx] = ToolResult(ok=False, error=str(result))
                else:
                    results[idx] = result

        # Execute sequential tools one by one
        for idx in sequential_indices:
            if cancel and cancel.is_set():
                results[idx] = ToolResult(ok=False, error="Cancelled during batch execution")
            else:
                results[idx] = await self.execute(tool_calls[idx], user_id, meta, cancel)

        # Type assertion: all results should be filled
        return [r for r in results if r is not None]

    def is_parallel_safe(self, name: str) -> bool:
        """Check if a tool is safe for parallel execution.

        Args:
            name: Tool name

        Returns:
            True if tool can be executed in parallel with other tools
        """
        return name in PARALLEL_SAFE_TOOLS

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names in sorted order
        """
        with self._lock:
            return sorted(self._handlers.keys())

    def list_core_tools(self) -> list[str]:
        """List tools that are available before transcript-driven activation."""
        with self._lock:
            return sorted(self._core_tools)

    def list_active_tools(self) -> list[str]:
        """List currently active tool names (core + discovered).

        Returns:
            List of active tool names
        """
        with self._lock:
            return sorted(self._core_tools | self._discovered)

    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._handlers)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._handlers
