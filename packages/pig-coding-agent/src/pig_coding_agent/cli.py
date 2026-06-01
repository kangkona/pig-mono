"""CLI entry point for py-coding-agent."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from pig_llm import LLM
from rich.console import Console

from .agent import CodingAgent

app = typer.Typer(
    name="pig-code",
    help="Interactive coding agent CLI",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


class JsonLineWriter:
    """Strict JSONL protocol writer for non-interactive modes."""

    def __init__(self, output=None):
        self.output = output or sys.stdout

    def write(self, payload: dict[str, Any]) -> None:
        self.output.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.output.flush()


def _parse_excluded_tools(value: str | None) -> set[str]:
    """Parse comma-separated tool names."""
    if not value or not isinstance(value, str):
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model to use"),
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider"),
    workspace: Path = typer.Option(".", "--path", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v/-q", help="Verbose output"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume last session"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    session_name: str | None = typer.Option(None, "--session", "-s", help="Session name"),
    name: str | None = typer.Option(None, "--name", "-n", help="Startup session display name"),
    session_id: str | None = typer.Option(
        None, "--session-id", help="Explicit session ID for automation"
    ),
    exclude_tools: str | None = typer.Option(
        None,
        "--exclude-tools",
        "-xt",
        help="Comma-separated built-in tool names to disable",
    ),
    no_extensions: bool = typer.Option(False, "--no-extensions", help="Disable extensions"),
    no_skills: bool = typer.Option(False, "--no-skills", help="Disable skills"),
    no_resilience: bool = typer.Option(False, "--no-resilience", help="Disable resilience"),
    no_cost_tracking: bool = typer.Option(
        False, "--no-cost-tracking", help="Disable cost tracking"
    ),
    mode: str = typer.Option("interactive", "--mode", help="Output mode: interactive, json, rpc"),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Custom API base URL (for custom providers)"
    ),
):
    """Start interactive coding agent."""
    if ctx.invoked_subcommand is not None:
        return
    protocol_mode = mode in {"json", "rpc"}

    # Get API key
    api_key = os.getenv(f"{provider.upper()}_API_KEY")
    if not api_key:
        console.print(f"[red]Error: {provider.upper()}_API_KEY not set[/red]")
        console.print(f"Please set your API key: export {provider.upper()}_API_KEY=your-key")
        raise typer.Exit(1)

    # Create LLM
    llm = LLM(
        provider=provider,
        api_key=api_key,
        model=model or ("gpt-3.5-turbo" if provider == "openai" else None),
        base_url=base_url,
    )

    # Handle session loading
    session_path = None
    if resume or continue_session:
        from pig_agent_core import SessionManager

        session_mgr = SessionManager(workspace)
        sessions = session_mgr.list_sessions(limit=10)

        if not sessions:
            if not protocol_mode:
                console.print("[yellow]No previous sessions found[/yellow]")
        elif continue_session or len(sessions) == 1:
            # Auto-continue most recent
            session_path = sessions[0].path
            if not protocol_mode:
                console.print(f"[cyan]Continuing:[/cyan] {sessions[0].session_name}")
        else:
            # Show selection UI
            if not protocol_mode:
                console.print("[cyan]Recent sessions:[/cyan]\n")
                console.print(session_mgr.format_session_list(sessions))
                console.print()

            from pig_tui import Prompt

            prompt = Prompt()

            try:
                choice = prompt.ask("Select session (number or name)", default="1")

                # Parse choice
                if choice.isdigit() and 1 <= int(choice) <= len(sessions):
                    session_path = sessions[int(choice) - 1].path
                else:
                    # Try by name
                    found = session_mgr.find_session(choice)
                    if found:
                        session_path = found
                    else:
                        if not protocol_mode:
                            console.print(
                                f"[yellow]Session '{choice}' not found, starting new[/yellow]"
                            )
            except (KeyboardInterrupt, EOFError):
                if not protocol_mode:
                    console.print("[yellow]Starting new session[/yellow]")

    # Create and run agent
    agent = CodingAgent(
        llm=llm,
        workspace=str(workspace),
        verbose=verbose,
        session_name=name or session_name,
        session_id=session_id,
        session_path=session_path,
        enable_extensions=not no_extensions,
        enable_skills=not no_skills,
        enable_resilience=not no_resilience,
        enable_cost_tracking=not no_cost_tracking,
        excluded_tools=_parse_excluded_tools(exclude_tools),
    )

    if not protocol_mode:
        console.print("[green]✓ Coding Agent started[/green]")
        console.print(f"Model: [cyan]{llm.config.model}[/cyan]")
        console.print(f"Workspace: [cyan]{workspace.resolve()}[/cyan]")

    if not protocol_mode and agent.session:
        console.print(f"Session: [cyan]{agent.session.name}[/cyan]")

    if not protocol_mode and agent.skill_manager and len(agent.skill_manager) > 0:
        console.print(f"Skills: [cyan]{len(agent.skill_manager)} loaded[/cyan]")

    if (
        not protocol_mode
        and agent.extension_manager
        and len(agent.extension_manager.extensions) > 0
    ):
        console.print(f"Extensions: [cyan]{len(agent.extension_manager.extensions)} loaded[/cyan]")

    # Handle different output modes
    if mode == "json":
        run_json_mode(agent)
    elif mode == "rpc":
        run_rpc_mode(agent)
    else:
        console.print()
        console.print("[dim]Type /help for commands, /exit to quit[/dim]")
        console.print()
        agent.run_interactive()


def run_json_mode(agent):
    """Run agent in JSON output mode.

    Args:
        agent: CodingAgent instance
    """
    from pig_agent_core import JSONOutputMode

    json_out = JSONOutputMode()

    # Read from stdin if piped, otherwise interactive
    import select

    if select.select([sys.stdin], [], [], 0.0)[0]:
        # Input available, read line
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                # Parse input
                data = json.loads(line)
                message = data.get("message") or data.get("content")

                if not message:
                    json_out.error("No message in request")
                    continue

                # Send message event
                json_out.message("user", message)

                # Get response
                response = agent.agent.run(message)

                # Send response
                json_out.message("assistant", response.content)
                json_out.done(response.content)

            except json.JSONDecodeError as e:
                json_out.error(f"Invalid JSON: {e}")
            except Exception as e:
                json_out.error(f"Error: {e}")
    else:
        # Interactive JSON mode
        json_out.emit_event("ready", {"agent": "pig-code", "mode": "json"})

        while True:
            try:
                user_input = input()
                if not user_input:
                    continue

                json_out.message("user", user_input)
                response = agent.agent.run(user_input)
                json_out.message("assistant", response.content)
                json_out.done()

            except (KeyboardInterrupt, EOFError):
                json_out.emit_event("shutdown", {"reason": "eof"})
                break


def run_rpc_mode(agent):
    """Run agent in RPC mode.

    Args:
        agent: CodingAgent instance
    """
    from pig_agent_core import RPCMode

    rpc = RPCMode()

    def handle_request(method: str, params: dict) -> Any:
        """Handle RPC requests.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            Method result
        """
        if method == "complete":
            message = params.get("message")
            if not message:
                raise ValueError("Missing 'message' parameter")

            response = agent.agent.run(message)
            return {"content": response.content, "model": agent.agent.llm.config.model}

        elif method == "stream":
            message = params.get("message")
            if not message:
                raise ValueError("Missing 'message' parameter")

            # Stream tokens as events
            for chunk in agent.agent.llm.stream(message):
                rpc.send_event("token", {"content": chunk.content})

            return {"done": True}

        elif method == "bash":
            command = params.get("command")
            if not command:
                raise ValueError("Missing 'command' parameter")

            from .tools import ShellTools

            output = ShellTools().run_command(
                command,
                cwd=params.get("cwd"),
                exclude_from_context=bool(params.get("excludeFromContext")),
            )
            return {
                "output": output,
                "excludedFromContext": bool(params.get("excludeFromContext")),
            }

        elif method == "ping":
            return {"pong": True}

        elif method == "status":
            return {
                "model": agent.agent.llm.config.model,
                "provider": agent.agent.llm.config.provider,
                "tools": len(agent.agent.registry),
            }

        else:
            raise ValueError(f"Unknown method: {method}")

    # Run server
    rpc.run_server(handle_request)


@app.command()
def gen(
    description: str = typer.Argument(..., help="What to generate"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model"),
):
    """Generate code from description."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY not set[/red]")
        raise typer.Exit(1)

    llm = LLM(api_key=api_key, model=model or "gpt-3.5-turbo")
    agent = CodingAgent(llm=llm, verbose=False)

    console.print(f"[cyan]Generating:[/cyan] {description}")
    result = agent.run_once(f"Generate code for: {description}")

    if output:
        output.write_text(result)
        console.print(f"[green]Saved to:[/green] {output}")
    else:
        console.print(result)


@app.command()
def analyze(
    path: Path = typer.Argument(..., help="File or directory to analyze"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model"),
):
    """Analyze code and provide insights."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY not set[/red]")
        raise typer.Exit(1)

    if not path.exists():
        console.print(f"[red]Error: {path} does not exist[/red]")
        raise typer.Exit(1)

    llm = LLM(api_key=api_key, model=model or "gpt-3.5-turbo")
    agent = CodingAgent(llm=llm, verbose=False)

    console.print(f"[cyan]Analyzing:[/cyan] {path}")
    result = agent.run_once(f"Analyze the file {path} and provide insights")
    console.print(result)


if __name__ == "__main__":
    app()
