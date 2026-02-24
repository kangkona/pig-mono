"""Basic web UI server example."""

import os
from pig_llm import LLM
from pig_web_ui import ChatServer


def main():
    """Run basic web chat server."""
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return

    # Create LLM
    llm = LLM(
        provider="openai",
        api_key=api_key,
        model="gpt-3.5-turbo",
    )

    # Create server
    server = ChatServer(
        llm=llm,
        title="My AI Assistant",
        port=8000,
        cors=True,  # Enable CORS for development
    )

    print("=" * 50)
    print("Web UI Server")
    print("=" * 50)
    print(f"Model: {llm.config.model}")
    print(f"URL: http://localhost:8000")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)

    # Run server
    server.run()


if __name__ == "__main__":
    main()
