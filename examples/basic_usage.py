"""Basic usage example for py-ai."""

import os
from pig_llm import LLM

def main():
    """Run basic examples."""
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return

    # Initialize LLM
    llm = LLM(provider="openai", api_key=api_key)

    # Simple completion
    print("=== Simple Completion ===")
    response = llm.complete("What is Python?")
    print(response.content)
    print(f"\nTokens used: {response.usage['total_tokens']}")

    # With system message
    print("\n=== With System Message ===")
    response = llm.complete(
        "Translate 'Hello, world!' to Spanish",
        system="You are a helpful translator",
    )
    print(response.content)

    # Streaming
    print("\n=== Streaming ===")
    for chunk in llm.stream("Count from 1 to 5"):
        print(chunk.content, end="", flush=True)
    print()

if __name__ == "__main__":
    main()
