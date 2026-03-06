"""Tests for messenger distributed state."""

import pytest
from pig_messenger.state import MessengerState


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    async def expire(self, key, seconds):
        if key in self.data:
            self.ttls[key] = seconds
            return 1
        return 0

    async def lpush(self, key, *values):
        if key not in self.data:
            self.data[key] = []
        for value in values:
            self.data[key].insert(0, value)
        return len(self.data[key])

    async def rpush(self, key, *values):
        if key not in self.data:
            self.data[key] = []
        self.data[key].extend(values)
        return len(self.data[key])

    async def llen(self, key):
        return len(self.data.get(key, []))

    async def lrange(self, key, start, stop):
        data = self.data.get(key, [])
        if stop == -1:
            return data[start:]
        return data[start : stop + 1]

    async def ltrim(self, key, start, stop):
        if key in self.data:
            self.data[key] = self.data[key][start : stop + 1]
        return True

    async def eval(self, script, num_keys, *args):
        """Mock eval for Lua scripts."""
        # Simple mock - just execute the logic
        keys = args[:num_keys]
        argv = args[num_keys:]

        # Check-and-delete pattern (release lock)
        if "get" in script and "del" in script and "llen" not in script:
            key = keys[0]
            token = argv[0]
            if self.data.get(key) == token:
                await self.delete(key)
                return 1
            return 0

        # Check-and-expire pattern (renew lock)
        if "get" in script and "expire" in script:
            key = keys[0]
            token = argv[0]
            ttl = int(argv[1])
            if self.data.get(key) == token:
                self.ttls[key] = ttl
                return 1
            return 0

        # Check-queue-and-release pattern
        if "llen" in script:
            lock_key = keys[0]
            queue_key = keys[1]
            token = argv[0]
            if self.data.get(lock_key) == token:
                queue_len = await self.llen(queue_key)
                if queue_len == 0:
                    await self.delete(lock_key)
                    return 1
                else:
                    return 0
            return 0

        # Drain queue pattern
        if "lrange" in script:
            key = keys[0]
            messages = self.data.get(key, [])
            if key in self.data:
                del self.data[key]
            return messages

        return 0


@pytest.mark.asyncio
async def test_check_event_dedup():
    """Test event deduplication."""
    redis = MockRedis()
    state = MessengerState(redis)

    # First check should return True (new event)
    assert await state.check_event_dedup("event_1") is True

    # Second check should return False (duplicate)
    assert await state.check_event_dedup("event_1") is False


@pytest.mark.asyncio
async def test_acquire_release_agent_lock():
    """Test agent lock acquire and release."""
    redis = MockRedis()
    state = MessengerState(redis)

    # Acquire lock
    token = await state.acquire_agent_lock("conv_1")
    assert token is not None

    # Try to acquire again (should fail)
    token2 = await state.acquire_agent_lock("conv_1")
    assert token2 is None

    # Release lock
    released = await state.release_agent_lock("conv_1", token)
    assert released is True

    # Can acquire again after release
    token3 = await state.acquire_agent_lock("conv_1")
    assert token3 is not None


@pytest.mark.asyncio
async def test_renew_agent_lock():
    """Test agent lock renewal."""
    redis = MockRedis()
    state = MessengerState(redis)

    token = await state.acquire_agent_lock("conv_1")
    assert token is not None

    # Renew with correct token
    renewed = await state.renew_agent_lock("conv_1", token)
    assert renewed is True

    # Renew with wrong token
    renewed = await state.renew_agent_lock("conv_1", "wrong_token")
    assert renewed is False


@pytest.mark.asyncio
async def test_release_lock_if_queue_empty():
    """Test conditional lock release based on queue."""
    redis = MockRedis()
    state = MessengerState(redis)

    token = await state.acquire_agent_lock("conv_1")

    # Queue is empty, should release
    released = await state.release_lock_if_queue_empty("conv_1", token)
    assert released is True

    # Acquire again and add to queue
    token = await state.acquire_agent_lock("conv_1")
    await state.enqueue_followup("conv_1", {"text": "hello"})

    # Queue not empty, should not release
    released = await state.release_lock_if_queue_empty("conv_1", token)
    assert released is False


@pytest.mark.asyncio
async def test_cancel_flag():
    """Test cancel flag operations."""
    redis = MockRedis()
    state = MessengerState(redis)

    # Set cancel flag
    await state.set_cancel_flag("task_1")

    # Check flag is set
    key = state._key("cancel:task_1")
    assert await redis.get(key) == "1"

    # Clear cancel flag
    await state.clear_cancel_flag("task_1")
    assert await redis.get(key) is None


@pytest.mark.asyncio
async def test_enqueue_drain_followups():
    """Test follow-up queue operations."""
    redis = MockRedis()
    state = MessengerState(redis)

    # Enqueue messages
    msg1 = {"text": "hello"}
    msg2 = {"text": "world"}
    await state.enqueue_followup("conv_1", msg1)
    await state.enqueue_followup("conv_1", msg2)

    # Drain queue
    messages = await state.drain_followups("conv_1")
    assert len(messages) == 2
    assert messages[0] == msg1
    assert messages[1] == msg2

    # Queue should be empty after drain
    messages = await state.drain_followups("conv_1")
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_followup_queue_max():
    """Test follow-up queue max limit."""
    redis = MockRedis()
    state = MessengerState(redis, followup_max_pending=2)

    # Enqueue up to max
    assert await state.enqueue_followup("conv_1", {"text": "1"}) is True
    assert await state.enqueue_followup("conv_1", {"text": "2"}) is True

    # Exceeding max should fail
    assert await state.enqueue_followup("conv_1", {"text": "3"}) is False


@pytest.mark.asyncio
async def test_dead_letters():
    """Test dead letter operations."""
    redis = MockRedis()
    state = MessengerState(redis)

    # Record dead letters
    await state.record_dead_letter({"error": "test1"})
    await state.record_dead_letter({"error": "test2"})

    # List dead letters
    letters = await state.list_dead_letters(count=10)
    assert len(letters) == 2
    assert letters[0]["error"] == "test2"  # Most recent first
    assert letters[1]["error"] == "test1"


@pytest.mark.asyncio
async def test_conv_create_lock():
    """Test conversation creation lock."""
    redis = MockRedis()
    state = MessengerState(redis)

    # Acquire lock
    token = await state.acquire_conv_create_lock("channel_1")
    assert token is not None

    # Try to acquire again (should fail)
    token2 = await state.acquire_conv_create_lock("channel_1")
    assert token2 is None

    # Release lock
    released = await state.release_conv_create_lock("channel_1", token)
    assert released is True


@pytest.mark.asyncio
async def test_no_redis():
    """Test state works without Redis (local mode)."""
    state = MessengerState(None)

    # All operations should work without errors
    assert await state.check_event_dedup("event_1") is True
    token = await state.acquire_agent_lock("conv_1")
    assert token is not None
    assert await state.release_agent_lock("conv_1", token) is True
    assert await state.enqueue_followup("conv_1", {"text": "hello"}) is True
    assert await state.drain_followups("conv_1") == []
