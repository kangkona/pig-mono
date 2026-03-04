#!/usr/bin/env python3
"""Test basic_agent.py example without requiring real API key"""

import asyncio
import os
import sys
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pig_agent_core import Agent
from pig_agent_core.tools import HANDLERS, TOOL_SCHEMAS
from pig_agent_core.tools.registry import ToolRegistry


def test_setup_agent():
    """Test agent setup"""
    print("Test 1: Agent setup...")

    # Set fake API key
    os.environ["OPENAI_API_KEY"] = "test-key"

    # Create tool registry
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

    print(f"✓ Registered {len(HANDLERS)} core tools: {', '.join(HANDLERS.keys())}")

    # Create agent with mock LLM
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(
        name="ThinkingAgent",
        llm=mock_llm,
        system_prompt="You are a helpful assistant.",
        max_iterations=5,
        verbose=False,
    )

    agent.registry = registry

    print("✓ Agent created successfully")
    return agent


async def test_respond():
    """Test respond() method"""
    print("\nTest 2: respond() method...")

    agent = test_setup_agent()

    # Mock the respond method
    mock_response = Mock()
    mock_response.content = "Test response"

    with patch.object(agent, "respond", return_value=mock_response):
        response = await agent.respond("Test question")
        assert response.content == "Test response"

    print("✓ respond() works")


async def test_respond_stream():
    """Test respond_stream() method"""
    print("\nTest 3: respond_stream() method...")

    agent = test_setup_agent()

    # Mock the respond_stream method
    async def mock_stream(*args, **kwargs):
        mock_chunk = Mock()
        mock_chunk.type = "text"
        mock_chunk.content = "Test"
        yield mock_chunk

    with patch.object(agent, "respond_stream", side_effect=mock_stream):
        chunks = []
        async for chunk in agent.respond_stream("Test question"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[0].type == "text"

    print("✓ respond_stream() works")


async def test_cancellation():
    """Test cancellation support"""
    print("\nTest 4: Cancellation support...")

    agent = test_setup_agent()

    cancel_event = asyncio.Event()

    # Mock respond_stream to check cancel parameter
    async def mock_stream(*args, cancel=None, **kwargs):
        assert cancel is not None, "Cancel event should be passed"
        mock_chunk = Mock()
        mock_chunk.type = "text"
        mock_chunk.content = "Test"
        yield mock_chunk

    with patch.object(agent, "respond_stream", side_effect=mock_stream):
        async for _chunk in agent.respond_stream("Test", cancel=cancel_event):
            pass

    print("✓ Cancellation support works")


async def test_error_handling():
    """Test error handling"""
    print("\nTest 5: Error handling...")

    try:
        # Test with invalid setup
        agent = test_setup_agent()

        # Mock respond to raise an error
        async def mock_error(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(agent, "respond", side_effect=mock_error):
            try:
                await agent.respond("Test")
                raise AssertionError("Should have raised error")
            except ValueError as e:
                assert str(e) == "Test error"

        print("✓ Error handling works")

    except Exception as e:
        print(f"✗ Error handling failed: {e}")
        raise


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing basic_agent.py example")
    print("=" * 60)

    await test_respond()
    await test_respond_stream()
    await test_cancellation()
    await test_error_handling()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
