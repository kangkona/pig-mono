"""Main Agent class with tool calling and state management."""

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pig_llm import LLM, Message, Response
from rich.console import Console

from .models import AgentState, ToolCall, ToolResult
from .registry import ToolRegistry
from .tools import Tool
from .message_queue import MessageQueue


class Agent:
    """Agent with LLM and tool calling capabilities."""

    def __init__(
        self,
        name: str = "Agent",
        llm: Optional[LLM] = None,
        tools: Optional[list[Tool]] = None,
        system_prompt: Optional[str] = None,
        max_iterations: int = 10,
        on_tool_start: Optional[Callable] = None,
        on_tool_end: Optional[Callable] = None,
        verbose: bool = False,
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
        """
        self.name = name
        self.llm = llm or LLM()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.verbose = verbose

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
                        tool_results.append({
                            "tool_call_id": tool_call.get("id"),
                            "role": "tool",
                            "name": tool_name,
                            "content": str(result),
                        })
                        self._log(f"[green]✓ Result: {result}[/green]")
                        
                        if self.on_tool_end:
                            self.on_tool_end(tool_name, result)
                    except Exception as e:
                        error_msg = f"Error: {e}"
                        tool_results.append({
                            "tool_call_id": tool_call.get("id"),
                            "role": "tool",
                            "name": tool_name,
                            "content": error_msg,
                        })
                        self._log(f"[red]✗ {error_msg}[/red]")

                # Add assistant message and tool results to history
                self.history.append(Message(
                    role="assistant",
                    content=response.content or "",
                    metadata={"tool_calls": response.tool_calls}
                ))
                for tool_result in tool_results:
                    self.history.append(Message(
                        role="tool",
                        content=tool_result["content"],
                        metadata={
                            "tool_call_id": tool_result["tool_call_id"],
                            "name": tool_result["name"]
                        }
                    ))
                
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
    def from_state(cls, path: str | Path, llm: Optional[LLM] = None) -> "Agent":
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
