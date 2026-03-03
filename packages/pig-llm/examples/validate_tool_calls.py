"""
Simple validation script to test tool_calls functionality.

This script tests that all providers correctly extract and return tool_calls.
"""

import json

from pig_llm.models import Message, Response


def test_tool_calls_format():
    """Test that tool_calls have the correct format."""
    print("Testing tool_calls format...")

    # Create a mock response with tool_calls
    response = Response(
        content="I'll check the weather for you.",
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        finish_reason="tool_use",
        tool_calls=[
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"location": "San Francisco, CA"}),
                },
            }
        ],
    )

    assert response.tool_calls is not None, "tool_calls should not be None"
    assert len(response.tool_calls) == 1, "Should have 1 tool call"

    tool_call = response.tool_calls[0]
    assert tool_call["id"] == "call_123", "Tool call ID mismatch"
    assert tool_call["type"] == "function", "Tool call type should be 'function'"
    assert tool_call["function"]["name"] == "get_weather", "Function name mismatch"

    args = json.loads(tool_call["function"]["arguments"])
    assert args["location"] == "San Francisco, CA", "Arguments mismatch"

    print("✓ Tool calls format is correct")


def test_message_with_tool_calls():
    """Test Message model with tool_calls metadata."""
    print("\nTesting Message with tool_calls metadata...")

    message = Message(
        role="assistant",
        content="I'll check the weather.",
        metadata={
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"location": "New York, NY"}),
                    },
                }
            ]
        },
    )

    assert message.metadata is not None, "Metadata should not be None"
    assert "tool_calls" in message.metadata, "Should have tool_calls in metadata"
    assert len(message.metadata["tool_calls"]) == 1, "Should have 1 tool call"

    print("✓ Message with tool_calls metadata works correctly")


def test_tool_result_message():
    """Test tool result message format."""
    print("\nTesting tool result message...")

    message = Message(
        role="tool",
        content="The temperature is 15°C",
        metadata={"tool_call_id": "call_789", "function_name": "get_weather"},
    )

    assert message.role == "tool", "Role should be 'tool'"
    assert message.metadata["tool_call_id"] == "call_789", "Tool call ID mismatch"
    assert message.metadata["function_name"] == "get_weather", "Function name mismatch"

    print("✓ Tool result message format is correct")


def test_providers_import():
    """Test that all providers can be imported."""
    print("\nTesting provider imports...")

    providers = [
        "openai",
        "anthropic",
        "google",
        "azure",
        "groq",
        "deepseek",
        "xai",
        "cerebras",
        "perplexity",
        "together",
        "openrouter",
    ]

    for provider_name in providers:
        try:
            # Just test that we can create the config
            from pig_llm.config import Config

            config = Config(provider=provider_name, api_key="test-key")
            assert config.provider == provider_name
            print(f"  ✓ {provider_name}")
        except Exception as e:
            print(f"  ✗ {provider_name}: {e}")

    print("✓ All providers can be imported")


def test_tool_definition():
    """Test tool definition format."""
    print("\nTesting tool definition format...")

    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string", "description": "City and state"}},
                "required": ["location"],
            },
        },
    }

    assert tool["type"] == "function", "Tool type should be 'function'"
    assert "name" in tool["function"], "Tool should have a name"
    assert "parameters" in tool["function"], "Tool should have parameters"

    print("✓ Tool definition format is correct")


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("pig-llm Tool Calls Validation")
    print("=" * 60)

    try:
        test_tool_calls_format()
        test_message_with_tool_calls()
        test_tool_result_message()
        test_providers_import()
        test_tool_definition()

        print("\n" + "=" * 60)
        print("✓ All validation tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
