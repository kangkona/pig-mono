"""Agent runtime with tool calling and state management."""

from .agent import Agent
from .auth import AuthManager, OAuthFlow, OAuthProvider, TokenInfo
from .context import (
    CompressionConfig,
    ContextLoader,
    ContextManager,
    SystemPromptBuilder,
    compress_messages,
)
from .export import SessionExporter
from .extensions import ExtensionAPI, ExtensionManager
from .memory import InMemoryProvider, MemoryProvider, Message
from .message_queue import MessageQueue, MessageType, QueuedMessage
from .models import AgentState, ToolCall, ToolResult
from .observability.events import (
    AgentEvent,
    AgentEventCallback,
    AgentEventType,
    BillingHook,
    emit_context_compressed,
    emit_model_fallback,
    emit_profile_rotated,
)
from .output_modes import JSONOutputMode, OutputModeManager, RPCMode
from .prompts import PromptManager, PromptTemplate
from .registry import ToolRegistry
from .resilience.profile import FailoverReason, ProfileManager, classify_failure
from .resilience.retry import ResilienceExhaustedError, resilient_call, resilient_streaming_call
from .session import Session, SessionEntry, SessionTree
from .session_manager import SessionInfo, SessionManager
from .share import GistSharer
from .skills import Skill, SkillManager
from .token_counter import count_tokens
from .tools import Tool, tool
from .tools.audit import ToolAuditEntry, ToolAuditLog
from .tools.base import ToolResult as EnhancedToolResult
from .tools.metrics import ToolMetrics, ToolMetricsCollector
from .tools.registry import ToolRegistry as EnhancedToolRegistry

__version__ = "0.0.4"

__all__ = [
    # Core
    "Agent",
    "Tool",
    "tool",
    "AgentState",
    "ToolCall",
    "ToolResult",
    "ToolRegistry",
    # Memory
    "MemoryProvider",
    "InMemoryProvider",
    "Message",
    # Context
    "ContextManager",
    "ContextLoader",
    "SystemPromptBuilder",
    "CompressionConfig",
    "compress_messages",
    # Observability
    "AgentEvent",
    "AgentEventType",
    "AgentEventCallback",
    "BillingHook",
    "emit_profile_rotated",
    "emit_context_compressed",
    "emit_model_fallback",
    # Resilience
    "ProfileManager",
    "FailoverReason",
    "classify_failure",
    "resilient_call",
    "resilient_streaming_call",
    "ResilienceExhaustedError",
    # Token counting
    "count_tokens",
    # Tool system
    "EnhancedToolRegistry",
    "EnhancedToolResult",
    "ToolAuditLog",
    "ToolAuditEntry",
    "ToolMetrics",
    "ToolMetricsCollector",
    # Session management
    "Session",
    "SessionTree",
    "SessionEntry",
    "SessionManager",
    "SessionInfo",
    # Extensions
    "ExtensionAPI",
    "ExtensionManager",
    "Skill",
    "SkillManager",
    # Prompts
    "PromptTemplate",
    "PromptManager",
    # Message queue
    "MessageQueue",
    "MessageType",
    "QueuedMessage",
    # Export/Share
    "SessionExporter",
    "GistSharer",
    # Output modes
    "JSONOutputMode",
    "RPCMode",
    "OutputModeManager",
    # Auth
    "AuthManager",
    "OAuthProvider",
    "OAuthFlow",
    "TokenInfo",
]
