"""Context file management (AGENTS.md, SYSTEM.md, etc.)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ContextManager:
    """Manages context files like AGENTS.md, SYSTEM.md."""

    def __init__(self, workspace: Path | None = None):
        """Initialize context manager.

        Args:
            workspace: Working directory (defaults to cwd)
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def find_context_files(self, filename: str) -> list[Path]:
        """Find context files in directory hierarchy.

        Searches from current directory up to home, plus global config.

        Args:
            filename: File to search for (e.g., "AGENTS.md")

        Returns:
            List of found files (ordered: global, parents, cwd)
        """
        found = []

        # Global config
        global_file = Path.home() / ".agents" / filename
        if global_file.exists():
            found.append(global_file)

        # Alternative global (for pi compatibility)
        pi_global = Path.home() / ".pi" / "agent" / filename
        if pi_global.exists() and pi_global not in found:
            found.append(pi_global)

        # Walk up from workspace
        current = self.workspace
        visited = set()

        while current != current.parent:
            if current in visited:
                break
            visited.add(current)

            # Check current directory
            file_path = current / filename
            if file_path.exists() and file_path not in found:
                found.append(file_path)

            # Check .agents directory
            agents_file = current / ".agents" / filename
            if agents_file.exists() and agents_file not in found:
                found.append(agents_file)

            # Check .pi directory
            pi_file = current / ".pi" / filename
            if pi_file.exists() and pi_file not in found:
                found.append(pi_file)

            # Move to parent
            current = current.parent

        return found

    def load_agents_md(self) -> str | None:
        """Load all AGENTS.md files.

        Returns:
            Combined content of all AGENTS.md files
        """
        files = self.find_context_files("AGENTS.md")

        if not files:
            return None

        content_parts = []
        for file_path in files:
            try:
                content = file_path.read_text()
                content_parts.append(f"# From: {file_path}\n\n{content}")
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")

        return "\n\n---\n\n".join(content_parts) if content_parts else None

    def load_system_md(self) -> str | None:
        """Load SYSTEM.md (replaces default system prompt).

        Returns:
            Content of SYSTEM.md if found
        """
        files = self.find_context_files("SYSTEM.md")

        if not files:
            return None

        # Use the most specific (last in list)
        try:
            return files[-1].read_text()
        except Exception as e:
            print(f"Warning: Failed to load SYSTEM.md: {e}")
            return None

    def load_append_system_md(self) -> str | None:
        """Load APPEND_SYSTEM.md (appends to system prompt).

        Returns:
            Combined content of all APPEND_SYSTEM.md files
        """
        files = self.find_context_files("APPEND_SYSTEM.md")

        if not files:
            return None

        content_parts = []
        for file_path in files:
            try:
                content = file_path.read_text()
                content_parts.append(content)
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")

        return "\n\n".join(content_parts) if content_parts else None

    def build_system_prompt(self, default_prompt: str) -> str:
        """Build final system prompt from context files.

        Args:
            default_prompt: Default system prompt

        Returns:
            Final system prompt with context files applied
        """
        # Check for SYSTEM.md override
        system_md = self.load_system_md()
        if system_md:
            base_prompt = system_md
        else:
            base_prompt = default_prompt

        # Append AGENTS.md if exists
        agents_md = self.load_agents_md()
        if agents_md:
            base_prompt += f"\n\n# Project Context\n\n{agents_md}"

        # Append APPEND_SYSTEM.md if exists
        append_md = self.load_append_system_md()
        if append_md:
            base_prompt += f"\n\n{append_md}"

        return base_prompt

    def watch_for_changes(self) -> None:
        """Watch context files for changes (for hot-reload).

        Note: Actual implementation would use file watching.
        This is a placeholder for the API.
        """
        # TODO: Implement file watching
        pass


# ---------------------------------------------------------------------------
# Agent context hydration (for runtime context management)
# ---------------------------------------------------------------------------


@dataclass
class CachedContext:
    """Cached context for agent execution.

    Attributes:
        system_prompt: System prompt template
        user_config: User-specific configuration
        metadata: Additional metadata
    """

    system_prompt: str = ""
    user_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


async def hydrate(user_id: str) -> CachedContext:
    """Load user context (simplified version without external dependencies).

    In a production environment, this would load from:
    - Database for user preferences
    - Redis cache for performance
    - External services for integrations

    Args:
        user_id: User identifier

    Returns:
        CachedContext with user-specific settings
    """
    # Simplified implementation - returns default context
    # In production, this would load from database/cache
    return CachedContext(
        system_prompt="You are a helpful AI assistant.",
        user_config={
            "user_id": user_id,
            "preferences": {},
        },
        metadata={},
    )


def build_messages(
    ctx: CachedContext,
    history: list[dict[str, Any]],
    user_text: str,
) -> list[dict[str, Any]]:
    """Build message list for LLM with context injection.

    Args:
        ctx: Cached context with system prompt
        history: Conversation history
        user_text: Current user message

    Returns:
        Complete message list for LLM
    """
    messages = []

    # Add system prompt if available
    if ctx.system_prompt:
        messages.append(
            {
                "role": "system",
                "content": ctx.system_prompt,
            }
        )

    # Add conversation history
    messages.extend(history)

    # Add current user message
    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    return messages


