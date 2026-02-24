"""Basic agent usage example."""

import os
from pig_llm import LLM
from pig_agent_core import Agent, tool


@tool(description="Get current weather for a location")
def get_weather(location: str) -> str:
    """Get weather information for a location."""
    # Simulated weather data
    weather_data = {
        "Paris": "Sunny, 72°F",
        "Tokyo": "Rainy, 65°F",
        "New York": "Cloudy, 68°F",
        "London": "Foggy, 55°F",
    }
    return weather_data.get(location, f"Weather data not available for {location}")


@tool(description="Calculate mathematical expression")
def calculate(expression: str) -> str:
    """Safely calculate a mathematical expression."""
    try:
        # Note: In production, use ast.literal_eval or a safe math parser
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error calculating: {e}"


def main():
    """Run basic agent example."""
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return

    # Create LLM
    llm = LLM(provider="openai", api_key=api_key, model="gpt-3.5-turbo")

    # Create agent with tools
    agent = Agent(
        name="WeatherBot",
        llm=llm,
        tools=[get_weather, calculate],
        system_prompt="You are a helpful weather assistant. Use tools to answer questions.",
        verbose=True,
    )

    print("=== Basic Agent Example ===\n")

    # Example 1: Simple weather query
    print("\n--- Example 1: Weather Query ---")
    response = agent.run("What's the weather in Paris?")
    print(f"\nFinal Answer: {response.content}\n")

    # Example 2: Calculation
    print("\n--- Example 2: Math Calculation ---")
    response = agent.run("What is 15 * 23 + 100?")
    print(f"\nFinal Answer: {response.content}\n")

    # Example 3: Combined query
    print("\n--- Example 3: Combined Query ---")
    response = agent.run("Is it warmer in Tokyo or London? Calculate the difference.")
    print(f"\nFinal Answer: {response.content}\n")

    # View conversation history
    print("\n--- Conversation History ---")
    for i, msg in enumerate(agent.history, 1):
        role = msg.role.upper()
        content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        print(f"{i}. {role}: {content}")


if __name__ == "__main__":
    main()
