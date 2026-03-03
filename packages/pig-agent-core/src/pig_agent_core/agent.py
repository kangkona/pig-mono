"""Main Agent class with tool calling and state management."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from pig_llm import LLM, Message, Response
from rich.console import Console

from .memory import InMemoryProvider, MemoryProvider
from .message_queue import MessageQueue
from .models import AgentState
from .observability.events import AgentEventCallback
from .registry import ToolRegistry
from .resilience.profile import ProfileManager
from .tools import Tool


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
        # New subsystem parameters
        profile_manager: ProfileManager | None = None,
        event_callback: AgentEventCallback | None = None,
        compress_fn: Callable[[list[Message]], list[Message]] | None = None,
        memory_provider: MemoryProvider | None = None,
    ):
        """Initialize agent.

        Args:
            name: Agent name
            llm: LLM client
            tools: List of tools
            system_prompt: System prompt
            max_iterations: Maximum tool calling iterations
            on_tool_start: Callback when tool starts
            on_tool_end: Callback when tool ends
            verbose: Enable verbose logging
            profile_manager: Optional profile manager for resilience
            event_callback: Optional callback for observability events
            compress_fn: Optional function to compress messages on context overflow
            memory_provider: Optional memory provider for conversation history
        """
        self.name = name
        self.llm = llm or LLM()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.verbose = verbose

        # New subsystems
        self.profile_manager = profile_manager
        self.event_callback = event_callback
        self.compress_fn = compress_fn
        self.memory_provider = memory_provider or InMemoryProvider()

        self.registry = ToolRegistry()
        if tools:
            for tool in tools:
                self.registry.register(tool)

        self.history: list[Message] = []
        if system_prompt:
            self.history.append(Message(role="system", content=system_prompt))

        self.console = Console() if verbose else None
        self.message_queue = MessageQueue()

    def _log(self, message: str, style: str = ""):
        """Log message if verbose."""
        if self.console:
            self.console.print(message, style=style)

    def add_tool(self, tool: Tool) -> None:
        """Add a tool to the agent.

        Args:
            tool: Tool to add
        """
        self.registry.register(tool)

    def run(self, message: str, check_queue: bool = True) -> Response:
        """Run agent with a user message.

        Args:
            message: User message
            check_queue: Check message queue for interrupts

        Returns:
            Agent response
        """
        self._log(f"[bold blue]User:[/bold blue] {message}")
        self.history.append(Message(role="user", content=message))

        iterations = 0
        while iterations < self.max_iterations:
            iterations += 1
            self._log(f"[dim]Iteration {iterations}[/dim]")

            # Get tool schemas
            tools_schema = self.registry.get_schemas() if len(self.registry) > 0 else None

            # Call LLM
            response = self.llm.chat(
                messages=self.history,
                tools=tools_schema,
            )

            # Check if tool calls are needed
            if hasattr(response, "tool_calls") and response.tool_calls:
                self._log(f"[yellow]Tool calls requested: {len(response.tool_calls)}[/yellow]")

                # Execute tools
                tool_results = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

                    self._log(f"[cyan]→ Calling tool: {tool_name}({tool_args})[/cyan]")

                    if self.on_tool_start:
                        self.on_tool_start(tool_name, tool_args)

                    try:
                        result = self.registry.execute(tool_name, **tool_args)
                        tool_results.append(
                            {
                                "tool_call_id": tool_call.get("id"),
                                "role": "tool",
                                "name": tool_name,
                                "content": str(result),
                            }
                        )
                        self._log(f"[green]✓ Result: {result}[/green]")

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
                            }
                        )
                        self._log(f"[red]✗ {error_msg}[/red]")

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

                # Check for steering messages after tool execution
                if check_queue and self.message_queue.has_steering():
                    steering = self.message_queue.get_steering_messages()
                    for msg in steering:
                        self._log(f"[yellow]⚡ Steering: {msg.content}[/yellow]")
                        self.history.append(Message(role="user", content=msg.content))

                # Continue loop to get final response
                continue
            else:
                # No tool calls, we have final response
                self.history.append(Message(role="assistant", content=response.content))
                self._log(f"[bold green]Agent:[/bold green] {response.content}")

                # Check for follow-up messages
                if check_queue and self.message_queue.has_followup():
                    followup = self.message_queue.get_followup_messages()
                    if followup:
                        # Process first follow-up recursively
                        self._log(f"[cyan]→ Follow-up: {followup[0].content}[/cyan]")
                        return self.run(followup[0].content, check_queue=True)

                return response

        # Max iterations reached
        final_response = Response(
            content="Maximum iterations reached without completion.",
            model=self.llm.config.model,
        )
        self.history.append(Message(role="assistant", content=final_response.content))
        return final_response

    async def arun(self, message: str) -> Response:
        """Async run agent with a user message.

        Args:
            message: User message

        Returns:
            Agent response
        """
        # For now, just call sync version
        # TODO: Implement full async support
        return self.run(message)

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
    ) -> AsyncIterator[str]:
        """Streaming respond method that yields text chunks.

        Args:
            message: User message
            cancel: Optional cancellation event

        Yields:
            Text chunks from the agent response
        """
        self._log(f"[bold blue]User:[/bold blue] {message}")
        self.history.append(Message(role="user", content=message))

        async for chunk in self._master_loop(cancel):
            yield chunk

    async def _master_loop(
        self,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Unified streaming master loop with tool calling support.

        Args:
            cancel: Optional cancellation event

        Yields:
            Text chunks from the final agent response
        """
        iterations = 0
        while iterations < self.max_iterations:
            iterations += 1
            self._log(f"[dim]Iteration {iterations}[/dim]")

            # Check for cancellation
            if cancel and cancel.is_set():
                yield "Request was cancelled."
                return

            # Get tool schemas
            tools_schema = self.registry.get_schemas() if len(self.registry) > 0 else None

            # Call LLM with streaming
            response_stream = self.llm.achat_stream(
                messages=self.history,
                tools=tools_schema,
            )

            # Accumulate streaming response
            content_parts = []
            tool_calls_acc: dict[int, dict[str, str]] = {}
            has_tool_calls = False
            buffered = []

            async for chunk in response_stream:
                if not hasattr(chunk, "choices") or not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Accumulate content
                if hasattr(delta, "content") and delta.content:
                    content_parts.append(delta.content)
                    if not has_tool_calls:
                        buffered.append(delta.content)

                # Accumulate tool calls
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    if not has_tool_calls:
                        has_tool_calls = True
                        buffered.clear()

                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index if hasattr(tc_delta, "index") else 0
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}

                        if hasattr(tc_delta, "id") and tc_delta.id:
                            tool_calls_acc[idx]["id"] = tc_delta.id

                        if hasattr(tc_delta, "function") and tc_delta.function:
                            if hasattr(tc_delta.function, "name") and tc_delta.function.name:
                                tool_calls_acc[idx]["name"] = tc_delta.function.name
                            if (
                                hasattr(tc_delta.function, "arguments")
                                and tc_delta.function.arguments
                            ):
                                tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

            # If no tool calls, yield buffered content and return
            if not tool_calls_acc:
                final_content = "".join(buffered)
                self.history.append(Message(role="assistant", content=final_content))
                self._log(f"[bold green]Agent:[/bold green] {final_content}")
                for part in buffered:
                    yield part
                return

            # Process tool calls
            assistant_content = "".join(content_parts) or None
            assistant_tool_calls = []
            for idx in sorted(tool_calls_acc):
                tc = tool_calls_acc[idx]
                assistant_tool_calls.append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                )

            # Add assistant message with tool calls to history
            self.history.append(
                Message(
                    role="assistant",
                    content=assistant_content or "",
                    metadata={"tool_calls": assistant_tool_calls},
                )
            )

            # Execute tool calls
            await self._execute_tool_calls_from_dict(assistant_tool_calls, cancel)

            # Continue loop for next iteration

        # Max iterations reached
        yield "Maximum iterations reached without completion."

    async def _execute_tool_calls_from_dict(
        self,
        tool_calls: list[dict[str, Any]],
        cancel: asyncio.Event | None = None,
    ) -> None:
        """Execute tool calls from dictionary format.

        Args:
            tool_calls: List of tool call dictionaries
            cancel: Optional cancellation event
        """
        for tool_call in tool_calls:
            if cancel and cancel.is_set():
                return

            tool_name = tool_call.get("function", {}).get("name")
            tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
            tool_call_id = tool_call.get("id")

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            self._log(f"[cyan]→ Calling tool: {tool_name}({tool_args})[/cyan]")

            if self.on_tool_start:
                self.on_tool_start(tool_name, tool_args)

            try:
                result = self.registry.execute(tool_name, **tool_args)
                self.history.append(
                    Message(
                        role="tool",
                        content=str(result),
                        metadata={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                        },
                    )
                )
                self._log(f"[green]✓ Result: {result}[/green]")

                if self.on_tool_end:
                    self.on_tool_end(tool_name, result)
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
                self._log(f"[red]✗ {error_msg}[/red]")

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """Execute tool calls (backward compatibility wrapper).

        Args:
            tool_calls: List of tool call dictionaries
        """
        await self._execute_tool_calls_from_dict(tool_calls, None)
