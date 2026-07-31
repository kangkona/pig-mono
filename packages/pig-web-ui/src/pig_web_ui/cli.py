"""CLI entry point for py-web-ui."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pig_llm import LLM

try:
    import typer
    from rich.console import Console
except ImportError:
    print("Error: Required dependencies not installed")
    print("Run: pip install py-web-ui")
    sys.exit(1)

from .server import ChatServer

console = Console()


def _load_llm_class() -> type[LLM]:
    try:
        from pig_llm import LLM
    except ImportError as exc:
        raise RuntimeError("pig_llm is not installed. Run: pip install pig-llm") from exc
    return LLM


def main(
    model: str | None = None,
    provider: str = "openai",
    port: int = 8000,
    host: str = "127.0.0.1",
    cors: bool = False,
    title: str = "Chat",
) -> None:
    """Start web chat server.

    Args:
        model: LLM model to use
        provider: LLM provider (openai, anthropic, google)
        port: Server port
        host: Server host
        cors: Enable CORS
        title: Chat title
    """
    # Get API key
    api_key = os.getenv(f"{provider.upper()}_API_KEY")
    if not api_key:
        console.print(f"[red]Error: {provider.upper()}_API_KEY not set[/red]")
        console.print(f"Please set your API key: export {provider.upper()}_API_KEY=your-key")
        sys.exit(1)

    # Create LLM
    try:
        llm_class = _load_llm_class()
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    try:
        llm = llm_class(
            provider=provider,
            api_key=api_key,
            model=model or ("gpt-3.5-turbo" if provider == "openai" else None),
        )
    except Exception as e:
        console.print(f"[red]Error creating LLM: {e}[/red]")
        sys.exit(1)

    # Create server
    server = ChatServer(
        llm=llm,
        title=title,
        port=port,
        host=host,
        cors=cors,
    )

    # Print info
    console.print("[green]✓ Web UI Server started[/green]")
    console.print(f"Model: [cyan]{llm.config.model}[/cyan]")
    console.print(f"URL: [cyan]http://{host}:{port}[/cyan]")
    console.print()
    console.print("Press Ctrl+C to stop")

    # Run server
    try:
        server.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")


def cli() -> None:
    """Entry point for pig-webui command."""
    typer.run(main)


if __name__ == "__main__":
    cli()
