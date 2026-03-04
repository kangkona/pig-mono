#!/usr/bin/env python3
"""Web Agent Demo

This example demonstrates using pig-agent-tools web tools with pig-agent-core:
- Searching the web with Tavily API
- Reading webpage content
- Tool result handling
- Error handling

Requirements:
- Set TAVILY_API_KEY environment variable
- Set OPENAI_API_KEY environment variable
- Install: pip install pig-agent-core pig-agent-tools[web]
"""

import asyncio
import os
import sys

from pig_agent_core import Agent
from pig_agent_core.tools.registry import ToolRegistry
from pig_agent_tools.web import HANDLERS, TOOL_SCHEMAS
from pig_llm import LLM


def setup_web_agent() -> Agent:
    """Create an agent with web search and webpage reading tools.

    Returns:
        Configured Agent instance with web tools
    """
    # Check for required API keys
    if not os.getenv("TAVILY_API_KEY"):
        print("Error: TAVILY_API_KEY environment variable not set")
        print("Get your key at: https://tavily.com")
        print("Set it with: export TAVILY_API_KEY='your-key-here'")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    # Create tool registry and register web tools
    registry = ToolRegistry()
    for schema in TOOL_SCHEMAS:
        tool_name = schema["function"]["name"]
        handler = HANDLERS.get(tool_name)
        if handler:
            registry.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=False,
                timeout=30.0,
            )

    print(f"Registered {len(HANDLERS)} web tools: {', '.join(HANDLERS.keys())}")

    # Create agent with web tools
    agent = Agent(
        name="WebAgent",
        llm=LLM(provider="openai", model="gpt-4"),
        system_prompt=(
            "You are a helpful assistant with web search and webpage reading capabilities. "
            "Use the 'search_web' tool to search for information on the internet. "
            "Use the 'read_webpage' tool to read and extract content from webpages."
        ),
        max_iterations=5,
        verbose=True,
    )

    # Assign the registry to the agent
    agent.registry = registry

    return agent


async def example_web_search():
    """Example 1: Search the web and summarize results"""
    print("\n" + "=" * 60)
    print("Example 1: Web Search")
    print("=" * 60)

    agent = setup_web_agent()

    try:
        # Ask agent to search for information
        print("\nUser: What are the latest developments in AI agents?")
        response = await agent.respond(
            "Search the web for the latest developments in AI agents "
            "and summarize the top 3 findings"
        )
        print(f"Agent: {response.content}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


async def example_read_webpage():
    """Example 2: Read and summarize a webpage"""
    print("\n" + "=" * 60)
    print("Example 2: Read Webpage")
    print("=" * 60)

    agent = setup_web_agent()

    try:
        # Ask agent to read a specific webpage
        print("\nUser: Read the Python.org homepage and tell me what it's about")
        response = await agent.respond(
            "Read the webpage at https://www.python.org and summarize what you find"
        )
        print(f"Agent: {response.content}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


async def example_search_and_read():
    """Example 3: Search and then read a webpage (streaming)"""
    print("\n" + "=" * 60)
    print("Example 3: Search and Read (Streaming)")
    print("=" * 60)

    agent = setup_web_agent()

    try:
        print("\nUser: Search for 'Python asyncio tutorial' and read the first result")
        print("Agent: ", end="", flush=True)

        # Stream the response
        async for chunk in agent.respond_stream(
            "Search for 'Python asyncio tutorial', then read the first result "
            "and give me a brief summary"
        ):
            if chunk.type == "text":
                # Print text chunks as they arrive
                print(chunk.content, end="", flush=True)
            elif chunk.type == "tool_call":
                # Show when tools are called
                print(f"\n[Tool call: {chunk.name}]", flush=True)
                print("Agent: ", end="", flush=True)

        print()  # New line at the end

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


async def example_error_handling():
    """Example 4: Error handling with invalid URL"""
    print("\n" + "=" * 60)
    print("Example 4: Error Handling")
    print("=" * 60)

    agent = setup_web_agent()

    try:
        # Try to read an invalid URL
        print("\nUser: Read the webpage at invalid-url")
        response = await agent.respond("Read the webpage at invalid-url")
        print(f"Agent: {response.content}")

    except Exception as e:
        print(f"Caught expected error: {type(e).__name__}: {e}")
        print("This demonstrates proper error handling")


async def main():
    """Run all examples"""
    print("=" * 60)
    print("pig-agent-tools Web Agent Demo")
    print("=" * 60)

    # Run examples
    await example_web_search()
    await example_read_webpage()
    await example_search_and_read()
    await example_error_handling()

    print("\n" + "=" * 60)
    print("Demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
