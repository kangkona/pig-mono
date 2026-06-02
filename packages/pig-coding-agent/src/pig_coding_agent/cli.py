"""CLI entry point for py-coding-agent."""

import json
import os
import sys
from io import UnsupportedOperation
from pathlib import Path
from typing import Any, TypeVar

import typer
from pig_agent_core import assert_valid_session_id
from pig_llm import LLM
from rich.console import Console

from .agent import CodingAgent
from .config import ConfigManager

app = typer.Typer(
    name="pig-code",
    help="Interactive coding agent CLI",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()
T = TypeVar("T")


def _read_piped_stdin() -> str | None:
    """Return piped stdin content when available in non-protocol modes."""
    import select

    try:
        ready = select.select([sys.stdin], [], [], 0.0)[0]
    except (OSError, ValueError, UnsupportedOperation):
        return None

    if not ready:
        return None

    data = sys.stdin.read()
    if not data:
        return None
    return data.rstrip("\n")


def _resolve_option_value(value: T) -> T | None:
    """Unwrap direct-call Typer OptionInfo defaults during tests."""
    if isinstance(value, typer.models.OptionInfo):
        return None
    return value


class JsonLineWriter:
    """Strict JSONL protocol writer for non-interactive modes."""

    def __init__(self, output=None):
        self.output = output or sys.stdout

    def write(self, payload: dict[str, Any]) -> None:
        self.output.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.output.flush()


def _shutdown_extensions(agent: Any, reason: str) -> None:
    """Forward protocol shutdown reasons into extension cleanup."""
    extension_manager = getattr(agent, "extension_manager", None)
    if extension_manager is None:
        return
    extension_manager.cleanup(reason=reason)


def _parse_excluded_tools(value: str | None) -> set[str]:
    """Parse comma-separated tool names."""
    if not value or not isinstance(value, str):
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def _validate_session_selector_flags(
    *,
    fork: str | None,
    session_id: str | None,
    session_name: str | None,
    resume: bool,
    continue_session: bool,
) -> None:
    """Reject conflicting exact-session and session-selector flags."""
    if fork is not None:
        conflicting_flags = []
        if session_name:
            conflicting_flags.append("--session")
        if continue_session:
            conflicting_flags.append("--continue")
        if resume:
            conflicting_flags.append("--resume")

        if conflicting_flags:
            console.print(
                f"[red]Error: --fork cannot be combined with {', '.join(conflicting_flags)}[/red]"
            )
            raise typer.Exit(1)

    if session_id is None:
        return

    conflicting_flags = []
    if session_name:
        conflicting_flags.append("--session")
    if continue_session:
        conflicting_flags.append("--continue")
    if resume:
        conflicting_flags.append("--resume")

    if conflicting_flags:
        console.print(
            f"[red]Error: --session-id cannot be combined with {', '.join(conflicting_flags)}[/red]"
        )
        raise typer.Exit(1)

    try:
        assert_valid_session_id(session_id)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc


def _validate_startup_name(name: str | None) -> None:
    """Reject empty startup session display names."""
    if name is None:
        return
    if not name.strip():
        console.print("[red]Error: --name requires a non-empty value[/red]")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model to use"),
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider"),
    workspace: Path = typer.Option(".", "--path", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v/-q", help="Verbose output"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Resume last session"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    fork: str | None = typer.Option(None, "--fork", help="Fork specific session file or ID"),
    session_name: str | None = typer.Option(None, "--session", "-s", help="Session name"),
    name: str | None = typer.Option(None, "--name", "-n", help="Startup session display name"),
    session_dir: Path | None = typer.Option(
        None, "--session-dir", help="Explicit session storage directory"
    ),
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
    compat_mode: str | None = typer.Option(
        None,
        "--compat-mode",
        help="Explicit OpenAI-compatible request normalization mode",
    ),
):
    """Start interactive coding agent."""
    if ctx.invoked_subcommand is not None:
        return
    protocol_mode = mode in {"json", "rpc"}
    resolved_verbose = bool(verbose) if isinstance(verbose, bool) else True
    if protocol_mode:
        resolved_verbose = False
    resolved_resume = bool(resume) if isinstance(resume, bool) else False
    resolved_continue = bool(continue_session) if isinstance(continue_session, bool) else False
    resolved_fork = _resolve_option_value(fork)
    resolved_session_name = _resolve_option_value(session_name)
    resolved_name = _resolve_option_value(name)
    resolved_session_dir = _resolve_option_value(session_dir)
    resolved_session_id = _resolve_option_value(session_id)
    resolved_exclude_tools = _resolve_option_value(exclude_tools)
    resolved_base_url = _resolve_option_value(base_url)
    resolved_compat_mode = _resolve_option_value(compat_mode)

    _validate_session_selector_flags(
        fork=resolved_fork,
        session_id=resolved_session_id,
        session_name=resolved_session_name,
        resume=resolved_resume,
        continue_session=resolved_continue,
    )
    _validate_startup_name(resolved_name)

    if resolved_session_dir is None and os.environ.get("PIG_CODING_AGENT_SESSION_DIR") is None:
        configured_session_dir = ConfigManager(workspace).get_session_dir()
        if configured_session_dir:
            resolved_session_dir = Path(configured_session_dir).expanduser()

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
        base_url=resolved_base_url,
        compat_mode=resolved_compat_mode,
    )

    # Handle session loading
    session_path = None
    if resolved_fork:
        from pig_agent_core import SessionManager

        session_mgr = SessionManager(workspace, session_dir=resolved_session_dir)
        session_path = session_mgr.find_session(resolved_fork)
        if session_path is None:
            if not protocol_mode:
                console.print(f"[red]Session '{resolved_fork}' not found[/red]")
            raise typer.Exit(1)
    elif resolved_resume or resolved_continue or resolved_session_name:
        from pig_agent_core import SessionManager

        session_mgr = SessionManager(workspace, session_dir=resolved_session_dir)
        if resolved_session_name:
            session_path = session_mgr.find_session(resolved_session_name)
        else:
            sessions = session_mgr.list_sessions(limit=10)

            if not sessions:
                if not protocol_mode:
                    console.print("[yellow]No previous sessions found[/yellow]")
            elif resolved_continue or len(sessions) == 1:
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
        verbose=resolved_verbose,
        session_name=resolved_name or resolved_session_name,
        session_id=resolved_session_id,
        session_dir=resolved_session_dir,
        session_path=session_path,
        fork_source_path=session_path if resolved_fork else None,
        enable_extensions=not no_extensions,
        enable_skills=not no_skills,
        enable_resilience=not no_resilience,
        enable_cost_tracking=not no_cost_tracking,
        excluded_tools=_parse_excluded_tools(resolved_exclude_tools),
    )

    piped_input = None
    if not protocol_mode:
        piped_input = _read_piped_stdin()

    if not protocol_mode and piped_input is None:
        console.print("[green]✓ Coding Agent started[/green]")
        console.print(f"Model: [cyan]{llm.config.model}[/cyan]")
        console.print(f"Workspace: [cyan]{workspace.resolve()}[/cyan]")

    if not protocol_mode and piped_input is None and agent.session:
        console.print(f"Session: [cyan]{agent.session.name}[/cyan]")

    if (
        not protocol_mode
        and piped_input is None
        and agent.skill_manager
        and len(agent.skill_manager) > 0
    ):
        console.print(f"Skills: [cyan]{len(agent.skill_manager)} loaded[/cyan]")

    if (
        not protocol_mode
        and piped_input is None
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
        if piped_input:
            response = agent.agent.run(piped_input)
            if response.content:
                print(response.content)
            return
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

    def emit_shutdown(reason: str) -> None:
        json_out.emit_event("shutdown", {"reason": reason})
        _shutdown_extensions(agent, reason)

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
                emit_shutdown("error")
                return
        emit_shutdown("eof")
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

            except KeyboardInterrupt:
                emit_shutdown("interrupt")
                break
            except EOFError:
                emit_shutdown("eof")
                break
            except Exception as e:
                json_out.error(f"Error: {e}")
                emit_shutdown("error")
                break


def run_rpc_mode(agent):
    """Run agent in RPC mode.

    Args:
        agent: CodingAgent instance
    """
    from pig_agent_core import RPCMode

    rpc = RPCMode()

    def emit_shutdown(reason: str) -> None:
        rpc.send_event("shutdown", {"reason": reason})
        _shutdown_extensions(agent, reason)

    rpc._shutdown_callback = emit_shutdown

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
    emit_shutdown(getattr(rpc, "last_shutdown_reason", None) or "eof")


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
