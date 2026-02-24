"""Tests for message queue."""

import pytest
from pig_agent_core.message_queue import MessageQueue, MessageType, QueuedMessage


def test_message_queue_creation():
    """Test creating message queue."""
    queue = MessageQueue()
    assert len(queue) == 0
    assert not queue


def test_queue_add_steering():
    """Test adding steering message."""
    queue = MessageQueue()
    
    queue.add_steering("Interrupt now")
    
    assert len(queue) == 1
    assert queue.has_steering()
    assert not queue.has_followup()


def test_queue_add_followup():
    """Test adding follow-up message."""
    queue = MessageQueue()
    
    queue.add_followup("After completion")
    
    assert len(queue) == 1
    assert queue.has_followup()
    assert not queue.has_steering()


def test_queue_get_steering():
    """Test getting steering messages."""
    queue = MessageQueue()
    
    queue.add_steering("Steering 1")
    queue.add_steering("Steering 2")
    queue.add_followup("Follow-up")
    
    steering = queue.get_steering_messages()
    
    # Should get steering messages (one at a time mode)
    assert len(steering) == 1
    assert steering[0].content == "Steering 1"
    
    # Steering removed, followup remains
    assert len(queue) == 1
    assert not queue.has_steering()


def test_queue_get_followup():
    """Test getting follow-up messages."""
    queue = MessageQueue()
    
    queue.add_followup("Followup 1")
    queue.add_followup("Followup 2")
    queue.add_steering("Steering")
    
    followup = queue.get_followup_messages()
    
    # Should get one follow-up
    assert len(followup) == 1
    assert followup[0].content == "Followup 1"
    
    # Followup removed, steering remains
    assert len(queue) == 1
    assert queue.has_steering()


def test_queue_mode_all():
    """Test queue with 'all' mode."""
    queue = MessageQueue()
    queue.steering_mode = "all"
    
    queue.add_steering("S1")
    queue.add_steering("S2")
    queue.add_steering("S3")
    
    steering = queue.get_steering_messages()
    
    # Should get all steering messages
    assert len(steering) == 3


def test_queue_peek():
    """Test peeking at queue."""
    queue = MessageQueue()
    
    queue.add_steering("First")
    queue.add_followup("Second")
    
    # Peek doesn't remove
    peeked = queue.peek()
    assert peeked.content == "First"
    assert len(queue) == 2


def test_queue_clear():
    """Test clearing queue."""
    queue = MessageQueue()
    
    queue.add_steering("S1")
    queue.add_followup("F1")
    
    assert len(queue) == 2
    
    cleared = queue.clear()
    
    assert len(cleared) == 2
    assert len(queue) == 0


def test_queue_status():
    """Test queue status string."""
    queue = MessageQueue()
    
    # Empty
    status = queue.get_status()
    assert "empty" in status.lower()
    
    # With messages
    queue.add_steering("S")
    queue.add_followup("F")
    
    status = queue.get_status()
    assert "steering" in status
    assert "follow-up" in status


def test_queued_message_type():
    """Test queued message type."""
    msg = QueuedMessage(content="Test", type=MessageType.STEERING)
    assert msg.type == MessageType.STEERING
    
    msg2 = QueuedMessage(content="Test")
    assert msg2.type == MessageType.FOLLOWUP  # Default


def test_queue_bool():
    """Test queue boolean value."""
    queue = MessageQueue()
    
    assert not queue
    
    queue.add_steering("Message")
    
    assert queue
    assert bool(queue) is True


def test_queue_len():
    """Test queue length."""
    queue = MessageQueue()
    
    assert len(queue) == 0
    
    queue.add_steering("S1")
    assert len(queue) == 1
    
    queue.add_followup("F1")
    assert len(queue) == 2
    
    queue.get_steering_messages()
    assert len(queue) == 1


def test_queue_has_methods():
    """Test has_steering and has_followup."""
    queue = MessageQueue()
    
    assert not queue.has_steering()
    assert not queue.has_followup()
    
    queue.add_steering("S")
    assert queue.has_steering()
    assert not queue.has_followup()
    
    queue.add_followup("F")
    assert queue.has_steering()
    assert queue.has_followup()
