"""Examples of custom extension implementations.

This module demonstrates how to implement custom protocols for:
- MemoryProvider: Custom conversation history storage
- BillingHook: Cost tracking and usage monitoring
- SystemPromptBuilder: Dynamic prompt construction
- ContextLoader: User context injection

Run with: python examples/custom_extensions.py
"""

import asyncio
import json
from typing import Any

from pig_agent_core import (
    Message,
)

# ============================================================================
# Custom MemoryProvider Example
# ============================================================================


class FileMemoryProvider:
    """Store conversation history in JSON files.

    This is a simple example showing how to implement MemoryProvider.
    In production, you might use Redis, PostgreSQL, or another database.
    """

    def __init__(self, storage_dir: str = "./memory"):
        """Initialize file-based memory provider.

        Args:
            storage_dir: Directory to store session files
        """
        self.storage_dir = storage_dir
        import os

        os.makedirs(storage_dir, exist_ok=True)

    def _get_filepath(self, session_id: str) -> str:
        """Get filepath for session."""
        return f"{self.storage_dir}/{session_id}.json"

    async def get_messages(self, session_id: str) -> list[Message]:
        """Load messages from file.

        Args:
            session_id: Session identifier

        Returns:
            List of messages for the session
        """
        filepath = self._get_filepath(session_id)
        try:
            with open(filepath) as f:
                data = json.load(f)
                return [Message(**msg) for msg in data]
        except FileNotFoundError:
            return []

    async def add_message(self, session_id: str, message: Message) -> None:
        """Save message to file.

        Args:
            session_id: Session identifier
            message: Message to add
        """
        messages = await self.get_messages(session_id)
        messages.append(message)

        filepath = self._get_filepath(session_id)
        with open(filepath, "w") as f:
            json.dump([msg.model_dump() for msg in messages], f, indent=2)

    async def clear_messages(self, session_id: str) -> None:
        """Clear session history.

        Args:
            session_id: Session identifier
        """
        filepath = self._get_filepath(session_id)
        try:
            import os

            os.remove(filepath)
        except FileNotFoundError:
            pass


# ============================================================================
# Custom BillingHook Example
# ============================================================================


class DetailedCostTracker:
    """Track costs with detailed breakdown by user and model.

    Implements BillingHook protocol for cost monitoring.
    """

    # Pricing per 1K tokens (example rates)
    PRICING = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
    }

    def __init__(self):
        """Initialize cost tracker."""
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.costs_by_user: dict[str, float] = {}
        self.costs_by_model: dict[str, float] = {}

    def on_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track LLM call and calculate cost.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            user_id: Optional user identifier
            metadata: Optional additional metadata
        """
        user_id = user_id or "default"

        # Calculate cost
        cost = 0.0
        if model in self.PRICING:
            pricing = self.PRICING[model]
            cost = (input_tokens / 1000 * pricing["input"]) + (
                output_tokens / 1000 * pricing["output"]
            )

        # Record call
        self.llm_calls.append(
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "user_id": user_id,
                "metadata": metadata or {},
            }
        )

        # Update totals
        self.costs_by_user[user_id] = self.costs_by_user.get(user_id, 0) + cost
        self.costs_by_model[model] = self.costs_by_model.get(model, 0) + cost

    def on_tool_call(
        self,
        tool_name: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Track tool usage.

        Args:
            tool_name: Name of the tool
            user_id: Optional user identifier
            metadata: Optional additional metadata
        """
        user_id = user_id or "default"

        self.tool_calls.append(
            {
                "tool_name": tool_name,
                "user_id": user_id,
                "metadata": metadata or {},
            }
        )

    def get_usage_summary(self, user_id: str | None = None) -> dict[str, Any]:
        """Get usage summary with cost breakdown.

        Args:
            user_id: Optional user to filter by

        Returns:
            Dictionary with usage statistics
        """
        if user_id:
            user_llm_calls = [c for c in self.llm_calls if c["user_id"] == user_id]
            user_tool_calls = [c for c in self.tool_calls if c["user_id"] == user_id]

            return {
                "user_id": user_id,
                "total_cost": self.costs_by_user.get(user_id, 0),
                "llm_calls": len(user_llm_calls),
                "tool_calls": len(user_tool_calls),
                "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in user_llm_calls),
            }

        return {
            "total_cost": sum(self.costs_by_user.values()),
            "total_llm_calls": len(self.llm_calls),
            "total_tool_calls": len(self.tool_calls),
            "costs_by_user": self.costs_by_user,
            "costs_by_model": self.costs_by_model,
            "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in self.llm_calls),
        }

    def print_summary(self) -> None:
        """Print formatted cost summary."""
        summary = self.get_usage_summary()

        print("\n" + "=" * 60)
        print("COST SUMMARY")
        print("=" * 60)
        print(f"Total Cost: ${summary['total_cost']:.4f}")
        print(f"Total LLM Calls: {summary['total_llm_calls']}")
        print(f"Total Tool Calls: {summary['total_tool_calls']}")
        print(f"Total Tokens: {summary['total_tokens']:,}")

        print("\nCosts by Model:")
        for model, cost in summary["costs_by_model"].items():
            print(f"  {model}: ${cost:.4f}")

        print("\nCosts by User:")
        for user, cost in summary["costs_by_user"].items():
            print(f"  {user}: ${cost:.4f}")
        print("=" * 60 + "\n")


