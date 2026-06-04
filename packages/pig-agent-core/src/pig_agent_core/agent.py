"""Main Agent class with tool calling and state management."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from pig_llm import LLM, Message, Response

from .context import SystemPromptBuilder
from .memory import InMemoryProvider, MemoryProvider
from .message_queue import MessageQueue
from .models import AgentState
from .observability.events import AgentEventCallback, BillingHook, emit_agent_end
from .resilience.profile import ProfileManager
from .resilience.retry import resilient_streaming_call
from .tools import Tool, ToolResult
from .tools.registry import ToolRegistry


class Agent:
    """Agent with LLM and tool calling capabilities."""

    def __init__(
        self,
        name: str = "Agent",
        llm: LLM | None = None,
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 10,
        on_tool_start: Callable | None = None,
        on_tool_end: Callable | None = None,
        verbose: bool = False,
        # Enhanced subsystem parameters
        profile_manager: ProfileManager | None = None,
        event_callback: AgentEventCallback | None = None,
        compress_fn: Callable[[list[Message]], list[Message]] | None = None,
        memory_provider: MemoryProvider | None = None,
        system_prompt_builder: SystemPromptBuilder | None = None,
        billing_hook: BillingHook | None = None,
        max_rounds: int | None = None,
        max_rounds_with_plan: int | None = None,
        before_tool_call: Callable[[str, dict[str, Any]], ToolResult | None] | None = None,
        after_tool_call: Callable[[str, dict[str, Any], ToolResult], ToolResult | None]
        | None = None,
    ):
        """Initialize agent.

        Args:
            name: Agent name
            llm: LLM client
            tools: List of tools
            system_prompt: System prompt (or base prompt if system_prompt_builder provided)
            max_iterations: Maximum tool calling iterations (deprecated, use max_rounds)
            on_tool_start: Callback when tool starts
            on_tool_end: Callback when tool ends
            verbose: Enable verbose logging
            profile_manager: Optional profile manager for resilience
            event_callback: Optional callback for observability events
            compress_fn: Optional function to compress messages on context overflow
            memory_provider: Optional memory provider for conversation history
            system_prompt_builder: Optional protocol for building system prompts
            billing_hook: Optional hook for tracking costs
            max_rounds: Maximum conversation rounds (replaces max_iterations)
            max_rounds_with_plan: Maximum rounds after plan tool is used
        """
        self.name = name
        self.llm = llm or LLM()
        self.system_prompt = system_prompt
        # max_rounds takes precedence over the legacy max_iterations. Use an
        # explicit None check so an explicit max_rounds=0 (unbounded, pi-mono
        # style) is honored instead of falling back via `or`.
        self.max_iterations = max_rounds if max_rounds is not None else max_iterations
        self.max_rounds_with_plan = max_rounds_with_plan
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.verbose = verbose

        # Enhanced subsystems
        self.profile_manager = profile_manager
        self.event_callback = event_callback
        self.compress_fn = compress_fn
        self.memory_provider = memory_provider or InMemoryProvider()
        self.system_prompt_builder = system_prompt_builder
        self.billing_hook = billing_hook
        self.before_tool_call = before_tool_call
        self.after_tool_call = after_tool_call

        # Use enhanced ToolRegistry from tools/registry.py
        self.registry = ToolRegistry()
        if tools:
            for tool in tools:
                # Get schema from Tool object
                schema = tool.to_openai_schema()
                self.registry.register(
                    name=tool.name,
                    handler=tool.func,
                    schema=schema,
                    is_core=True,
                )

        self.history: list[Message] = []
        if system_prompt:
            self.history.append(Message(role="system", content=system_prompt))

        self.message_queue = MessageQueue()
        self._plan_used = False  # Track if plan tool has been used
        self._rounds_since_plan = 0  # Track rounds since plan tool

    @staticmethod
    def _as_tool_result(value: Any) -> ToolResult:
        """Normalize arbitrary tool return values into ToolResult."""
        if isinstance(value, ToolResult):
            return value
        return ToolResult(ok=True, data=value)

    def _execute_sync_tool_call(self, tool_call: dict[str, Any]) -> tuple[dict[str, str], bool]:
        """Execute one sync tool call.

        Returns the serialized tool message and whether the current tool batch
        should abort before executing sibling calls.
        """
        tool_name = tool_call.get("function", {}).get("name")
        tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

        self._log(f"→ Calling tool: {tool_name}({self._format_tool_args(tool_args)})", style="cyan")

        if self.before_tool_call:
            preflight = self.before_tool_call(tool_name, tool_args)
            if preflight is not None:
                result = self._as_tool_result(preflight)
                return self._tool_message(tool_call, tool_name, result), bool(
                    result.meta.get("abort_batch")
                )

        if self.on_tool_start:
            self.on_tool_start(tool_name, tool_args)

        try:
            if hasattr(self.registry, "execute_sync"):
                result = self.registry.execute_sync(tool_name, tool_args)
            else:
                raw_result = self.registry.execute(tool_name, **tool_args)
                result = self._as_tool_result(raw_result)
            self._log(f"✓ Result: {result.data if result.ok else result.error}", style="green")

            if self.after_tool_call:
                try:
                    override = self.after_tool_call(tool_name, tool_args, result)
                    if override is not None:
                        result = self._as_tool_result(override)
                except Exception as exc:
                    result = ToolResult(ok=False, error=f"Error: {exc}")

            if self.on_tool_end:
                self.on_tool_end(tool_name, result)
        except Exception as e:
            result = ToolResult(ok=False, error=f"Error: {e}")
            self._log(f"✗ {result.error}", style="red")

        return self._tool_message(tool_call, tool_name, result), False

    @staticmethod
    def _tool_message(
        tool_call: dict[str, Any],
        tool_name: str,
        result: ToolResult,
    ) -> dict[str, Any]:
        """Convert ToolResult into a history-ready tool message."""
        content = result.data if result.ok else result.error
        return {
            "tool_call_id": tool_call.get("id"),
            "role": "tool",
            "name": tool_name,
            "content": str(content),
            "result": result,
        }

    def _log(self, message: str, style: str = "") -> None:
        """Log message if verbose.

        When a UI is attached, render through its Rich console and apply colour
        via the ``style`` argument rather than inline markup, printing the
        message with ``markup=False`` so arbitrary interpolated content (tool
        output, model text) is never parsed as Rich markup — which would either
        swallow ``[...]`` substrings or raise ``MarkupError`` on unbalanced
        tags. Falls back to a plain ``print`` when there is no UI.

        Args:
            message: Message to log (plain text; no Rich markup)
            style: Optional Rich style applied to the whole line
        """
        if not self.verbose:
            return

        ui = getattr(self, "ui", None)
        console = getattr(ui, "console", None) if ui is not None else None
        if console is not None:
            console.print(message, style=style or None, markup=False, highlight=False)
        else:
            print(message)

    @staticmethod
    def _format_tool_args(args: Any, max_len: int = 80) -> str:
        """Compactly format tool-call arguments for logging.

        Long string values (e.g. a whole file passed to write_file) are
        truncated to a short preview plus a char count, so they don't flood
        the terminal.
        """
        if not isinstance(args, dict):
            text = str(args)
            return text if len(text) <= max_len else f"{text[:max_len]}… ({len(text)} chars)"
        parts = []
        for key, value in args.items():
            if isinstance(value, str) and len(value) > max_len:
                preview = value[:max_len].replace("\n", "\\n")
                parts.append(f"{key}='{preview}… ({len(value)} chars)'")
            else:
                parts.append(f"{key}={value!r}")
        return ", ".join(parts)

    def _log_turn(self, message: str) -> None:
        """Echo a conversational turn (User/Agent).

        When a UI is attached it owns turn rendering, so the library-level echo
        is suppressed to avoid printing each message twice.
        """
        if getattr(self, "ui", None) is not None:
            return
        self._log(message)

    def _drain_followup_messages(
        self, messages: list[Any], *, check_queue: bool
    ) -> Response | None:
        """Process queued follow-up messages in delivery order."""
        if not check_queue or not messages:
            return None

        response: Response | None = None
        for message in messages:
            self._log(f"→ Follow-up: {message.content}", style="cyan")
            response = self.run(message.content, check_queue=True)
        return response

    def _emit_agent_end(self, *, success: bool, error: str | None = None) -> None:
        """Emit a terminal agent_end event for the current run."""
        emit_agent_end(
            self.event_callback,
            agent_id=self.name,
            success=success,
            error=error,
        )

    def _can_use_async_batch_execution(self) -> bool:
        """Return True when async tool batches can bypass per-tool hook handling."""
        return not any(
            [
                self.before_tool_call,
                self.after_tool_call,
                self.on_tool_start,
                self.on_tool_end,
                self.billing_hook,
            ]
        )

    async def _execute_async_batch_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        cancel: asyncio.Event | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Execute tool calls via ToolRegistry.execute_batch preserving call order."""
        from types import SimpleNamespace

        tool_call_objects = [
            SimpleNamespace(
                function=SimpleNamespace(
                    name=tool_call.get("function", {}).get("name"),
                    arguments=tool_call.get("function", {}).get("arguments", "{}"),
                )
            )
            for tool_call in tool_calls
        ]
        results = await self.registry.execute_batch(tool_call_objects, "default", {}, cancel)

        tool_messages: list[dict[str, Any]] = []
        terminate_all = True
        for tool_call, result in zip(tool_calls, results, strict=False):
            tool_name = tool_call.get("function", {}).get("name")
            tool_messages.append(self._tool_message(tool_call, tool_name, result))
            terminate_all = terminate_all and bool(result.ok and result.meta.get("terminate"))

        return tool_messages, terminate_all

    def add_tool(self, tool: Tool) -> None:
        """Add a tool to the agent.

        Args:
            tool: Tool to add
        """
        schema = tool.to_openai_schema()
        self.registry.register(
            name=tool.name,
            handler=tool.func,
            schema=schema,
            is_core=True,
        )

    def run(self, message: str, check_queue: bool = True) -> Response:
        """Run agent with a user message.

        Args:
            message: User message
            check_queue: Check message queue for interrupts

        Returns:
            Agent response
        """
        self._log_turn(f"User: {message}")
        self.history.append(Message(role="user", content=message))

        iterations = 0
        unbounded = self.max_iterations <= 0
        while unbounded or iterations < self.max_iterations:
            iterations += 1
            self._log(f"Iteration {iterations}", style="dim")

            # Get tool schemas
            tools_schema = self.registry.get_schemas() if len(self.registry) > 0 else None

            # Call LLM
            try:
                response = self.llm.chat(
                    messages=self.history,
                    tools=tools_schema,
                )
            except Exception as e:
                self._log(f"LLM call failed: {e}", style="red")
                self._emit_agent_end(success=False, error=str(e))
                raise

            # Check if tool calls are needed
            if hasattr(response, "tool_calls") and response.tool_calls:
                self._log(f"Tool calls requested: {len(response.tool_calls)}", style="yellow")

                tool_results = []
                for tool_call in response.tool_calls:
                    tool_result, abort_batch = self._execute_sync_tool_call(tool_call)
                    tool_results.append(tool_result)
                    if abort_batch:
                        break

                # Add assistant message and tool results to history
                self.history.append(
                    Message(
                        role="assistant",
                        content=response.content or "",
                        metadata={"tool_calls": response.tool_calls},
                    )
                )
                for tool_result in tool_results:
                    self.history.append(
                        Message(
                            role="tool",
                            content=tool_result["content"],
                            metadata={
                                "tool_call_id": tool_result["tool_call_id"],
                                "name": tool_result["name"],
                            },
                        )
                    )

                if tool_results and all(
                    tr.get("result") and tr["result"].ok and tr["result"].meta.get("terminate")
                    for tr in tool_results
                ):
                    final_content = "\n".join(str(tr["content"]) for tr in tool_results)
                    final_response = Response(content=final_content, model=self.llm.config.model)
                    self.history.append(Message(role="assistant", content=final_response.content))
                    self._emit_agent_end(success=True)
                    if check_queue and self.message_queue.has_followup():
                        followup = self.message_queue.get_followup_messages()
                        response = self._drain_followup_messages(followup, check_queue=check_queue)
                        if response is not None:
                            return response
                    return final_response

                # Check for steering messages after tool execution
                if check_queue and self.message_queue.has_steering():
                    steering = self.message_queue.get_steering_messages()
                    for msg in steering:
                        self._log(f"⚡ Steering: {msg.content}", style="yellow")
                        self.history.append(Message(role="user", content=msg.content))

                # Continue loop to get final response
                continue
            else:
                # No tool calls, we have final response
                self.history.append(Message(role="assistant", content=response.content))
                self._log_turn(f"Agent: {response.content}")

                # Check for follow-up messages
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    response = self._drain_followup_messages(followup, check_queue=check_queue)
                    if response is not None:
                        return response

                self._emit_agent_end(success=True)
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    response = self._drain_followup_messages(followup, check_queue=check_queue)
                    if response is not None:
                        return response

                return response

        # Max iterations reached
        final_response = Response(
            content="Maximum iterations reached without completion.",
            model=self.llm.config.model,
        )
        self.history.append(Message(role="assistant", content=final_response.content))
        self._emit_agent_end(success=False, error=final_response.content)
        return final_response

    async def arun(
        self,
        message: str,
        check_queue: bool = True,
        cancel: asyncio.Event | None = None,
    ) -> Response:
        """Async run agent with a user message using enhanced subsystems.

        Uses resilient_streaming_call for LLM calls with retry and fallback.
        Supports context compression, billing tracking, and event emission.

        Args:
            message: User message
            check_queue: Check message queue for interrupts
            cancel: Optional cancellation event (abort between rounds, mid-stream,
                and during tool execution)

        Returns:
            Agent response
        """
        self._log_turn(f"User: {message}")
        self.history.append(Message(role="user", content=message))

        iterations = 0
        max_iters = self.max_iterations
        unbounded = max_iters <= 0

        # Check if plan tool was used and apply max_rounds_with_plan
        if self._plan_used and self.max_rounds_with_plan:
            self._rounds_since_plan += 1
            if self._rounds_since_plan > self.max_rounds_with_plan:
                # Inject plan nag
                nag_message = (
                    "You used the plan tool earlier. Please execute the plan or "
                    "provide a final response."
                )
                self._log(f"Plan nag: {nag_message}")
                self.history.append(Message(role="user", content=nag_message))

        while unbounded or iterations < max_iters:
            iterations += 1
            self._log(f"Iteration {iterations}")

            # Abort between rounds.
            if cancel and cancel.is_set():
                self._emit_agent_end(success=False, error="aborted")
                return Response(content="", model=self.llm.config.model)

            # Get tool schemas
            tools_schema = self.registry.get_schemas() if len(self.registry) > 0 else None

            # Use resilient_streaming_call for LLM call
            response_content = ""
            response_tool_calls = None
            aborted = False

            try:
                async for chunk in resilient_streaming_call(
                    llm=self.llm,
                    messages=self.history,
                    profile_manager=self.profile_manager,
                    compress_fn=self.compress_fn,
                    event_callback=self.event_callback,
                    tools=tools_schema,
                ):
                    if cancel and cancel.is_set():
                        aborted = True
                        break
                    if chunk.content:
                        response_content += chunk.content
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        response_tool_calls = chunk.tool_calls

                # Track billing if hook provided
                if self.billing_hook and hasattr(chunk, "usage"):
                    self.billing_hook.on_llm_call(
                        model=self.llm.config.model,
                        input_tokens=chunk.usage.get("input_tokens", 0),
                        output_tokens=chunk.usage.get("output_tokens", 0),
                    )

            except Exception as e:
                self._log(f"LLM call failed: {e}")
                self._emit_agent_end(success=False, error=str(e))
                raise

            # Aborted mid-stream: record partial text and stop cleanly.
            if aborted or (cancel and cancel.is_set()):
                if response_content:
                    self.history.append(Message(role="assistant", content=response_content))
                self._emit_agent_end(success=False, error="aborted")
                return Response(content=response_content, model=self.llm.config.model)

            # Check if tool calls are needed
            if response_tool_calls:
                self._log(f"Tool calls requested: {len(response_tool_calls)}")

                for tool_call in response_tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    if tool_name == "plan":
                        self._plan_used = True
                        self._rounds_since_plan = 0

                if self._can_use_async_batch_execution():
                    tool_results, terminate_all = await self._execute_async_batch_tool_calls(
                        response_tool_calls, cancel
                    )
                else:
                    terminate_all = False

                if not self._can_use_async_batch_execution():
                    # Execute tools
                    tool_results = []
                    for tool_call in response_tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        tool_args = json.loads(tool_args_str)

                        self._log(
                            f"→ Calling tool: {tool_name}({self._format_tool_args(tool_args)})"
                        )

                        if self.before_tool_call:
                            preflight = self.before_tool_call(tool_name, tool_args)
                            if preflight is not None:
                                result = self._as_tool_result(preflight)
                                tool_results.append(
                                    {
                                        "tool_call_id": tool_call.get("id"),
                                        "role": "tool",
                                        "name": tool_name,
                                        "content": str(result.data if result.ok else result.error),
                                        "result": result,
                                    }
                                )
                                if result.meta.get("abort_batch"):
                                    break
                                continue

                        if self.on_tool_start:
                            self.on_tool_start(tool_name, tool_args)

                        if self.billing_hook:
                            self.billing_hook.on_tool_call(tool_name=tool_name)

                        try:
                            from types import SimpleNamespace

                            tool_call_obj = SimpleNamespace(
                                function=SimpleNamespace(
                                    name=tool_name,
                                    arguments=tool_args_str,
                                )
                            )

                            if hasattr(self.registry, "execute"):
                                result = await self.registry.execute(
                                    tool_call=tool_call_obj,
                                    user_id="default",  # TODO: Make configurable
                                    meta={},
                                    cancel=cancel,
                                )
                            else:
                                result = self.registry.execute_sync(tool_name, tool_args)

                            tool_results.append(
                                {
                                    "tool_call_id": tool_call.get("id"),
                                    "role": "tool",
                                    "name": tool_name,
                                    "content": str(result.data if result.ok else result.error),
                                    "result": result,
                                }
                            )
                            self._log(f"✓ Result: {result.data if result.ok else result.error}")

                            if self.after_tool_call:
                                try:
                                    override = self.after_tool_call(tool_name, tool_args, result)
                                    if override is not None:
                                        result = self._as_tool_result(override)
                                        tool_results[-1]["content"] = str(
                                            result.data if result.ok else result.error
                                        )
                                        tool_results[-1]["result"] = result
                                except Exception as exc:
                                    result = ToolResult(ok=False, error=f"Error: {exc}")
                                    tool_results[-1]["content"] = result.error
                                    tool_results[-1]["result"] = result

                            if self.on_tool_end:
                                self.on_tool_end(tool_name, result)
                        except Exception as e:
                            error_msg = f"Error: {e}"
                            tool_results.append(
                                {
                                    "tool_call_id": tool_call.get("id"),
                                    "role": "tool",
                                    "name": tool_name,
                                    "content": error_msg,
                                    "result": ToolResult(ok=False, error=error_msg),
                                }
                            )
                            self._log(f"✗ {error_msg}")

                # Add assistant message and tool results to history
                self.history.append(
                    Message(
                        role="assistant",
                        content=response_content or "",
                        metadata={"tool_calls": response_tool_calls},
                    )
                )
                for tool_result in tool_results:
                    self.history.append(
                        Message(
                            role="tool",
                            content=tool_result["content"],
                            metadata={
                                "tool_call_id": tool_result["tool_call_id"],
                                "name": tool_result["name"],
                            },
                        )
                    )

                if tool_results and (
                    terminate_all
                    if self._can_use_async_batch_execution()
                    else all(
                        tr.get("result") and tr["result"].ok and tr["result"].meta.get("terminate")
                        for tr in tool_results
                    )
                ):
                    final_content = "\n".join(str(tr["content"]) for tr in tool_results)
                    final_response = Response(content=final_content, model=self.llm.config.model)
                    self.history.append(Message(role="assistant", content=final_response.content))
                    self._emit_agent_end(success=True)
                    if check_queue and self.message_queue.has_followup():
                        followup = self.message_queue.get_followup_messages()
                        if followup:
                            response: Response | None = None
                            for queued in followup:
                                self._log(f"→ Follow-up: {queued.content}")
                                response = await self.arun(queued.content, check_queue=True)
                            if response is not None:
                                return response
                    return final_response

                # Check for steering messages after tool execution
                if check_queue and self.message_queue.has_steering():
                    steering = self.message_queue.get_steering_messages()
                    for msg in steering:
                        self._log(f"⚡ Steering: {msg.content}")
                        self.history.append(Message(role="user", content=msg.content))

                # Continue loop to get final response
                continue
            else:
                # No tool calls, we have final response
                self.history.append(Message(role="assistant", content=response_content))
                self._log_turn(f"Agent: {response_content}")

                # Check for follow-up messages
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    if followup:
                        response: Response | None = None
                        for queued in followup:
                            self._log(f"→ Follow-up: {queued.content}")
                            response = await self.arun(queued.content, check_queue=True)
                        if response is not None:
                            return response

                self._emit_agent_end(success=True)
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    if followup:
                        response: Response | None = None
                        for queued in followup:
                            self._log(f"→ Follow-up: {queued.content}")
                            response = await self.arun(queued.content, check_queue=True)
                        if response is not None:
                            return response

                return Response(
                    content=response_content,
                    model=self.llm.config.model,
                )

        # Max iterations reached
        final_response = Response(
            content="Maximum iterations reached without completion.",
            model=self.llm.config.model,
        )
        self.history.append(Message(role="assistant", content=final_response.content))
        self._emit_agent_end(success=False, error=final_response.content)
        return final_response

    def get_state(self) -> AgentState:
        """Get current agent state.

        Returns:
            Agent state
        """
        return AgentState(
            name=self.name,
            system_prompt=self.system_prompt,
            messages=[msg.model_dump() for msg in self.history],
        )

    def save_state(self, path: str | Path) -> None:
        """Save agent state to file.

        Args:
            path: File path to save state
        """
        state = self.get_state()
        Path(path).write_text(state.model_dump_json(indent=2))

    @classmethod
    def from_state(cls, path: str | Path, llm: LLM | None = None) -> "Agent":
        """Load agent from saved state.

        Args:
            path: File path to load state from
            llm: LLM client (required)

        Returns:
            Agent instance
        """
        state_json = Path(path).read_text()
        state = AgentState.model_validate_json(state_json)

        agent = cls(
            name=state.name,
            llm=llm,
            system_prompt=state.system_prompt,
        )

        # Restore history
        agent.history = [Message(**msg) for msg in state.messages]

        return agent

    def clear_history(self) -> None:
        """Clear conversation history (keeps system prompt)."""
        if self.system_prompt:
            self.history = [Message(role="system", content=self.system_prompt)]
        else:
            self.history = []

    async def respond(
        self,
        message: str,
        cancel: asyncio.Event | None = None,
    ) -> str:
        """Non-streaming respond method that collects all chunks.

        Args:
            message: User message
            cancel: Optional cancellation event

        Returns:
            Complete agent response as string
        """
        chunks = []
        async for chunk in self.respond_stream(message, cancel):
            chunks.append(chunk)
        return "".join(chunks)

    async def respond_stream(
        self,
        message: str,
        cancel: asyncio.Event | None = None,
        max_iterations: int | None = None,
    ) -> AsyncIterator[str]:
        """Streaming respond method that yields text chunks.

        Args:
            message: User message
            cancel: Optional cancellation event
            max_iterations: Per-call round cap. None uses the agent default;
                a value <= 0 means unbounded (loop until natural completion,
                a terminate tool result, or cancellation) — pi-mono parity.

        Yields:
            Text chunks from the agent response
        """
        self._log_turn(f"User: {message}")
        self.history.append(Message(role="user", content=message))

        async for chunk in self._master_loop(cancel, max_iterations):
            yield chunk

    async def _master_loop(
        self,
        cancel: asyncio.Event | None = None,
        max_iterations: int | None = None,
    ) -> AsyncIterator[str]:
        """Unified streaming master loop with tool calling support.

        Args:
            cancel: Optional cancellation event
            max_iterations: Per-call round cap (None = agent default, <= 0 = unbounded)

        Yields:
            Text chunks from the final agent response
        """
        effective_max = self.max_iterations if max_iterations is None else max_iterations
        unbounded = effective_max <= 0

        iterations = 0
        while unbounded or iterations < effective_max:
            iterations += 1
            self._log(f"Iteration {iterations}", style="dim")

            # Check for cancellation before starting the next round
            if cancel and cancel.is_set():
                self._emit_agent_end(success=False, error="aborted")
                return

            # Get tool schemas
            tools_schema = self.registry.get_schemas() if len(self.registry) > 0 else None

            # Call LLM with streaming. achat_stream yields StreamChunks: text
            # deltas (content) and, on completion, a chunk carrying the fully
            # assembled tool_calls.
            stream_call = self.llm.achat_stream(
                messages=self.history,
                tools=tools_schema,
            )
            try:
                if asyncio.iscoroutine(stream_call):
                    response_stream = await stream_call
                else:
                    response_stream = stream_call
            except Exception as e:
                self._log(f"Streaming LLM call failed: {e}", style="red")
                self._emit_agent_end(success=False, error=str(e))
                raise

            # Consume the stream: yield text tokens live, capture tool calls.
            content_parts: list[str] = []
            streamed_tool_calls: list[dict[str, Any]] | None = None
            aborted = False

            async for chunk in response_stream:
                if cancel and cancel.is_set():
                    aborted = True
                    break
                if chunk.content:
                    content_parts.append(chunk.content)
                    yield chunk.content
                if getattr(chunk, "tool_calls", None):
                    streamed_tool_calls = chunk.tool_calls

            # Aborted mid-stream: the partial text already streamed; record it so the
            # session reflects it, then stop cleanly (no dangling tool message).
            if aborted or (cancel and cancel.is_set()):
                partial = "".join(content_parts)
                if partial:
                    self.history.append(Message(role="assistant", content=partial))
                self._emit_agent_end(success=False, error="aborted")
                return

            # No tool calls: the final text already streamed; record it.
            if not streamed_tool_calls:
                final_content = "".join(content_parts)
                self.history.append(Message(role="assistant", content=final_content))
                self._log_turn(f"Agent: {final_content}")

                # If the user steered while we were answering, keep going so the
                # steering is acted on in this same turn instead of being stranded.
                if self.message_queue.has_steering():
                    for msg in self.message_queue.get_steering_messages():
                        self._log(f"⚡ Steering: {msg.content}", style="yellow")
                        self.history.append(Message(role="user", content=msg.content))
                    continue

                self._emit_agent_end(success=True)
                if self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    for queued in followup:
                        async for chunk in self.respond_stream(queued.content, cancel):
                            yield chunk
                return

            # Tool calls: record the assistant turn (with tool_calls) and execute.
            assistant_content = "".join(content_parts) or None
            assistant_tool_calls = streamed_tool_calls
            self.history.append(
                Message(
                    role="assistant",
                    content=assistant_content or "",
                    metadata={"tool_calls": assistant_tool_calls},
                )
            )

            # Execute tool calls
            tool_history_start = len(self.history)
            terminate_all = await self._execute_tool_calls_from_dict(assistant_tool_calls, cancel)
            if terminate_all:
                current_tool_call_ids = {tool_call["id"] for tool_call in assistant_tool_calls}
                final_content = "\n".join(
                    message.content
                    for message in self.history[tool_history_start:]
                    if message.role == "tool"
                    and message.metadata.get("tool_call_id") in current_tool_call_ids
                )
                self.history.append(Message(role="assistant", content=final_content))
                self._emit_agent_end(success=True)
                if self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    for queued in followup:
                        async for chunk in self.respond_stream(queued.content, cancel):
                            yield chunk
                return

            # Inject steering messages queued during this turn (e.g. typed while
            # the agent was streaming) before the next LLM call. Mirrors run().
            if self.message_queue.has_steering():
                for msg in self.message_queue.get_steering_messages():
                    self._log(f"⚡ Steering: {msg.content}", style="yellow")
                    self.history.append(Message(role="user", content=msg.content))

            # Continue loop for next iteration

        # Bounded loop exhausted its round budget (unreachable when unbounded).
        self._emit_agent_end(
            success=False,
            error="Maximum iterations reached without completion.",
        )
        yield "Maximum iterations reached without completion."

    async def _execute_tool_calls_from_dict(
        self,
        tool_calls: list[dict[str, Any]],
        cancel: asyncio.Event | None = None,
    ) -> bool:
        """Execute tool calls from dictionary format.

        Args:
            tool_calls: List of tool call dictionaries
            cancel: Optional cancellation event

        Returns:
            True when every tool result requested early termination.
        """
        if self._can_use_async_batch_execution():
            tool_messages, terminate_all = await self._execute_async_batch_tool_calls(
                tool_calls, cancel
            )
            for tool_result in tool_messages:
                self.history.append(
                    Message(
                        role="tool",
                        content=tool_result["content"],
                        metadata={
                            "tool_call_id": tool_result["tool_call_id"],
                            "name": tool_result["name"],
                        },
                    )
                )
            return terminate_all

        terminate_all = True
        for tool_call in tool_calls:
            if cancel and cancel.is_set():
                return False

            tool_name = tool_call.get("function", {}).get("name")
            tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
            tool_call_id = tool_call.get("id")

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            self._log(
                f"→ Calling tool: {tool_name}({self._format_tool_args(tool_args)})", style="cyan"
            )

            if self.before_tool_call:
                preflight = self.before_tool_call(tool_name, tool_args)
                if preflight is not None:
                    result = self._as_tool_result(preflight)
                    self.history.append(
                        Message(
                            role="tool",
                            content=str(result.data if result.ok else result.error),
                            metadata={
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                            },
                        )
                    )
                    terminate_all = terminate_all and bool(
                        result.ok and result.meta.get("terminate")
                    )
                    if result.meta.get("abort_batch"):
                        return False
                    continue

            if self.on_tool_start:
                self.on_tool_start(tool_name, tool_args)

            try:
                if hasattr(self.registry, "execute"):
                    from types import SimpleNamespace

                    tool_call_obj = SimpleNamespace(
                        function=SimpleNamespace(
                            name=tool_name,
                            arguments=tool_args_str,
                        )
                    )
                    result = await self.registry.execute(tool_call_obj, "default", {}, cancel)
                else:
                    result = self.registry.execute_sync(tool_name, tool_args)
                self.history.append(
                    Message(
                        role="tool",
                        content=str(result.data if result.ok else result.error),
                        metadata={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                        },
                    )
                )
                self._log(f"✓ Result: {result.data if result.ok else result.error}", style="green")

                if self.after_tool_call:
                    try:
                        override = self.after_tool_call(tool_name, tool_args, result)
                        if override is not None:
                            result = self._as_tool_result(override)
                            self.history[-1].content = str(
                                result.data if result.ok else result.error
                            )
                    except Exception as exc:
                        result = ToolResult(ok=False, error=f"Error: {exc}")
                        self.history[-1].content = result.error

                if self.on_tool_end:
                    self.on_tool_end(tool_name, result)
                terminate_all = terminate_all and bool(result.ok and result.meta.get("terminate"))
            except Exception as e:
                error_msg = f"Error: {e}"
                self.history.append(
                    Message(
                        role="tool",
                        content=error_msg,
                        metadata={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                        },
                    )
                )
                self._log(f"✗ {error_msg}", style="red")
                terminate_all = False

        return terminate_all

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """Execute tool calls (backward compatibility wrapper).

        Args:
            tool_calls: List of tool call dictionaries
        """
        await self._execute_tool_calls_from_dict(tool_calls, None)
