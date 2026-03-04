#!/usr/bin/env python3
"""Basic Agent Demo

This example demonstrates the core features of pig-agent-core:
- Creating an agent with tools
- Using respond() for non-streaming responses
- Using respond_stream() for streaming responses
- Error handling

Requirements:
- Set OPENAI_API_KEY environment variable
- Install: pip install pig-agent-core
"""

import asyncio
import os
import sys

from pig_agent_core import Agent
from pig_agent_core.tools import HANDLERS, TOOL_SCHEMAS
from pig_agent_core.tools.registry import ToolRegistry
from pig_llm import LLM


def setup_agent() -> Agent:
    """Create an agent with think and plan tools.

    Returns:
        Configured Agent instance
    """
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    # Create tool registry and register core tools
    registry = ToolRegistry()
    for schema in TOOL_SCHEMAS:
        tool_name = schema["function"]["name"]
        handler = HANDLERS.get(tool_name)
        if handler:
            registry.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=True,
                timeout=30.0,
            )

    print(f"Registered {len(HANDLERS)} core tools: {', '.join(HANDLERS.keys())}")

    # Create agent
    agent = Agent(
        name="ThinkingAgent",
        llm=LLM(provider="openai", model="gpt-4"),
        system_prompt=(
            "You are a helpful assistant with reasoning capabilities. "
            "Use the 'think' tool to reason through complex problems. "
            "Use the 'plan' tool to create structured plans."
        ),
        max_iterations=5,
        verbose=True,
    )

    # Assign the registry to the agent
    agent.registry = registry

    return agent


async def example_respond():
    """Example 1: Non-streaming response with respond()"""
    print("\n" + "=" * 60)
    print("Example 1: Non-streaming response")
    print("=" * 60)

    agent = setup_agent()

    try:
        # Simple question
        print("\nUser: What is 2 + 2?")
        response = await agent.respond("What is 2 + 2?")
        print(f"Agent: {response.content}")

        # Question that might trigger thinking
        print("\nUser: Help me plan a weekend project to build a bookshelf")
        response = await agent.respond("Help me plan a weekend project to build a bookshelf")
        print(f"Agent: {response.content}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


async def example_respond_stream():
    """Example 2: Streaming response with respond_stream()"""
    print("\n" + "=" * 60)
    print("Example 2: Streaming response")
    print("=" * 60)

    agent = setup_agent()

    try:
        print("\nUser: Tell me a short story about a robot learning to paint")
        print("Agent: ", end="", flush=True)

        # Stream the response
        async for chunk in agent.respond_stream(
            "Tell me a short story about a robot learning to paint"
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


async def example_with_cancellation():
    """Example 3: Cancellation support"""
    print("\n" + "=" * 60)
    print("Example 3: Cancellation support")
    print("=" * 60)

    agent = setup_agent()

    try:
        # Create a cancellation event
        cancel_event = asyncio.Event()

        # Start a task that will be cancelled
        async def run_with_timeout():
            try:
                print("\nUser: Write a very long essay about the history of computing")
                print("Agent: ", end="", flush=True)

                async for chunk in agent.respond_stream(
                    "Write a very long essay about the history of computing",
                    cancel=cancel_event,
                ):
                    if chunk.type == "text":
                        print(chunk.content, end="", flush=True)

                print()
            except asyncio.CancelledError:
                print("\n[Response cancelled]")
                raise

        # Run with a timeout
        task = asyncio.create_task(run_with_timeout())

        # Cancel after 3 seconds
        await asyncio.sleep(3)
        cancel_event.set()
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            print("Task was cancelled successfully")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


async def example_error_handling():
    """Example 4: Error handling"""
    print("\n" + "=" * 60)
    print("Example 4: Error handling")
    print("=" * 60)

    # Create agent with invalid API key to demonstrate error handling
    try:
        # Save original key
        original_key = os.environ.get("OPENAI_API_KEY")

        # Set invalid key
        os.environ["OPENAI_API_KEY"] = "invalid-key"

        agent = setup_agent()

        print("\nAttempting to use agent with invalid API key...")
        response = await agent.respond("Hello")
        print(f"Response: {response.content}")

    except Exception as e:
        print(f"Caught expected error: {type(e).__name__}: {e}")
        print("This demonstrates proper error handling")

    finally:
        # Restore original key
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key


async def main():
    """Run all examples"""
    print("=" * 60)
    print("pig-agent-core Basic Agent Demo")
    print("=" * 60)

    # Run examples
    await example_respond()
    await example_respond_stream()
    await example_with_cancellation()
    await example_error_handling()

    print("\n" + "=" * 60)
    print("Demo completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