# ============================================================================
# Custom SystemPromptBuilder Example
# ============================================================================


class PersonalizedPromptBuilder:
    """Build personalized system prompts based on user context.

    Implements SystemPromptBuilder protocol.
    """

    def build_prompt(self, base_prompt: str, context: dict[str, Any]) -> str:
        """Build personalized prompt with user context.

        Args:
            base_prompt: Base system prompt
            context: User context dictionary

        Returns:
            Personalized system prompt
        """
        # Extract context
        user_name = context.get("user_name", "User")
        language = context.get("language", "English")
        preferences = context.get("preferences", {})
        tone = preferences.get("tone", "professional")

        # Build personalized prompt
        prompt = f"""{base_prompt}

User Information:
- Name: {user_name}
- Preferred Language: {language}
- Communication Tone: {tone}

Instructions:
- Address the user by name when appropriate
- Respond in {language}
- Use a {tone} tone
"""

        # Add preference-specific instructions
        if preferences.get("concise"):
            prompt += "- Keep responses concise and to the point\n"

        if preferences.get("examples"):
            prompt += "- Provide examples when explaining concepts\n"

        return prompt


# ============================================================================
# Custom ContextLoader Example
# ============================================================================


class MockContextLoader:
    """Load user context from a mock database.

    Implements ContextLoader protocol.
    In production, this would query a real database.
    """

    def __init__(self):
        """Initialize with mock user data."""
        self.users = {
            "user123": {
                "user_name": "Alice",
                "language": "English",
                "preferences": {
                    "tone": "friendly",
                    "concise": True,
                    "examples": True,
                },
                "recent_topics": ["Python", "Machine Learning", "APIs"],
            },
            "user456": {
                "user_name": "Bob",
                "language": "Spanish",
                "preferences": {
                    "tone": "professional",
                    "concise": False,
                    "examples": False,
                },
                "recent_topics": ["JavaScript", "React", "Node.js"],
            },
        }

    async def load_context(self, user_id: str) -> dict[str, Any]:
        """Load user context.

        Args:
            user_id: User identifier

        Returns:
            User context dictionary
        """
        return self.users.get(
            user_id,
            {
                "user_name": "Guest",
                "language": "English",
                "preferences": {"tone": "professional"},
                "recent_topics": [],
            },
        )


# ============================================================================
# Example Usage
# ============================================================================


