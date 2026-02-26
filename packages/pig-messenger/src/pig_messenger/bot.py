"""Universal messenger bot core."""

import asyncio
import time
from collections.abc import Iterator
from functools import partial
from pathlib import Path

from pig_agent_core import Agent

from .message import UniversalMessage
from .platform import MessagePlatform
from .session_manager import MultiPlatformSessionManager

_STREAM_THROTTLE_SECONDS = 0.5


class MessengerBot:
    """Universal multi-platform bot."""

    def __init__(
        self,
        agent: Agent,
        workspace: Path | None = None,
        enable_sessions: bool = True,
    ):
        """Initialize messenger bot.

        Args:
            agent: Agent instance
            workspace: Workspace directory
            enable_sessions: Enable session management
        """
        self.agent = agent
        self.workspace = Path(workspace) if workspace else Path.cwd() / ".messenger"
        self.workspace.mkdir(exist_ok=True)

        self.platforms: dict[str, MessagePlatform] = {}
        self.session_manager = None

        if enable_sessions:
            self.session_manager = MultiPlatformSessionManager(self.workspace)

    def add_platform(self, platform: MessagePlatform) -> None:
        """Add a platform adapter.

        Args:
            platform: Platform adapter instance
        """
        self.platforms[platform.name] = platform
        platform.set_message_handler(self.handle_message)
        print(f"✓ Added platform: {platform.name}")

    def remove_platform(self, platform_name: str) -> None:
        """Remove a platform adapter.

        Args:
            platform_name: Platform name
        """
        if platform_name in self.platforms:
            platform = self.platforms[platform_name]
            platform.stop()
            del self.platforms[platform_name]
            print(f"✓ Removed platform: {platform_name}")

    async def handle_message(self, message: UniversalMessage) -> None:
        """Handle incoming message from any platform.

        Uses streaming card updates when the platform supports it and the
        agent has an LLM with a ``stream`` method.  Otherwise falls back to
        the standard request/response flow.

        Args:
            message: Universal message
        """
        platform = self.platforms.get(message.platform)

        # Streaming path: platform overrides update_card *and* agent has LLM streaming
        if (
            platform is not None
            and type(platform).update_card is not MessagePlatform.update_card
            and hasattr(self.agent, "llm")
            and hasattr(self.agent.llm, "stream")
        ):
            await self._handle_message_streaming(message, platform)
            return

        # Standard (non-streaming) path
        try:
            session = None
            if self.session_manager:
                session = self.session_manager.get_session(message.platform, message.channel_id)
                session.add_message("user", message.text)

            response = self.agent.run(message.text)

            if session:
                session.add_message("assistant", response.content)

            if platform:
                await platform.send_message(
                    message.channel_id,
                    response.content,
                    thread_id=message.thread_id if message.is_thread else None,
                )

        except Exception as e:
            print(f"Error handling message: {e}")
            if platform:
                try:
                    await platform.send_message(
                        message.channel_id,
                        f"❌ Error: {e}",
                        thread_id=message.thread_id if message.is_thread else None,
                    )
                except Exception:
                    pass

    async def _handle_message_streaming(
        self,
        message: UniversalMessage,
        platform: MessagePlatform,
    ) -> None:
        """Handle a message with streaming card updates.

        1. Send a placeholder card.
        2. Stream LLM chunks, throttle-updating the card.
        3. Final update with the complete text.

        Args:
            message: Incoming user message
            platform: Platform adapter (must support ``update_card``)
        """
        session = None
        if self.session_manager:
            session = self.session_manager.get_session(message.platform, message.channel_id)
            session.add_message("user", message.text)

        try:
            # 1. Send placeholder card
            card_id = await platform.send_card(message.channel_id, "⏳ 思考中...")

            # 2. Stream chunks from the LLM
            loop = asyncio.get_running_loop()
            accumulated = ""
            last_update = time.monotonic()

            # agent.llm.stream() is synchronous — run in executor
            stream_iter: Iterator = await loop.run_in_executor(
                None,
                partial(self.agent.llm.stream, message.text),
            )

            for chunk in stream_iter:
                accumulated += chunk.content
                now = time.monotonic()
                if now - last_update >= _STREAM_THROTTLE_SECONDS:
                    await platform.update_card(card_id, accumulated + "\n\n● 生成中...")
                    last_update = now

            # 3. Final update — remove "生成中" indicator
            await platform.update_card(card_id, accumulated)

            if session:
                session.add_message("assistant", accumulated)

        except Exception as e:
            print(f"Error in streaming handler: {e}")
            try:
                await platform.send_message(
                    message.channel_id,
                    f"❌ Error: {e}",
                    thread_id=message.thread_id if message.is_thread else None,
                )
            except Exception:
                pass

    def start(self) -> None:
        """Start all platforms.

        This is a blocking call.
        """
        if not self.platforms:
            print("No platforms configured!")
            return

        print(f"\n🤖 Starting MessengerBot with {len(self.platforms)} platform(s)...")
        for name in self.platforms:
            print(f"   • {name}")
        print()

        if len(self.platforms) == 1:
            # Single platform — just call start() directly (blocking)
            platform = next(iter(self.platforms.values()))
            try:
                platform.start()
            except KeyboardInterrupt:
                print("\n\nStopping bot...")
                self.stop()
        else:
            # Multiple platforms — run in threads
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(p.start): name for name, p in self.platforms.items()}
                try:
                    concurrent.futures.wait(futures)
                except KeyboardInterrupt:
                    print("\n\nStopping bot...")
                    self.stop()

    def stop(self) -> None:
        """Stop all platforms."""
        for platform in self.platforms.values():
            try:
                platform.stop()
            except Exception as e:
                print(f"Error stopping {platform.name}: {e}")

        print("✓ Bot stopped")
