"""CLI entry point for py-web-ui."""

import os
import sys
from typing import Optional

try:
    import typer
    from rich.console import Console
except ImportError:
    print("Error: Required dependencies not installed")
    print("Run: pip install py-web-ui")
    sys.exit(1)

try:
    from pig_llm import LLM
except ImportError:
    print("Error: py-ai not installed")
    print("Run: pip install py-ai")
    sys.exit(1)

from .server import ChatServer


console = Console()


def main(
    model: Optional[str] = None,
    provider: str = "openai",
    port: int = 8000,
    host: str = "127.0.0.1",
    cors: bool = False,
    title: str = "Chat",
):
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
        llm = LLM(
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
    console.print(f"[green]✓ Web UI Server started[/green]")
    console.print(f"Model: [cyan]{llm.config.model}[/cyan]")
    console.print(f"URL: [cyan]http://{host}:{port}[/cyan]")
    console.print()
    console.print("Press Ctrl+C to stop")
    
    # Run server
    try:
        server.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")


def cli():
    """Entry point for pig-webui command."""
    typer.run(main)


if __name__ == "__main__":
    cli()
