"""Message routing and processing manager for messenger lifecycle orchestration."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerThread,
    MessengerType,
)

logger = logging.getLogger(__name__)


def split_message(text: str, max_length: int) -> list[str]:
    """Split text into chunks at natural boundaries.

    Args:
        text: Text to split
        max_length: Maximum length per chunk

    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Find split point in second half
        split_point = max_length
        search_start = max_length // 2

        # Priority: \n\n > \n > . > space
        for delimiter in ["\n\n", "\n", ". ", " "]:
            idx = remaining.rfind(delimiter, search_start, max_length)
            if idx != -1:
                split_point = idx + len(delimiter)
                break

        chunks.append(remaining[:split_point])
        remaining = remaining[split_point:]

    return chunks


def _is_transient(error: Exception) -> bool:
    """Check if error is transient and retryable.

    Args:
        error: Exception to check

    Returns:
        True if error is transient
    """
    if isinstance(error, ConnectionError | TimeoutError):
        return True

    # Check HTTP status codes
    error_str = str(error).lower()
    return any(code in error_str for code in ["429", "502", "503", "504"])


async def _post_with_retry(
    fn: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 1.5,
) -> Any:
    """Retry adapter send operations with exponential backoff.

    Args:
        fn: Async function to retry
        max_retries: Maximum retry attempts
        base_delay: Base delay in seconds

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_transient(e):
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Transient error (attempt {attempt + 1}): {e}. Retrying in {delay}s"
                )
                await asyncio.sleep(delay)
            else:
                break

    raise last_error  # type: ignore


class MessengerManager:
    """Message routing and processing manager."""

    def __init__(
        self,
        agent_factory: Callable[[IncomingMessage, MessengerThread], Any],
        state: Any | None = None,
        conversation_factory: Callable[[str, str], Any] | None = None,
        i18n: dict[str, str] | None = None,
        max_followup_rounds: int = 8,
        followup_ack_message: str | None = None,
    ):
        """Initialize manager.

        Args:
            agent_factory: Factory for creating agent instances
            state: MessengerState instance or None
            conversation_factory: Factory for creating conversations
            i18n: Internationalization strings
            max_followup_rounds: Max follow-up drain rounds
            followup_ack_message: Message when queuing during active run
        """
        self.agent_factory = agent_factory
        self.state = state
        self.conversation_factory = conversation_factory
        self.i18n = i18n or {}
        self.max_followup_rounds = max_followup_rounds
        self.followup_ack_message = followup_ack_message

        self._background_tasks: set[asyncio.Task] = set()
        self._adapters: dict[MessengerType, BaseMessengerAdapter] = {}
        self._discord_leader_task: asyncio.Task | None = None
        self._stream_intervals = {
            MessengerType.TELEGRAM: 0.25,
        }

    async def handle_event(
        self,
        messenger_type: MessengerType,
        raw_event: dict[str, Any],
        *,
        adapter: BaseMessengerAdapter,
    ) -> None:
        """Handle incoming messenger event.

        Args:
            messenger_type: Platform type
            raw_event: Raw event data
            adapter: Messenger adapter instance
        """
        self._adapters[messenger_type] = adapter

        # Parse event
        message = await adapter.parse_event(raw_event)
        if not message:
            return

        # Check deduplication
        if self.state:
            is_dup = await self.state.check_event_dedup(message.message_id)
            if is_dup:
                logger.debug(f"Duplicate event: {message.message_id}")
                return

        # Create thread
        thread = MessengerThread(
            adapter=adapter,
            channel_id=message.channel_id,
            capabilities=adapter.capabilities,
        )

        # Spawn background processing
        self._spawn_background(
            self._process_message(message, thread),
            message.message_id,
        )

    async def _process_message(self, message: IncomingMessage, thread: MessengerThread) -> None:
        """Process message with agent execution and follow-up drain.

        Args:
            message: Incoming message
            thread: Messenger thread
        """
        lock_key = f"{message.platform.value}:{message.channel_id}"
        lock_token = None

        try:
            # Acquire agent lock
            if self.state:
                lock_token = await self.state.acquire_agent_lock(lock_key)
                if not lock_token:
                    # Queue as follow-up
                    await self.state.enqueue_followup(lock_key, {"text": message.text})
                    if self.followup_ack_message:
                        await _post_with_retry(lambda: thread.post(self.followup_ack_message))
                    return

            # Process message with agent
            await self._run_agent(message, thread)

            # Drain follow-ups
            if self.state and lock_token:
                await self._drain_followups(lock_key, lock_token, thread, message.platform)

        finally:
            # Release lock
            if self.state and lock_token:
                await self.state.release_agent_lock(lock_key, lock_token)

    async def _run_agent(self, message: IncomingMessage, thread: MessengerThread) -> None:
        """Run agent with streaming support.

        Args:
            message: Incoming message
            thread: Messenger thread
        """
        # Create conversation if needed
        if self.conversation_factory:
            await self._ensure_conversation(message.platform.value, message.channel_id)

        # Call agent factory
        agent_result = self.agent_factory(message, thread)

        # Handle async generator (streaming)
        if hasattr(agent_result, "__anext__"):
            interval = self._stream_intervals.get(message.platform, 0.5)
            await thread.stream(agent_result, interval=interval)
        # Handle awaitable
        elif hasattr(agent_result, "__await__"):
            response = await agent_result
            if response:
                await _post_with_retry(lambda: thread.post(response))
        # Handle sync result
        elif agent_result:
            await _post_with_retry(lambda: thread.post(str(agent_result)))

    async def _drain_followups(
        self,
        lock_key: str,
        lock_token: str,
        thread: MessengerThread,
        platform: MessengerType,
    ) -> None:
        """Drain follow-up queue.

        Args:
            lock_key: Lock key
            lock_token: Lock token
            thread: Messenger thread
            platform: Platform type
        """
        for round_num in range(self.max_followup_rounds):
            # Check if queue empty and release if so
            released = await self.state.release_lock_if_queue_empty(lock_key, lock_token)
            if released:
                logger.debug(f"Queue empty, released lock: {lock_key}")
                return

            # Drain follow-ups
            followups = await self.state.drain_followups(lock_key)
            if not followups:
                break

            logger.info(f"Draining {len(followups)} follow-ups (round {round_num + 1})")

            # Process each follow-up
            for followup_data in followups:
                # Create synthetic message
                message = IncomingMessage(
                    message_id=f"followup-{round_num}",
                    platform=platform,
                    channel_id=thread.channel_id,
                    text=followup_data.get("text", ""),
                    user=None,
                    timestamp=0,
                )

                # Run agent
                await self._run_agent(message, thread)

    async def _ensure_conversation(self, platform: str, channel_id: str) -> None:
        """Ensure conversation exists with distributed lock.

        Args:
            platform: Platform type
            channel_id: Channel ID
        """
        if not self.conversation_factory:
            return

        lock_key = f"conv_create:{platform}:{channel_id}"
        lock_token = None

        try:
            if self.state:
                lock_token = await self.state.acquire_conv_create_lock(lock_key)
                if not lock_token:
                    # Another instance is creating
                    await asyncio.sleep(0.5)
                    return

            # Create conversation
            await self.conversation_factory(platform, channel_id)

        finally:
            if self.state and lock_token:
                await self.state.release_conv_create_lock(lock_key, lock_token)

    def _spawn_background(self, coro: Any, task_id: str | None = None) -> None:
        """Spawn background task with error handling.

        Args:
            coro: Coroutine to run
            task_id: Optional task identifier
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(lambda t: self._on_task_done(t, task_id))

    def _on_task_done(self, task: asyncio.Task, task_id: str | None) -> None:
        """Handle task completion.

        Args:
            task: Completed task
            task_id: Task identifier
        """
        self._background_tasks.discard(task)

        if task.exception():
            exc = task.exception()
            logger.error(f"Background task failed: {exc}", exc_info=exc)

            # Record dead letter
            if self.state:
                asyncio.create_task(
                    self.state.record_dead_letter(
                        {
                            "task_id": task_id,
                            "error": str(exc),
                            "type": type(exc).__name__,
                        }
                    )
                )

    async def list_dead_letters(self, count: int = 50) -> list[dict[str, Any]]:
        """List dead letters.

        Args:
            count: Maximum number to return

        Returns:
            List of dead letter data
        """
        if not self.state:
            return []
        return await self.state.list_dead_letters(count)

    async def replay_dead_letters(self, handler: Callable[[dict[str, Any]], Any]) -> int:
        """Replay dead letters with handler.

        Args:
            handler: Handler function for each dead letter

        Returns:
            Number of dead letters replayed
        """
        if not self.state:
            return 0
        return await self.state.replay_dead_letters(handler)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down messenger manager")

        # Stop Discord leader election
        if self._discord_leader_task:
            self._discord_leader_task.cancel()
            try:
                await self._discord_leader_task
            except asyncio.CancelledError:
                pass

        # Wait for background tasks
        if self._background_tasks:
            logger.info(f"Waiting for {len(self._background_tasks)} background tasks")
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Close all adapters
        for adapter in self._adapters.values():
            try:
                await adapter.aclose()
            except Exception as e:
                logger.error(f"Error closing adapter: {e}")

        logger.info("Shutdown complete")