async def example_custom_memory():
    """Example: Using custom FileMemoryProvider."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Custom Memory Provider")
    print("=" * 60)

    # Create agent with file-based memory
    memory = FileMemoryProvider(storage_dir="./example_memory")

    print("\nUsing FileMemoryProvider to store conversation history")
    print("Messages will be saved to: ./example_memory/")

    # Simulate adding messages
    session_id = "session_001"
    await memory.add_message(session_id, Message(role="user", content="Hello, how are you?"))
    await memory.add_message(
        session_id, Message(role="assistant", content="I'm doing well, thank you!")
    )

    # Retrieve messages
    messages = await memory.get_messages(session_id)
    print(f"\nRetrieved {len(messages)} messages from storage:")
    for msg in messages:
        print(f"  {msg.role}: {msg.content}")

    print("\n✓ Custom memory provider working correctly")


async def example_billing_hook():
    """Example: Using DetailedCostTracker."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Billing Hook for Cost Tracking")
    print("=" * 60)

    tracker = DetailedCostTracker()

    # Simulate LLM calls
    print("\nSimulating LLM calls...")
    tracker.on_llm_call("gpt-4", input_tokens=1000, output_tokens=500, user_id="alice")
    tracker.on_llm_call("gpt-3.5-turbo", input_tokens=500, output_tokens=300, user_id="bob")
    tracker.on_llm_call("gpt-4", input_tokens=800, output_tokens=400, user_id="alice")

    # Simulate tool calls
    tracker.on_tool_call("search_web", user_id="alice")
    tracker.on_tool_call("read_file", user_id="bob")

    # Print summary
    tracker.print_summary()

    print("✓ Billing hook tracking costs correctly")


async def example_prompt_builder():
    """Example: Using PersonalizedPromptBuilder."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: System Prompt Builder")
    print("=" * 60)

    builder = PersonalizedPromptBuilder()
    context_loader = MockContextLoader()

    # Load context for user
    context = await context_loader.load_context("user123")

    # Build personalized prompt
    base_prompt = "You are a helpful AI assistant."
    personalized_prompt = builder.build_prompt(base_prompt, context)

    print("\nBase prompt:")
    print(f"  {base_prompt}")

    print("\nPersonalized prompt:")
    print(personalized_prompt)

    print("✓ Prompt builder personalizing correctly")


async def example_integrated_agent():
    """Example: Agent with all custom extensions."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Integrated Agent with Custom Extensions")
    print("=" * 60)

    # Note: This example shows the structure but won't actually run
    # without a real LLM API key

    print("\nCreating agent with custom extensions:")
    print("  - FileMemoryProvider for conversation storage")
    print("  - DetailedCostTracker for billing")
    print("  - PersonalizedPromptBuilder for dynamic prompts")
    print("  - MockContextLoader for user context")

    # Create custom components
    memory = FileMemoryProvider(storage_dir="./example_memory")
    tracker = DetailedCostTracker()
    prompt_builder = PersonalizedPromptBuilder()
    context_loader = MockContextLoader()

    print("\n✓ All custom extensions initialized")
    print("\nTo use with a real agent:")
    print("""
    agent = Agent(
        llm=LLM(provider="openai"),
        memory_provider=memory,
        billing_hook=tracker,
        system_prompt_builder=prompt_builder,
        system_prompt="You are a helpful AI assistant.",
    )

    # Load user context
    context = await context_loader.load_context("user123")

    # Run agent
    response = await agent.arun("Hello!")

    # Check costs
    tracker.print_summary()
    """)


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("CUSTOM EXTENSIONS EXAMPLES")
    print("=" * 60)

    await example_custom_memory()
    await example_billing_hook()
    await example_prompt_builder()
    await example_integrated_agent()

    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETED")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("1. MemoryProvider: Implement get_messages(), add_message(), clear_messages()")
    print("2. BillingHook: Implement on_llm_call(), on_tool_call(), get_usage_summary()")
    print("3. SystemPromptBuilder: Implement build_prompt() to customize system prompts")
    print("4. ContextLoader: Implement load_context() to inject user data")
    print("\nAll protocols use structural typing - no inheritance required!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
