"""Redis-backed distributed state management for messenger.

Provides:
- Event deduplication
- Agent locks with auto-renewal
- Follow-up queues
- Dead letter management
- Cancel flags
- Conversation creation locks

All operations use Lua scripts for atomicity.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class MessengerState:
    """Distributed state management for messenger bots."""

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        key_prefix: str = "messenger:",
        event_dedup_ttl: int = 60,
        agent_lock_ttl: int = 300,
        followup_queue_ttl: int = 600,
        followup_max_pending: int = 5,
        dead_letter_max: int = 200,
        cancel_flag_ttl: int = 120,
    ):
        """Initialize messenger state.

        Args:
            redis_client: Redis client (optional, lazy import)
            key_prefix: Prefix for all Redis keys
            event_dedup_ttl: Event deduplication TTL in seconds
            agent_lock_ttl: Agent lock TTL in seconds
            followup_queue_ttl: Follow-up queue TTL in seconds
            followup_max_pending: Maximum pending follow-ups
            dead_letter_max: Maximum dead letters to keep
            cancel_flag_ttl: Cancel flag TTL in seconds
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.event_dedup_ttl = event_dedup_ttl
        self.agent_lock_ttl = agent_lock_ttl
        self.followup_queue_ttl = followup_queue_ttl
        self.followup_max_pending = followup_max_pending
        self.dead_letter_max = dead_letter_max
        self.cancel_flag_ttl = cancel_flag_ttl

    def _key(self, suffix: str) -> str:
        """Build Redis key with prefix.

        Args:
            suffix: Key suffix

        Returns:
            Full Redis key
        """
        return f"{self.key_prefix}{suffix}"

    async def check_event_dedup(self, event_id: str) -> bool:
        """Check if event has been processed (deduplication).

        Args:
            event_id: Event ID

        Returns:
            True if event is new (not duplicate)
        """
        if not self.redis:
            return True

        key = self._key(f"dedup:{event_id}")
        # SET NX with TTL - returns 1 if set, 0 if already exists
        result = await self.redis.set(key, "1", ex=self.event_dedup_ttl, nx=True)
        return bool(result)

    async def acquire_agent_lock(self, lock_key: str) -> str | None:
        """Acquire agent lock.

        Args:
            lock_key: Lock key (e.g., conversation ID)

        Returns:
            Lock token if acquired, None if already locked
        """
        if not self.redis:
            return str(uuid.uuid4())

        key = self._key(f"lock:agent:{lock_key}")
        token = str(uuid.uuid4())
        result = await self.redis.set(key, token, ex=self.agent_lock_ttl, nx=True)
        return token if result else None

    async def release_agent_lock(self, lock_key: str, token: str) -> bool:
        """Release agent lock.

        Args:
            lock_key: Lock key
            token: Lock token from acquire

        Returns:
            True if released
        """
        if not self.redis:
            return True

        key = self._key(f"lock:agent:{lock_key}")
        # Lua script for atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 1, key, token)
        return bool(result)

    async def renew_agent_lock(self, lock_key: str, token: str) -> bool:
        """Renew agent lock TTL.

        Args:
            lock_key: Lock key
            token: Lock token

        Returns:
            True if renewed
        """
        if not self.redis:
            return True

        key = self._key(f"lock:agent:{lock_key}")
        # Lua script for atomic check-and-expire
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 1, key, token, self.agent_lock_ttl)
        return bool(result)

    async def _renew_lock_loop(self, lock_key: str, token: str, interval: int = 30) -> None:
        """Background loop to auto-renew lock.

        Args:
            lock_key: Lock key
            token: Lock token
            interval: Renewal interval in seconds
        """
        while True:
            await asyncio.sleep(interval)
            renewed = await self.renew_agent_lock(lock_key, token)
            if not renewed:
                logger.warning(f"Failed to renew lock {lock_key}, stopping renewal loop")
                break

    async def release_lock_if_queue_empty(self, lock_key: str, token: str) -> bool:
        """Release lock only if follow-up queue is empty (atomic).

        Args:
            lock_key: Lock key
            token: Lock token

        Returns:
            True if released
        """
        if not self.redis:
            return True

        lock_redis_key = self._key(f"lock:agent:{lock_key}")
        queue_key = self._key(f"followup:{lock_key}")

        # Lua script for atomic check-queue-and-release
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            local queue_len = redis.call("llen", KEYS[2])
            if queue_len == 0 then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 2, lock_redis_key, queue_key, token)
        return bool(result)

    async def set_cancel_flag(self, key: str) -> None:
        """Set cancel flag.

        Args:
            key: Cancel key
        """
        if not self.redis:
            return

        redis_key = self._key(f"cancel:{key}")
        await self.redis.set(redis_key, "1", ex=self.cancel_flag_ttl)

    async def clear_cancel_flag(self, key: str) -> None:
        """Clear cancel flag.

        Args:
            key: Cancel key
        """
        if not self.redis:
            return

        redis_key = self._key(f"cancel:{key}")
        await self.redis.delete(redis_key)

    async def watch_cancel_flag(self, key: str, event: asyncio.Event, interval: int = 1) -> None:
        """Watch cancel flag and set event when flagged.

        Args:
            key: Cancel key
            event: Event to set when cancelled
            interval: Check interval in seconds
        """
        if not self.redis:
            return

        redis_key = self._key(f"cancel:{key}")
        while not event.is_set():
            result = await self.redis.get(redis_key)
            if result:
                event.set()
                break
            await asyncio.sleep(interval)

    async def enqueue_followup(self, key: str, message_data: dict[str, Any]) -> bool:
        """Enqueue follow-up message.

        Args:
            key: Queue key
            message_data: Message data

        Returns:
            True if enqueued, False if queue full
        """
        if not self.redis:
            return True

        queue_key = self._key(f"followup:{key}")
        # Check queue length
        queue_len = await self.redis.llen(queue_key)
        if queue_len >= self.followup_max_pending:
            return False

        # Push to queue with TTL
        await self.redis.rpush(queue_key, json.dumps(message_data))
        await self.redis.expire(queue_key, self.followup_queue_ttl)
        return True

    async def drain_followups(self, key: str) -> list[dict[str, Any]]:
        """Drain all follow-up messages atomically.

        Args:
            key: Queue key

        Returns:
            List of message data dicts
        """
        if not self.redis:
            return []

        queue_key = self._key(f"followup:{key}")
        # Lua script for atomic drain
        script = """
        local messages = redis.call("lrange", KEYS[1], 0, -1)
        redis.call("del", KEYS[1])
        return messages
        """
        messages = await self.redis.eval(script, 1, queue_key)
        return [json.loads(msg) for msg in messages] if messages else []

    async def record_dead_letter(self, data: dict[str, Any]) -> None:
        """Record dead letter.

        Args:
            data: Dead letter data
        """
        if not self.redis:
            return

        key = self._key("dead_letters")
        # Add timestamp
        data["timestamp"] = time.time()
        await self.redis.lpush(key, json.dumps(data))
        # Trim to max size
        await self.redis.ltrim(key, 0, self.dead_letter_max - 1)

    async def list_dead_letters(self, count: int = 10) -> list[dict[str, Any]]:
        """List recent dead letters.

        Args:
            count: Number of dead letters to retrieve

        Returns:
            List of dead letter data dicts
        """
        if not self.redis:
            return []

        key = self._key("dead_letters")
        messages = await self.redis.lrange(key, 0, count - 1)
        return [json.loads(msg) for msg in messages] if messages else []

    async def replay_dead_letters(self, handler: Callable[[dict[str, Any]], None]) -> int:
        """Replay dead letters through handler.

        Args:
            handler: Handler function for each dead letter

        Returns:
            Number of dead letters replayed
        """
        dead_letters = await self.list_dead_letters(count=self.dead_letter_max)
        for letter in dead_letters:
            try:
                await handler(letter)
            except Exception as e:
                logger.error(f"Failed to replay dead letter: {e}")

        return len(dead_letters)

    async def acquire_conv_create_lock(self, key: str) -> str | None:
        """Acquire conversation creation lock.

        Args:
            key: Lock key (e.g., channel ID)

        Returns:
            Lock token if acquired, None if already locked
        """
        if not self.redis:
            return str(uuid.uuid4())

        redis_key = self._key(f"lock:conv_create:{key}")
        token = str(uuid.uuid4())
        # 15 second TTL for conversation creation
        result = await self.redis.set(redis_key, token, ex=15, nx=True)
        return token if result else None

    async def release_conv_create_lock(self, key: str, token: str) -> bool:
        """Release conversation creation lock.

        Args:
            key: Lock key
            token: Lock token

        Returns:
            True if released
        """
        if not self.redis:
            return True

        redis_key = self._key(f"lock:conv_create:{key}")
        # Lua script for atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 1, redis_key, token)
        return bool(result)
