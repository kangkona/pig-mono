"""Session management example."""

from pathlib import Path
from pig_agent_core import Session


def main():
    """Demonstrate session management features."""
    print("=== Session Management Example ===\n")

    # Create a session
    print("1. Creating session...")
    session = Session(name="demo-session", workspace="./workspace")

    # Add some messages
    print("2. Adding messages...")
    session.add_message("system", "You are a helpful assistant")
    session.add_message("user", "What is Python?")
    session.add_message("assistant", "Python is a programming language...")
    session.add_message("user", "Tell me more about its features")
    session.add_message("assistant", "Python has many features...")

    # Display current conversation
    print("\n3. Current conversation:")
    for entry in session.get_current_conversation():
        print(f"   [{entry.role}] {entry.content[:50]}...")

    # Branch to an earlier point
    print("\n4. Branching to earlier point...")
    conversation = session.get_current_conversation()
    branch_point = conversation[2]  # After first user message

    session.branch_to(branch_point.id)
    session.add_message("user", "Can you show me a code example?")
    session.add_message("assistant", "Sure! Here's an example...")

    print("   New conversation path:")
    for entry in session.get_current_conversation():
        print(f"   [{entry.role}] {entry.content[:50]}...")

    # Get session info
    print("\n5. Session info:")
    info = session.get_info()
    print(f"   ID: {info['id'][:8]}...")
    print(f"   Name: {info['name']}")
    print(f"   Total entries: {info['entries']}")
    print(f"   Current path: {info['current_path_length']} entries")
    print(f"   Branches: {info['branches']}")

    # Save session
    print("\n6. Saving session...")
    save_path = session.save()
    print(f"   Saved to: {save_path}")

    # Load session
    print("\n7. Loading session...")
    loaded = Session.load(save_path)
    print(f"   Loaded: {loaded.name}")
    print(f"   Entries: {len(loaded.tree.entries)}")

    # Fork session
    print("\n8. Forking session...")
    fork = session.fork(conversation[1].id, "demo-fork")
    print(f"   Fork created: {fork.name}")
    print(f"   Fork entries: {len(fork.tree.entries)}")

    # Compact session
    print("\n9. Testing compaction...")
    # Add more messages to make compaction meaningful
    for i in range(10):
        session.add_message("user", f"Question {i}")
        session.add_message("assistant", f"Answer {i}")

    compacted = session.compact("Summarize the technical discussion")
    print(f"   Compacted from {len(session.tree.entries)} entries")
    print(f"   Compacted path has {len(compacted)} entries")
    print(f"   First entry: {compacted[0].content[:100]}...")

    print("\n✓ Session management demo complete!")


if __name__ == "__main__":
    main()
