"""Agent runtime with tool calling and state management."""

from .agent import Agent
from .tools import Tool, tool
from .models import AgentState, ToolCall, ToolResult
from .registry import ToolRegistry
from .session import Session, SessionTree, SessionEntry
from .session_manager import SessionManager, SessionInfo
from .extensions import ExtensionAPI, ExtensionManager
from .skills import Skill, SkillManager
from .context import ContextManager
from .prompts import PromptTemplate, PromptManager
from .message_queue import MessageQueue, MessageType, QueuedMessage
from .export import SessionExporter
from .share import GistSharer
from .output_modes import JSONOutputMode, RPCMode, OutputModeManager
from .auth import AuthManager, OAuthProvider, OAuthFlow, TokenInfo

__version__ = "0.0.1"

__all__ = [
    "Agent",
    "Tool",
    "tool",
    "AgentState",
    "ToolCall",
    "ToolResult",
    "ToolRegistry",
    "Session",
    "SessionTree",
    "SessionEntry",
    "SessionManager",
    "SessionInfo",
    "ExtensionAPI",
    "ExtensionManager",
    "Skill",
    "SkillManager",
    "ContextManager",
    "PromptTemplate",
    "PromptManager",
    "MessageQueue",
    "MessageType",
    "QueuedMessage",
    "SessionExporter",
    "GistSharer",
    "JSONOutputMode",
    "RPCMode",
    "OutputModeManager",
    "AuthManager",
    "OAuthProvider",
    "OAuthFlow",
    "TokenInfo",
]
