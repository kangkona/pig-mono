"""
Tool Calling Examples for pig-llm

This file demonstrates how to use tool calling with different providers.
"""

import json

from pig_llm import LLM


# Define a sample tool
def get_weather_tool():
    """Returns a weather tool definition in OpenAI format."""
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The unit of temperature",
                    },
                },
                "required": ["location"],
            },
        },
    }


def simulate_weather_api(location: str, unit: str = "celsius") -> str:
    """Simulates a weather API call."""
    # In a real application, this would call an actual weather API
    weather_data = {
        "San Francisco, CA": {"celsius": "15°C", "fahrenheit": "59°F"},
        "New York, NY": {"celsius": "8°C", "fahrenheit": "46°F"},
        "London, UK": {"celsius": "12°C", "fahrenheit": "54°F"},
    }

    temp = weather_data.get(location, {}).get(unit, "Unknown")
    return f"The current temperature in {location} is {temp}"


# Example 1: OpenAI Provider
def example_openai():
    """Example using OpenAI provider with tool calling."""
    print("\n=== OpenAI Tool Calling Example ===\n")

    # Initialize LLM
    llm = LLM(
        provider="openai",
        api_key="your-openai-api-key",  # Replace with your API key
        model="gpt-4",
    )

    # First request with tools
    response = llm.complete("What's the weather like in San Francisco?", tools=[get_weather_tool()])

    print(f"Response: {response.content}")
    print(f"Finish reason: {response.finish_reason}")

    # Check if Claude wants to use a tool
    if response.tool_calls:
        print(f"\nTool calls detected: {len(response.tool_calls)}")

        for tool_call in response.tool_calls:
            print(f"\nTool: {tool_call['function']['name']}")
            print(f"Arguments: {tool_call['function']['arguments']}")

            # Parse arguments and call the function
            args = json.loads(tool_call["function"]["arguments"])
            result = simulate_weather_api(**args)
            print(f"Result: {result}")


# Example 2: Anthropic Provider
def example_anthropic():
    """Example using Anthropic provider with tool calling."""
    print("\n=== Anthropic Tool Calling Example ===\n")

    # Initialize LLM
    llm = LLM(
        provider="anthropic",
        api_key="your-anthropic-api-key",  # Replace with your API key
        model="claude-opus-4-6",
    )

    # First request with tools
    response = llm.complete("What's the weather like in New York?", tools=[get_weather_tool()])

    print(f"Response: {response.content}")
    print(f"Finish reason: {response.finish_reason}")

    # Check if Claude wants to use a tool
    if response.tool_calls:
        print(f"\nTool calls detected: {len(response.tool_calls)}")

        for tool_call in response.tool_calls:
            print(f"\nTool: {tool_call['function']['name']}")
            print(f"Arguments: {tool_call['function']['arguments']}")

            # Parse arguments and call the function
            args = json.loads(tool_call["function"]["arguments"])
            result = simulate_weather_api(**args)
            print(f"Result: {result}")


# Example 3: Google Gemini Provider
def example_google():
    """Example using Google Gemini provider with tool calling."""
    print("\n=== Google Gemini Tool Calling Example ===\n")

    # Initialize LLM
    llm = LLM(
        provider="google",
        api_key="your-google-api-key",  # Replace with your API key
        model="gemini-2.0-flash-exp",
    )

    # First request with tools
    response = llm.complete("What's the weather like in London?", tools=[get_weather_tool()])

    print(f"Response: {response.content}")
    print(f"Finish reason: {response.finish_reason}")

    # Check if Gemini wants to use a tool
    if response.tool_calls:
        print(f"\nTool calls detected: {len(response.tool_calls)}")

        for tool_call in response.tool_calls:
            print(f"\nTool: {tool_call['function']['name']}")
            print(f"Arguments: {tool_call['function']['arguments']}")

            # Parse arguments and call the function
            args = json.loads(tool_call["function"]["arguments"])
            result = simulate_weather_api(**args)
            print(f"Result: {result}")


# Example 4: Multiple Tools
def example_multiple_tools():
    """Example with multiple tools."""
    print("\n=== Multiple Tools Example ===\n")

    # Define multiple tools
    tools = [
        get_weather_tool(),
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get the current time in a given timezone",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "The IANA timezone name, e.g. America/Los_Angeles",
                        }
                    },
                    "required": ["timezone"],
                },
            },
        },
    ]

    llm = LLM(provider="openai", api_key="your-openai-api-key", model="gpt-4")

    response = llm.complete("What's the weather and time in San Francisco?", tools=tools)

    print(f"Response: {response.content}")

    if response.tool_calls:
        print(f"\nTool calls: {len(response.tool_calls)}")
        for tc in response.tool_calls:
            print(f"  - {tc['function']['name']}")


# Example 5: Custom Provider (OpenAI-compatible)
def example_custom_provider():
    """Example using a custom OpenAI-compatible provider."""
    print("\n=== Custom Provider Example ===\n")

    # Any OpenAI-compatible API
    llm = LLM(
        provider="my-custom-llm",  # Any name
        api_key="your-api-key",
        base_url="https://api.your-provider.com/v1",  # Custom base URL
        model="your-model-name",
    )

    response = llm.complete("What's the weather in Tokyo?", tools=[get_weather_tool()])

    print(f"Response: {response.content}")

    if response.tool_calls:
        print(f"Tool calls: {len(response.tool_calls)}")


# Example 6: Checking Tool Call Details
def example_tool_call_details():
    """Example showing how to inspect tool call details."""
    print("\n=== Tool Call Details Example ===\n")

    llm = LLM(provider="anthropic", api_key="your-key", model="claude-opus-4-6")

    response = llm.complete("What's the weather in Paris?", tools=[get_weather_tool()])

    if response.tool_calls:
        for tool_call in response.tool_calls:
            print(f"Tool Call ID: {tool_call['id']}")
            print(f"Type: {tool_call['type']}")
            print(f"Function Name: {tool_call['function']['name']}")
            print(f"Arguments (JSON): {tool_call['function']['arguments']}")

            # Parse arguments
            args = json.loads(tool_call["function"]["arguments"])
            print(f"Parsed Arguments: {args}")

            # For Anthropic, you can check the caller type
            if "caller" in tool_call:
                print(f"Caller: {tool_call['caller']}")


if __name__ == "__main__":
    print("=" * 60)
    print("pig-llm Tool Calling Examples")
    print("=" * 60)

    print("\nNote: Replace API keys with your actual keys to run these examples.")
    print("\nSupported providers with tool calling:")
    print("  ✓ OpenAI")
    print("  ✓ Azure OpenAI")
    print("  ✓ Anthropic (Claude)")
    print("  ✓ Google (Gemini)")
    print("  ✓ OpenRouter")
    print("  ✓ DeepSeek")
    print("  ✓ Groq")
    print("  ✓ xAI (Grok)")
    print("  ✓ Cerebras")
    print("  ✓ Perplexity")
    print("  ✓ Together AI")
    print("  ✓ Custom OpenAI-compatible providers")

    # Uncomment to run examples (requires API keys)
    # example_openai()
    # example_anthropic()
    # example_google()
    # example_multiple_tools()
    # example_custom_provider()
    # example_tool_call_details()
