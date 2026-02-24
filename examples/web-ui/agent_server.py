"""Web UI server with agent and tools."""

import os
from datetime import datetime
from pig_llm import LLM
from pig_agent_core import Agent, tool
from pig_web_ui import ChatServer


@tool(description="Get current time")
def get_time() -> str:
    """Get current time."""
    return datetime.now().strftime("%H:%M:%S")


@tool(description="Get current date")
def get_date() -> str:
    """Get current date."""
    return datetime.now().strftime("%Y-%m-%d")


@tool(description="Calculate mathematical expression")
def calculate(expression: str) -> str:
    """Calculate a math expression."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


def main():
    """Run web chat server with agent."""
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

    # Create agent with tools
    agent = Agent(
        name="TimeAgent",
        llm=llm,
        tools=[get_time, get_date, calculate],
        system_prompt="""You are a helpful assistant with access to time and calculation tools.
        
Use the tools when needed:
- get_time() for current time
- get_date() for current date
- calculate() for math expressions

Be helpful and friendly!""",
        verbose=True,  # Show tool calls in console
    )

    # Create server with agent
    server = ChatServer(
        agent=agent,
        title="Time & Math Assistant",
        port=8000,
        cors=True,
    )

    print("=" * 50)
    print("Agent Web UI Server")
    print("=" * 50)
    print(f"Model: {llm.config.model}")
    print(f"Tools: get_time, get_date, calculate")
    print(f"URL: http://localhost:8000")
    print()
    print("Try asking:")
    print("  - What time is it?")
    print("  - What's today's date?")
    print("  - Calculate 15 * 23 + 100")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)

    # Run server
    server.run()


if __name__ == "__main__":
    main()