# ---------------------------------------------------------------------------
# Extension Protocols
# ---------------------------------------------------------------------------


class ContextLoader(Protocol):
    """Protocol for loading user/brand context.

    Allows products to inject custom context loading logic.
    """

    async def load_context(self, user_id: str) -> dict[str, Any]:
        """Load context for a user.

        Args:
            user_id: User identifier

        Returns:
            Context dictionary with user-specific data
        """
        ...


class SystemPromptBuilder(Protocol):
    """Protocol for building system prompts.

    Allows products to customize system prompt construction.
    """

    def build_prompt(self, base_prompt: str, context: dict[str, Any]) -> str:
        """Build system prompt from base and context.

        Args:
            base_prompt: Base system prompt
            context: User/brand context

        Returns:
            Final system prompt
        """
        ...


# ---------------------------------------------------------------------------
# 3-Level Context Compression
# ---------------------------------------------------------------------------


@dataclass
class CompressionConfig:
    """Configuration for context compression.

    Attributes:
        level1_threshold: Token ratio to trigger Level 1 (truncate tool results)
        level2_threshold: Token ratio to trigger Level 2 (replace with summaries)
        level3_threshold: Token ratio to trigger Level 3 (LLM summarization)
        max_tool_result_chars: Max characters per tool result after Level 1
    """

    level1_threshold: float = 0.7  # 70% of context window
    level2_threshold: float = 0.8  # 80% of context window
    level3_threshold: float = 0.9  # 90% of context window
    max_tool_result_chars: int = 1000


def compress_level1(messages: list[dict[str, Any]], max_chars: int = 1000) -> list[dict[str, Any]]:
    """Level 1: Truncate tool result messages.

    Args:
        messages: Message list
        max_chars: Maximum characters per tool result

    Returns:
        Compressed message list
    """
    compressed = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if len(content) > max_chars:
                truncation_msg = f"\n\n[... truncated {len(content) - max_chars} chars]"
                truncated = content[:max_chars] + truncation_msg
                compressed.append({**msg, "content": truncated})
            else:
                compressed.append(msg)
        else:
            compressed.append(msg)
    return compressed


def compress_level2(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Level 2: Replace tool call/result pairs with summaries.

    Args:
        messages: Message list

    Returns:
        Compressed message list with summaries
    """
    compressed = []
    i = 0
    while i < len(messages):
        msg = messages[i]

        # Look for assistant message with tool calls
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls", [])
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]

            # Collect following tool results
            j = i + 1
            tool_results = []
            while j < len(messages) and messages[j].get("role") == "tool":
                tool_results.append(messages[j])
                j += 1

            # Create summary
            summary = f"[Tool execution: {', '.join(tool_names)} - {len(tool_results)} results]"
            compressed.append(
                {
                    "role": "assistant",
                    "content": summary,
                }
            )

            # Skip the tool result messages
            i = j
        else:
            compressed.append(msg)
            i += 1

    return compressed


async def compress_level3(messages: list[dict[str, Any]], llm: Any) -> list[dict[str, Any]]:
    """Level 3: LLM-summarize middle messages.

    Keeps system prompt, recent messages, and summarizes the middle.

    Args:
        messages: Message list
        llm: LLM client for summarization

    Returns:
        Compressed message list with LLM summary
    """
    if len(messages) <= 5:
        return messages

    # Keep system prompt (first message if role=system)
    system_msg = []
    start_idx = 0
    if messages and messages[0].get("role") == "system":
        system_msg = [messages[0]]
        start_idx = 1

    # Keep last 3 messages
    recent = messages[-3:]
    middle = messages[start_idx:-3]

    if not middle:
        return messages

    # Build summary prompt
    middle_text = "\n\n".join(
        [f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}" for msg in middle]
    )

    summary_prompt = (
        "Summarize this conversation history in 2-3 sentences, "
        f"focusing on key decisions and context:\n\n{middle_text}\n\nSummary:"
    )

    try:
        # Use LLM to summarize
        response = await llm.achat(
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=200,
        )
        summary = response.content

        # Build compressed messages
        compressed = (
            system_msg
            + [
                {
                    "role": "assistant",
                    "content": f"[Previous conversation summary: {summary}]",
                }
            ]
            + recent
        )

        return compressed
    except Exception:
        # If summarization fails, fall back to Level 2
        return compress_level2(messages)


def compress_messages(
    messages: list[dict[str, Any]],
    current_tokens: int,
    max_tokens: int,
    config: CompressionConfig | None = None,
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Apply appropriate compression level based on token usage.

    Args:
        messages: Message list
        current_tokens: Current token count
        max_tokens: Maximum allowed tokens
        config: Compression configuration
        llm: LLM client for Level 3 compression

    Returns:
        Compressed message list
    """
    if config is None:
        config = CompressionConfig()

    ratio = current_tokens / max_tokens

    if ratio < config.level1_threshold:
        # No compression needed
        return messages

    if ratio < config.level2_threshold:
        # Level 1: Truncate tool results
        return compress_level1(messages, config.max_tool_result_chars)

    if ratio < config.level3_threshold:
        # Level 2: Replace with summaries
        return compress_level2(messages)

    # Level 3: LLM summarization (async, so return Level 2 for now)
    # In practice, this should be called with await compress_level3()
    return compress_level2(messages)
