"""Tests for messenger manager."""

import asyncio

import pytest
from pig_messenger.base import (
    IncomingMessage,
    MessengerCapabilities,
    MessengerType,
    MessengerUser,
)
from pig_messenger.manager import (
    MessengerManager,
    _is_transient,
    _post_with_retry,
    split_message,
)


def test_split_message_short():
    """Test split_message with short text."""
    text = "Hello world"
    chunks = split_message(text, 100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_message_paragraph_boundary():
    """Test split_message at paragraph boundary."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = split_message(text, 30)
    assert len(chunks) == 3
    assert chunks[0] == "First paragraph.\n\n"
    assert chunks[1] == "Second paragraph.\n\n"
    assert chunks[2] == "Third paragraph."


def test_split_message_line_boundary():
    """Test split_message at line boundary."""
    text = "Line 1\nLine 2\nLine 3\nLine 4"
    chunks = split_message(text, 20)
    assert len(chunks) == 2
    assert chunks[0] == "Line 1\nLine 2\n"
    assert chunks[1] == "Line 3\nLine 4"


def test_split_message_sentence_boundary():
    """Test split_message at sentence boundary."""
    text = "First sentence. Second sentence. Third sentence."
    chunks = split_message(text, 30)
    assert len(chunks) == 2
    # Split happens at space after "Second" (position 23)
    assert chunks[0] == "First sentence. Second "
    assert chunks[1] == "sentence. Third sentence."


def test_split_message_word_boundary():
    """Test split_message at word boundary."""
    text = "word " * 20
    chunks = split_message(text, 30)
    assert all(len(chunk) <= 30 for chunk in chunks)
    assert "".join(chunks) == text


def test_is_transient_connection_error():
    """Test _is_transient with ConnectionError."""
    assert _is_transient(ConnectionError("Connection failed"))


def test_is_transient_timeout_error():
    """Test _is_transient with TimeoutError."""
    assert _is_transient(TimeoutError("Timeout"))


def test_is_transient_http_429():
    """Test _is_transient with HTTP 429."""
    assert _is_transient(Exception("HTTP 429 Too Many Requests"))


def test_is_transient_http_503():
    """Test _is_transient with HTTP 503."""
    assert _is_transient(Exception("503 Service Unavailable"))


def test_is_transient_non_transient():
    """Test _is_transient with non-transient error."""
    assert not _is_transient(ValueError("Invalid value"))


@pytest.mark.asyncio
async def test_post_with_retry_success():
    """Test _post_with_retry with immediate success."""
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await _post_with_retry(fn)
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_post_with_retry_transient_then_success():
    """Test _post_with_retry with transient error then success."""
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Transient")
        return "success"

    result = await _post_with_retry(fn, base_delay=0.01)
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_post_with_retry_max_retries():
    """Test _post_with_retry exhausts retries."""
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Always fails")

    with pytest.raises(ConnectionError):
        await _post_with_retry(fn, max_retries=2, base_delay=0.01)

    assert call_count == 3  # Initial + 2 retries


class MockAdapter:
    """Mock messenger adapter."""

    def __init__(self):
        self.capabilities = MessengerCapabilities(
            can_edit=False,
            can_delete=False,
            can_react=False,
            can_thread=False,
            can_upload_file=False,
            supports_blocks=False,
            supports_draft=False,
            max_message_length=1000,
        )
        self.sent_messages = []

    async def parse_event(self, raw_event):
        """Parse event."""
        return IncomingMessage(
            message_id=raw_event["id"],
            platform=MessengerType.TELEGRAM,
            channel_id=raw_event["channel"],
            text=raw_event["text"],
            user=MessengerUser(id="user1", username="testuser", display_name="Test User"),
            timestamp=0,
        )

    async def send_message(self, channel_id, text, **kwargs):
        """Send message."""
        self.sent_messages.append(text)
        return {"message_id": "msg123"}

    async def aclose(self):
        """Close adapter."""
        pass


class MockState:
    """Mock messenger state."""

    def __init__(self):
        self.dedup_events = set()
        self.locks = {}
        self.followups = {}

    async def check_event_dedup(self, event_id):
        """Check event dedup."""
        if event_id in self.dedup_events:
            return True
        self.dedup_events.add(event_id)
        return False

    async def acquire_agent_lock(self, key):
        """Acquire agent lock."""
        if key in self.locks:
            return None
        token = f"token-{key}"
        self.locks[key] = token
        return token

    async def release_agent_lock(self, key, token):
        """Release agent lock."""
        if self.locks.get(key) == token:
            del self.locks[key]

    async def enqueue_followup(self, key, data):
        """Enqueue follow-up."""
        if key not in self.followups:
            self.followups[key] = []
        self.followups[key].append(data)

    async def drain_followups(self, key):
        """Drain follow-ups."""
        items = self.followups.get(key, [])
        self.followups[key] = []
        return items

    async def release_lock_if_queue_empty(self, key, token):
        """Release lock if queue empty."""
        if not self.followups.get(key):
            await self.release_agent_lock(key, token)
            return True
        return False

    async def record_dead_letter(self, data):
        """Record dead letter."""
        pass

    async def list_dead_letters(self, count):
        """List dead letters."""
        return []

    async def replay_dead_letters(self, handler):
        """Replay dead letters."""
        return 0


@pytest.mark.asyncio
async def test_manager_handle_event():
    """Test MessengerManager.handle_event."""
    adapter = MockAdapter()
    state = MockState()

    responses = []

    def agent_factory(message, thread):
        responses.append(message.text)
        return "Response"

    manager = MessengerManager(agent_factory=agent_factory, state=state)

    # Handle event
    await manager.handle_event(
        MessengerType.TELEGRAM,
        {"id": "evt1", "channel": "ch1", "text": "Hello"},
        adapter=adapter,
    )

    # Wait for background task
    await asyncio.sleep(0.1)

    assert "Hello" in responses
    assert "Response" in adapter.sent_messages


@pytest.mark.asyncio
async def test_manager_dedup():
    """Test MessengerManager event deduplication."""
    adapter = MockAdapter()
    state = MockState()

    call_count = 0

    def agent_factory(message, thread):
        nonlocal call_count
        call_count += 1
        return "Response"

    manager = MessengerManager(agent_factory=agent_factory, state=state)

    # Handle same event twice
    event = {"id": "evt1", "channel": "ch1", "text": "Hello"}
    await manager.handle_event(MessengerType.TELEGRAM, event, adapter=adapter)
    await manager.handle_event(MessengerType.TELEGRAM, event, adapter=adapter)

    await asyncio.sleep(0.1)

    # Agent should only be called once
    assert call_count == 1


@pytest.mark.asyncio
async def test_manager_shutdown():
    """Test MessengerManager.shutdown."""
    adapter = MockAdapter()

    def agent_factory(message, thread):
        return "Response"

    manager = MessengerManager(agent_factory=agent_factory)

    await manager.handle_event(
        MessengerType.TELEGRAM,
        {"id": "evt1", "channel": "ch1", "text": "Hello"},
        adapter=adapter,
    )

    # Shutdown
    await manager.shutdown()

    # Background tasks should be complete
    assert len(manager._background_tasks) == 0
