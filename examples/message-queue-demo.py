"""Message queue demonstration."""

from pig_agent_core import Agent, MessageQueue
from unittest.mock import Mock


def demo_message_queue():
    """Demonstrate message queue functionality."""
    
    print("=" * 60)
    print("Message Queue Demo")
    print("=" * 60)
    print()
    
    # Create queue
    queue = MessageQueue()
    
    print("1. Empty queue:")
    print(f"   {queue.get_status()}")
    print()
    
    # Add messages
    print("2. Adding messages:")
    queue.add_steering("Stop and explain what you're doing")
    print("   ✓ Added steering message")
    
    queue.add_followup("Now optimize the code")
    print("   ✓ Added follow-up message")
    
    queue.add_followup("Add tests")
    print("   ✓ Added another follow-up")
    
    print(f"\n   {queue.get_status()}")
    print()
    
    # Check queue
    print("3. Queue contents:")
    print(f"   Total: {len(queue)} messages")
    print(f"   Has steering: {queue.has_steering()}")
    print(f"   Has follow-up: {queue.has_followup()}")
    print()
    
    # Get steering messages
    print("4. Processing steering messages:")
    steering = queue.get_steering_messages()
    print(f"   Retrieved: {len(steering)} message(s)")
    for msg in steering:
        print(f"   • [{msg.type.value}] {msg.content}")
    
    print(f"\n   Remaining in queue: {len(queue)}")
    print()
    
    # Get follow-up messages
    print("5. Processing follow-up messages:")
    followup = queue.get_followup_messages()
    print(f"   Retrieved: {len(followup)} message(s)")
    for msg in followup:
        print(f"   • [{msg.type.value}] {msg.content}")
    
    print(f"\n   Remaining in queue: {len(queue)}")
    print()
    
    # Demo 'all' mode
    print("6. Testing 'all' mode:")
    queue.followup_mode = "all"
    
    queue.add_followup("F1")
    queue.add_followup("F2")
    queue.add_followup("F3")
    
    followup_all = queue.get_followup_messages()
    print(f"   Retrieved: {len(followup_all)} messages (all mode)")
    print()
    
    print("✓ Message queue demo complete!")
    print()
    print("In pig-code:")
    print("  While agent is working:")
    print("    !Stop and explain         → Steering (interrupts)")
    print("    >>Then add error handling → Follow-up (waits)")
    print()
    print("  /queue                      → Show queue status")


def demo_with_agent():
    """Demonstrate queue with agent."""
    
    print("\n" + "=" * 60)
    print("Message Queue with Agent")
    print("=" * 60)
    print()
    
    # Create mock agent
    mock_llm = Mock()
    mock_llm.config = Mock(model="test-model")
    
    agent = Agent(llm=mock_llm, name="QueueDemo", verbose=False)
    
    print("Agent created with message queue")
    print(f"Queue status: {agent.message_queue.get_status()}")
    print()
    
    # Queue some messages
    print("Queueing messages for later:")
    agent.message_queue.add_steering("Pause and explain")
    agent.message_queue.add_followup("Add documentation")
    
    print(f"  {agent.message_queue.get_status()}")
    print()
    
    # In real usage, these would be processed during agent.run()
    print("During agent.run():")
    print("  • Steering messages interrupt after tool execution")
    print("  • Follow-up messages execute after completion")
    print()
    
    print("✓ Agent queue demo complete!")


if __name__ == "__main__":
    demo_message_queue()
    demo_with_agent()
