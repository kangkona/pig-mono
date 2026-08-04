"""Tests for messenger manager."""

import asyncio
from typing import Any, NoReturn

import pytest
from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerType,
    MessengerUser,
    WebhookRequest,
)
from pig_messenger.manager import (
    MessengerManager,
    _is_transient,
    _post_with_retry,
    split_message,
)
from pig_messenger.state import MessengerState


def test_split_message_short() -> None:
    """Test split_message with short text."""
    text = "Hello world"
    chunks = split_message(text, 100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_message_paragraph_boundary() -> None:
    """Test split_message at paragraph boundary."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = split_message(text, 30)
    assert len(chunks) == 3
    assert chunks[0] == "First paragraph.\n\n"
    assert chunks[1] == "Second paragraph.\n\n"
    assert chunks[2] == "Third paragraph."


def test_split_message_line_boundary() -> None:
    """Test split_message at line boundary."""
    text = "Line 1\nLine 2\nLine 3\nLine 4"
    chunks = split_message(text, 20)
    assert len(chunks) == 2
    assert chunks[0] == "Line 1\nLine 2\n"
    assert chunks[1] == "Line 3\nLine 4"


def test_split_message_sentence_boundary() -> None:
    """Test split_message at sentence boundary."""
    text = "First sentence. Second sentence. Third sentence."
    chunks = split_message(text, 30)
    assert len(chunks) == 2
    # Split happens at space after "Second" (position 23)
    assert chunks[0] == "First sentence. Second "
    assert chunks[1] == "sentence. Third sentence."


def test_split_message_word_boundary() -> None:
    """Test split_message at word boundary."""
    text = "word " * 20
    chunks = split_message(text, 30)
    assert all(len(chunk) <= 30 for chunk in chunks)
    assert "".join(chunks) == text


def test_is_transient_connection_error() -> None:
    """Test _is_transient with ConnectionError."""
    assert _is_transient(ConnectionError("Connection failed"))


def test_is_transient_timeout_error() -> None:
    """Test _is_transient with TimeoutError."""
    assert _is_transient(TimeoutError("Timeout"))


def test_is_transient_http_429() -> None:
    """Test _is_transient with HTTP 429."""
    assert _is_transient(Exception("HTTP 429 Too Many Requests"))


def test_is_transient_http_503() -> None:
    """Test _is_transient with HTTP 503."""
    assert _is_transient(Exception("503 Service Unavailable"))


def test_is_transient_non_transient() -> None:
    """Test _is_transient with non-transient error."""
    assert not _is_transient(ValueError("Invalid value"))


@pytest.mark.asyncio
async def test_post_with_retry_success() -> None:
    """Test _post_with_retry with immediate success."""
    call_count = 0

    async def fn() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    result = await _post_with_retry(fn)
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_post_with_retry_transient_then_success() -> None:
    """Test _post_with_retry with transient error then success."""
    call_count = 0

    async def fn() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Transient")
        return "success"

    result = await _post_with_retry(fn, base_delay=0.01)
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_post_with_retry_max_retries() -> None:
    """Test _post_with_retry exhausts retries."""
    call_count = 0

    async def fn() -> NoReturn:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Always fails")

    with pytest.raises(ConnectionError):
        await _post_with_retry(fn, max_retries=2, base_delay=0.01)

    assert call_count == 3  # Initial + 2 retries


class MockAdapter(BaseMessengerAdapter):
    """Mock messenger adapter."""

    def __init__(self) -> None:
        super().__init__(
            MessengerCapabilities(
                can_edit=False,
                can_delete=False,
                can_react=False,
                can_thread=False,
                can_upload_file=False,
                supports_blocks=False,
                supports_draft=False,
                max_message_length=1000,
            )
        )
        self.sent_messages: list[str] = []

    async def parse_event(self, raw_event: Any) -> Any:
        """Parse event."""
        return IncomingMessage(
            message_id=raw_event["id"],
            platform=MessengerType.TELEGRAM,
            channel_id=raw_event["channel"],
            text=raw_event["text"],
            user=MessengerUser(id="user1", username="testuser", display_name="Test User"),
            timestamp=0,
        )

    async def send_message(self, channel_id: Any, text: Any, **kwargs: Any) -> Any:
        """Send message."""
        self.sent_messages.append(text)
        return {"message_id": "msg123"}

    async def update_message(
        self, channel_id: Any, message_id: Any, text: Any, **kwargs: Any
    ) -> None:
        """Update a message."""
        return None

    async def verify_signature(self, request: WebhookRequest) -> bool:
        """Accept synthetic test webhooks."""
        return True

    async def aclose(self) -> None:
        """Close adapter."""
        pass


class MockState(MessengerState):
    """Mock messenger state."""

    def __init__(self) -> None:
        super().__init__()
        self.dedup_events: set[Any] = set()
        self.locks: dict[Any, Any] = {}
        self.followups: dict[Any, list[Any]] = {}

    async def check_event_dedup(self, event_id: Any) -> bool:
        """Check event dedup."""
        if event_id in self.dedup_events:
            return True
        self.dedup_events.add(event_id)
        return False

    async def acquire_agent_lock(self, key: Any) -> Any:
        """Acquire agent lock."""
        if key in self.locks:
            return None
        token = f"token-{key}"
        self.locks[key] = token
        return token

    async def release_agent_lock(self, key: Any, token: Any) -> bool:
        """Release agent lock."""
        if self.locks.get(key) == token:
            del self.locks[key]
            return True
        return False

    async def enqueue_followup(self, key: Any, data: Any) -> bool:
        """Enqueue follow-up."""
        if key not in self.followups:
            self.followups[key] = []
        self.followups[key].append(data)
        return True

    async def drain_followups(self, key: Any) -> Any:
        """Drain follow-ups."""
        items = self.followups.get(key, [])
        self.followups[key] = []
        return items

    async def release_lock_if_queue_empty(self, key: Any, token: Any) -> bool:
        """Release lock if queue empty."""
        if not self.followups.get(key):
            await self.release_agent_lock(key, token)
            return True
        return False

    async def record_dead_letter(self, data: Any) -> None:
        """Record dead letter."""
        pass

    async def list_dead_letters(self, count: int = 50) -> list[dict[str, object]]:
        """List dead letters."""
        return []

    async def replay_dead_letters(self, handler: Any) -> int:
        """Replay dead letters."""
        return 0


@pytest.mark.asyncio
async def test_manager_handle_event() -> None:
    """Test MessengerManager.handle_event."""
    adapter = MockAdapter()
    state = MockState()

    responses = []

    def agent_factory(message: Any, thread: Any) -> str:
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
async def test_manager_dedup() -> None:
    """Test MessengerManager event deduplication."""
    adapter = MockAdapter()
    state = MockState()

    call_count = 0

    def agent_factory(message: Any, thread: Any) -> str:
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
async def test_manager_shutdown() -> None:
    """Test MessengerManager.shutdown."""
    adapter = MockAdapter()

    def agent_factory(message: Any, thread: Any) -> str:
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
