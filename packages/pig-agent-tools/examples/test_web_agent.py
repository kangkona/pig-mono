#!/usr/bin/env python3
"""Test web_agent.py example without requiring real API keys"""

import asyncio
import os
import sys
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pig_agent_core import Agent
from pig_agent_core.tools.registry import ToolRegistry
from pig_agent_tools.web import HANDLERS, TOOL_SCHEMAS


def test_setup_agent():
    """Test agent setup with web tools"""
    print("Test 1: Agent setup with web tools...")

    # Set fake API keys
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["TAVILY_API_KEY"] = "test-key"

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
                is_core=False,
                timeout=30.0,
            )

    print(f"✓ Registered {len(HANDLERS)} web tools: {', '.join(HANDLERS.keys())}")

    # Create agent with mock LLM
    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(
        name="WebAgent",
        llm=mock_llm,
        system_prompt="You are a helpful assistant with web capabilities.",
        max_iterations=5,
        verbose=False,
    )

    agent.registry = registry

    print("✓ Agent created successfully with web tools")
    return agent


async def test_web_search():
    """Test web search functionality"""
    print("\nTest 2: Web search...")

    agent = test_setup_agent()

    # Mock the respond method
    mock_response = Mock()
    mock_response.content = "Found 3 results about AI agents"

    with patch.object(agent, "respond", return_value=mock_response):
        response = await agent.respond("Search for AI agents")
        assert response.content == "Found 3 results about AI agents"

    print("✓ Web search works")


async def test_read_webpage():
    """Test webpage reading functionality"""
    print("\nTest 3: Read webpage...")

    agent = test_setup_agent()

    # Mock the respond method
    mock_response = Mock()
    mock_response.content = "Python is a programming language"

    with patch.object(agent, "respond", return_value=mock_response):
        response = await agent.respond("Read https://www.python.org")
        assert "Python" in response.content

    print("✓ Read webpage works")


async def test_streaming():
    """Test streaming with web tools"""
    print("\nTest 4: Streaming with web tools...")

    agent = test_setup_agent()

    # Mock the respond_stream method
    async def mock_stream(*args, **kwargs):
        # Simulate tool call
        mock_tool_chunk = Mock()
        mock_tool_chunk.type = "tool_call"
        mock_tool_chunk.name = "search_web"
        yield mock_tool_chunk

        # Simulate text response
        mock_text_chunk = Mock()
        mock_text_chunk.type = "text"
        mock_text_chunk.content = "Search results"
        yield mock_text_chunk

    with patch.object(agent, "respond_stream", side_effect=mock_stream):
        chunks = []
        async for chunk in agent.respond_stream("Search and summarize"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].type == "tool_call"
        assert chunks[1].type == "text"

    print("✓ Streaming with web tools works")


async def test_error_handling():
    """Test error handling"""
    print("\nTest 5: Error handling...")

    try:
        agent = test_setup_agent()

        # Mock respond to raise an error
        async def mock_error(*args, **kwargs):
            raise ValueError("Invalid URL")

        with patch.object(agent, "respond", side_effect=mock_error):
            try:
                await agent.respond("Read invalid-url")
                raise AssertionError("Should have raised error")
            except ValueError as e:
                assert str(e) == "Invalid URL"

        print("✓ Error handling works")

    except Exception as e:
        print(f"✗ Error handling failed: {e}")
        raise


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing web_agent.py example")
    print("=" * 60)

    await test_web_search()
    await test_read_webpage()
    await test_streaming()
    await test_error_handling()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
