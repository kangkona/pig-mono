"""Extension system example."""

from pig_agent_core import Agent, ExtensionAPI, ExtensionManager
from pig_llm import LLM
from unittest.mock import Mock


# Example extension
def demo_extension(api: ExtensionAPI):
    """Demo extension showing all features."""

    # Register a custom tool
    @api.tool(description="Calculate factorial")
    def factorial(n: int) -> int:
        """Calculate factorial of n."""
        if n <= 1:
            return 1
        return n * factorial(n - 1)

    # Register a command
    @api.command("stats", "Show session statistics")
    def show_stats():
        """Show statistics."""
        return f"Agent has {len(api.agent.registry)} tools"

    # Register event handlers
    @api.on("tool_call_start")
    def on_tool_start(event, context):
        """Handle tool call start."""
        print(f"🔧 Tool starting: {event.get('tool_name')}")

    @api.on("tool_call_end")
    def on_tool_end(event, context):
        """Handle tool call end."""
        print(f"✓ Tool finished: {event.get('tool_name')}")

    print("✓ Demo extension loaded!")


def main():
    """Demonstrate extension system."""
    print("=== Extension System Example ===\n")

    # Create agent with mock LLM
    print("1. Creating agent...")
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    agent = Agent(llm=mock_llm, name="ExtensionAgent")

    # Create extension manager
    print("2. Creating extension manager...")
    ext_manager = ExtensionManager(agent)

    # Load extension (simulated - normally from file)
    print("3. Loading demo extension...")
    demo_extension(ext_manager.api)

    # Show loaded tools
    print("\n4. Loaded tools:")
    for tool in agent.registry.list_tools():
        print(f"   - {tool.name}: {tool.description}")

    # Test custom command
    print("\n5. Testing custom command:")
    result = ext_manager.handle_command("stats")
    print(f"   {result}")

    # Test event emission
    print("\n6. Testing event system:")
    ext_manager.emit_event(
        "tool_call_start", {"tool_name": "factorial", "args": {"n": 5}}
    )
    ext_manager.emit_event("tool_call_end", {"tool_name": "factorial", "result": 120})

    # Test tool execution
    print("\n7. Testing custom tool:")
    result = agent.registry.execute("factorial", n=5)
    print(f"   factorial(5) = {result}")

    print("\n✓ Extension system demo complete!")


if __name__ == "__main__":
    main()
