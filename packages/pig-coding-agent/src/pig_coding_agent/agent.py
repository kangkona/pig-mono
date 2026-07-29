"""Coding agent with file operations and code generation."""

import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from pig_agent_core import (
    Agent,
    ContextManager,
    ExtensionManager,
    PromptManager,
    Session,
    SessionManager,
    SkillManager,
    assert_valid_session_id,
)
from pig_agent_core.tools import Tool, ToolResult
from pig_llm import LLM, Message

from .app_actions import AppActions
from .billing import CostTracker, CostTrackerBillingHook
from .config import ConfigManager
from .file_reference import FileReferenceParser
from .interaction_catalog import InteractionCatalog
from .interaction_runtime import InteractionRuntime, InteractionUI
from .interactive_mode import InteractiveMode
from .permissions import (
    SIDE_EFFECTFUL_TOOL_NAMES,
    PermissionPolicy,
    PermissionRequest,
    format_permission_denial,
)
from .project_trust import (
    ProjectTrustDecider,
    ProjectTrustStore,
    resolve_project_trust,
)
from .resilience import create_profile_manager_from_env, get_profile_status
from .results import ResultFactory
from .tools import FileTools, build_coding_tools


class SessionExitRequested(Exception):
    """Raised for explicit user-driven session exits like /exit and /quit."""


@dataclass(frozen=True)
class AgentTurnResult:
    """One completed turn plus any permission denials observed during it."""

    content: str
    permission_denials: tuple[dict[str, str], ...] = ()

    @property
    def denied(self) -> bool:
        """Return whether a side-effectful tool was denied during the turn."""
        return bool(self.permission_denials)


class _TrustedContextManager(ContextManager):
    """Load global instructions always and workspace instructions only when trusted."""

    def __init__(self, workspace: Path, *, project_trusted: bool) -> None:
        super().__init__(workspace)
        self.project_trusted = project_trusted

    def find_context_files(self, filename: str) -> list[Path]:
        """Return global files, plus the inherited project hierarchy when trusted."""
        if self.project_trusted:
            return super().find_context_files(filename)

        found: list[Path] = []
        global_candidates = (
            Path.home() / ".agents" / filename,
            Path.home() / ".pi" / "agent" / filename,
        )
        for path in global_candidates:
            if path.exists() and path not in found:
                found.append(path)

        return found


class CodingAgent:
    """Interactive coding agent with file and code tools."""

    @staticmethod
    def _compress_overflow_messages(messages: list[Message]) -> list[Message]:
        """Build a deterministic retry context that is strictly shorter."""
        if len(messages) <= 3:
            return messages

        leading: list[Message] = []
        body = messages
        if messages[0].role == "system":
            leading = [messages[0]]
            body = messages[1:]
        keep_count = min(4, max(1, len(body) - 2))
        older = body[:-keep_count]
        recent = body[-keep_count:]
        if len(older) < 2:
            return messages

        excerpts = []
        for item in older[-6:]:
            compact = " ".join(item.content.split())
            excerpts.append(f"{item.role}: {compact[:160]}")
        summary = Message(
            role="system",
            content=(
                f"[Overflow recovery compacted {len(older)} earlier messages]\n"
                + "\n".join(excerpts)
            ),
            metadata={"compacted": True, "reason": "overflow"},
        )
        return [*leading, summary, *recent]

    def __init__(
        self,
        llm: LLM | None = None,
        workspace: str = ".",
        verbose: bool = True,
        session_name: str | None = None,
        session_id: str | None = None,
        session_dir: str | Path | None = None,
        session_path: Path | None = None,
        fork_source_path: Path | None = None,
        enable_extensions: bool = True,
        enable_skills: bool = True,
        enable_resilience: bool = True,
        enable_cost_tracking: bool = True,
        excluded_tools: set[str] | None = None,
        permission_policy: PermissionPolicy | None = None,
        project_trust: bool | None = None,
        project_trust_decider: ProjectTrustDecider | None = None,
        project_trust_store: ProjectTrustStore | None = None,
        unattended_project_trust: bool = True,
    ) -> None:
        """Initialize coding agent.

        Args:
            llm: LLM client
            workspace: Working directory
            verbose: Enable verbose output
            session_name: Session name for auto-save
            session_id: Explicit session ID for automation
            session_dir: Explicit session directory override
            session_path: Path to load existing session
            fork_source_path: Existing session path to fork into a new session
            enable_extensions: Enable extension system
            enable_skills: Enable skills system
            enable_resilience: Enable resilience (API key rotation, fallback)
            enable_cost_tracking: Enable cost tracking
            excluded_tools: Tool names to disable for this agent
            permission_policy: Permission gate for write_file and run_command
            project_trust: Explicit per-invocation project trust override
            project_trust_decider: Interactive host callback for unknown workspaces
            project_trust_store: Persistent allow/deny decision store
            unattended_project_trust: Fail closed when no trust decision exists
        """
        self.workspace = Path(workspace).resolve()
        self.project_trusted = resolve_project_trust(
            self.workspace,
            override=project_trust,
            decider=project_trust_decider,
            store=project_trust_store,
            # Supplying a decider is the host's explicit opt-in to an
            # interactive decision even though embedding defaults unattended.
            unattended=unattended_project_trust and project_trust_decider is None,
        )
        self.llm = llm or LLM()
        self.verbose = verbose
        self.excluded_tools = set(excluded_tools or set())
        self.permission_policy = permission_policy or self._build_interactive_permission_policy()
        self._extensions_shutdown_done = False
        self._protocol_shutdown: Callable[[str], None] | None = None
        self._protocol_shutdown_emitted = False
        self.config_manager = ConfigManager(
            self.workspace,
            project_trusted=self.project_trusted,
        )
        self.result_factory = ResultFactory()
        self.app_actions = AppActions(self)
        self.interaction_catalog = InteractionCatalog(self)
        if session_dir is None and os.environ.get("PIG_CODING_AGENT_SESSION_DIR") is None:
            session_dir = self.config_manager.get_session_dir()
        self.sessions_dir = SessionManager(self.workspace, session_dir=session_dir).sessions_dir
        self._session_start_reason = "startup"
        self._previous_session_file: str | None = None

        if session_id is not None:
            assert_valid_session_id(session_id)

        # Initialize resilience (ProfileManager)
        self.profile_manager = None
        if enable_resilience:
            self.profile_manager = create_profile_manager_from_env()
            if self.profile_manager and verbose:
                status = get_profile_status(self.profile_manager)
                print(f"✓ Resilience enabled: {status['available_profiles']} API keys available")

        # Initialize cost tracking
        self.cost_tracker = None
        self.billing_hook = None
        if enable_cost_tracking:
            self.cost_tracker = CostTracker(self.workspace)
            self.billing_hook = CostTrackerBillingHook(self.cost_tracker)
            if verbose:
                print("✓ Cost tracking enabled")

        self.session = self._initialize_session(
            session_name=session_name,
            session_id=session_id,
            session_dir=session_dir,
            session_path=session_path,
            fork_source_path=fork_source_path,
            verbose=verbose,
        )

        # Initialize tools (new-registry style: explicit schemas + handlers,
        # registered in bulk on the agent's registry once it exists below).
        coding_schemas, coding_handlers = build_coding_tools(
            str(self.workspace),
            permission_policy=self.permission_policy,
        )

        # Initialize context manager (needed by _get_system_prompt)
        self.context_manager = _TrustedContextManager(
            self.workspace,
            project_trusted=self.project_trusted,
        )

        # Initialize skill manager
        self.skill_manager = None
        if enable_skills:
            self.skill_manager = SkillManager()
            self._load_skills()
            if verbose and len(self.skill_manager) > 0:
                print(f"✓ Loaded {len(self.skill_manager)} skills")

        # Create agent
        self.agent = Agent(
            name="CodingAgent",
            llm=self.llm,
            system_prompt=self._get_system_prompt(),
            verbose=verbose,
            profile_manager=self.profile_manager,
            compress_fn=self._compress_overflow_messages,
            billing_hook=self.billing_hook,
            # No iteration cap (pi-mono parity): turns run until natural
            # completion, a terminate tool result, or user abort (Esc/Ctrl-C).
            max_rounds=0,
            session=self.session,
            tool_adapter=self._prepare_tool,
        )

        # Register the coding tools on the agent's registry, then drop any tools
        # excluded for this agent instance. (Web search is handled natively by
        # the model provider when enabled, not as a locally-dispatched tool.)
        self.agent.registry.register_package(coding_schemas, coding_handlers, is_core=True)
        for name in self.excluded_tools:
            self.agent.registry.unregister(name)

        if hasattr(self.session, "usage_ledger"):
            self.agent.usage = self.session.usage_ledger

        # When resuming/forking an existing session at startup, replay its
        # conversation into the agent's LLM context so the model continues with
        # the prior history (not just the persisted tree). No-op for a fresh
        # session (empty conversation).
        if self._session_start_reason in ("resume", "fork"):
            self.app_actions.rebuild_history_from_session()

        # Initialize extension manager
        self.extension_manager = self._initialize_extension_manager(enable_extensions)

        # Initialize prompt manager
        self.prompt_manager = self._initialize_prompt_manager(verbose)

        # Initialize file reference parser
        self.file_ref_parser = FileReferenceParser(self.workspace)

        self.interaction_runtime = InteractionRuntime(self)
        self.interactive_mode = InteractiveMode(self, self.interaction_runtime)
        self.agent.ui = self.ui

        if self.extension_manager:
            event = {"reason": self._session_start_reason}
            if self._previous_session_file is not None:
                event["previousSessionFile"] = self._previous_session_file
            self.extension_manager.emit_event("session_start", event)

    def _new_session(self, name: str, session_id: str | None = None) -> Session:
        session = Session(
            name=name,
            workspace=str(self.workspace),
            auto_save=True,
            session_dir=self.sessions_dir,
        )
        if session_id:
            session.id = session_id
        return session

    def _resolve_existing_session_path(
        self,
        session_id: str | None,
        session_dir: str | Path | None,
    ) -> Path | None:
        if not session_id:
            return None
        session_manager = SessionManager(self.workspace, session_dir=session_dir)
        return session_manager.find_session(session_id)

    def _initialize_session(
        self,
        *,
        session_name: str | None,
        session_id: str | None,
        session_dir: str | Path | None,
        session_path: Path | None,
        fork_source_path: Path | None,
        verbose: bool,
    ) -> Session:
        if fork_source_path and fork_source_path.exists():
            source_session = Session.load(fork_source_path)
            conversation = source_session.get_current_conversation()
            if conversation:
                fork_name = session_name or f"{source_session.name}-fork"
                session = source_session.fork(conversation[-1].id, fork_name)
            else:
                session = self._new_session(
                    session_name or f"{source_session.name}-fork",
                    session_id=session_id,
                )
            if session_id:
                session.id = session_id
            self._session_start_reason = "fork"
            self._previous_session_file = str(fork_source_path)
            return session

        if session_path and session_path.exists():
            session = Session.load(session_path)
            self._session_start_reason = "resume"
            self._previous_session_file = str(session_path)
            if verbose:
                print(f"✓ Loaded session: {session.name}")
            return session

        resolved_session_path = self._resolve_existing_session_path(session_id, session_dir)
        if resolved_session_path and resolved_session_path.exists():
            session = Session.load(resolved_session_path)
            self._session_start_reason = "resume"
            self._previous_session_file = str(resolved_session_path)
            if verbose:
                print(f"✓ Loaded session: {session.name}")
            return session

        return self._new_session(session_name or "coding-session", session_id=session_id)

    def _load_extensions(self) -> None:
        """Load extensions from standard directories."""
        if not self.extension_manager:
            return

        # Standard extension paths
        ext_paths = [
            Path.home() / ".agents" / "extensions",
            Path.home() / ".pi" / "agent" / "extensions",
        ]
        if self.project_trusted:
            ext_paths[:0] = [
                self.workspace / ".agents" / "extensions",
                self.workspace / ".pi" / "extensions",
            ]

        for path in ext_paths:
            if path.exists():
                self.extension_manager.load_from_directory(path)

    def _initialize_extension_manager(self, enable_extensions: bool) -> ExtensionManager | None:
        if not enable_extensions:
            return None
        manager = ExtensionManager(self.agent)
        self.extension_manager = manager
        self._load_extensions()
        return manager

    def _initialize_prompt_manager(self, verbose: bool) -> PromptManager:
        manager = PromptManager()
        self.prompt_manager = manager
        self._load_prompts()
        if verbose and len(manager) > 0:
            print(f"✓ Loaded {len(manager)} prompt templates")
        return manager

    def _skill_paths(self) -> list[Path | str]:
        paths: list[Path | str] = [
            Path.home() / ".agents" / "skills",
            Path.home() / ".pi" / "agent" / "skills",
        ]
        if self.project_trusted:
            paths.extend(
                [
                    self.workspace / ".agents" / "skills",
                    self.workspace / ".pi" / "skills",
                ]
            )
        return paths

    def _load_skills(self) -> None:
        if self.skill_manager is not None:
            self.skill_manager.discover_skills(self._skill_paths())

    def _prompt_paths(self) -> list[Path]:
        paths = [
            Path.home() / ".agents" / "prompts",
            Path.home() / ".pi" / "agent" / "prompts",
        ]
        if self.project_trusted:
            paths.extend(
                [
                    self.workspace / ".agents" / "prompts",
                    self.workspace / ".pi" / "prompts",
                ]
            )
        return paths

    def _load_prompts(self) -> None:
        if self.prompt_manager is None:
            return
        for directory in self._prompt_paths():
            if not directory.exists():
                continue
            for template_file in directory.glob("*.md"):
                if not template_file.name.startswith("_"):
                    self.prompt_manager.load_template(template_file)

    def add_tool(self, tool: Tool) -> None:
        """Register a tool unless it is excluded for this agent instance."""
        self.agent.add_tool(tool)

    def _prepare_tool(self, tool: Tool) -> Tool | None:
        """Apply exclusions and permission guards to host-provided tools."""
        if tool.name in self.excluded_tools:
            return None
        return self._guard_extension_tool(tool)

    def _guard_extension_tool(self, tool: Tool) -> Tool:
        """Apply the agent policy to side-effectful extension tool names."""
        if tool.name not in SIDE_EFFECTFUL_TOOL_NAMES:
            return tool

        original = tool.func

        def authorize(arguments: dict[str, Any]) -> ToolResult | None:
            target_key = "command" if tool.name == "run_command" else "path"
            target_value = arguments.get(target_key, arguments.get("target"))
            if target_value is None and arguments:
                target_value = next(iter(arguments.values()))
            target = str(target_value if target_value is not None else tool.name)
            return self.permission_policy.authorize(
                tool.name,
                target,
                arguments=dict(arguments),
            )

        if inspect.iscoroutinefunction(original):

            @wraps(original)
            async def guarded_async(**kwargs: Any) -> Any:
                denial = authorize(kwargs)
                if denial is not None:
                    return denial
                return await original(**kwargs)

            guarded = guarded_async

        else:

            @wraps(original)
            def guarded_sync(**kwargs: Any) -> Any:
                denial = authorize(kwargs)
                if denial is not None:
                    return denial
                return original(**kwargs)

            guarded = guarded_sync

        tool_kwargs: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "params_model": tool.params_model,
        }
        supported = inspect.signature(Tool).parameters
        for field in ("strict_json", "grammar", "deferred"):
            if field in supported:
                tool_kwargs[field] = getattr(tool, field, False if field == "deferred" else None)
        return Tool(guarded, **tool_kwargs)

    @property
    def ui(self) -> InteractionUI:
        assert self.interaction_runtime.ui is not None
        return self.interaction_runtime.ui

    @ui.setter
    def ui(self, value: InteractionUI) -> None:
        self.interaction_runtime.set_ui(value)
        if hasattr(self, "agent"):
            self.agent.ui = value

    def _shutdown_extensions(self, reason: str) -> None:
        """Forward shutdown reason into extension cleanup lifecycle."""
        if not self.extension_manager:
            return
        if self._extensions_shutdown_done:
            return
        self._extensions_shutdown_done = True
        try:
            self.extension_manager.cleanup(reason=reason)
        except Exception:
            pass

    def _get_system_prompt(self) -> str:
        """Get system prompt for coding agent."""
        # Default prompt
        default_prompt = f"""\
You are an expert coding assistant with access to file operations and code generation tools.

Workspace: {self.workspace}

You can:
- Read and write files
- Generate and modify code
- Execute shell commands
- Analyze and explain code

        Be helpful and precise. Side-effectful tools are protected by a permission policy.
        When generating code, provide clean, well-documented, production-ready code.
        """

        # Build with context files
        prompt = self.context_manager.build_system_prompt(default_prompt)

        # Add skills information if available
        if self.skill_manager and len(self.skill_manager) > 0:
            skills_prompt = self.skill_manager.get_all_skills_prompt()
            prompt += f"\n\n{skills_prompt}"

        return prompt

    def _build_interactive_permission_policy(self) -> PermissionPolicy:
        """Create the default interactive permission policy."""

        def confirm(request: PermissionRequest) -> bool:
            question = f"Allow {request.action} on {request.target}?"
            runtime = self.__dict__.get("interaction_runtime")
            if not isinstance(runtime, InteractionRuntime):
                return False
            terminal_runtime = runtime._build_terminal_runtime()
            return terminal_runtime.confirm(question, default=False)

        return PermissionPolicy.confirm_all(confirm)

    def run_interactive(self) -> None:
        """Run interactive chat session."""
        self.interactive_mode.run_interactive()

    async def _run_turn(self, user_input: str) -> None:
        """Stream one agent turn through the dedicated interaction runtime."""
        await self.interactive_mode.run_turn(user_input)

    def _handle_command(self, command: str) -> None:
        """Delegate slash commands to the dedicated interaction runtime."""
        self.interaction_runtime.handle_command(command)

    def _list_workspace_files(self) -> str:
        return FileTools(
            str(self.workspace),
            permission_policy=self.permission_policy,
        ).list_files()

    def _session_manager(self) -> SessionManager:
        return SessionManager(self.workspace, session_dir=self.sessions_dir)

    @staticmethod
    def _copy_to_clipboard(text: str) -> bool:
        import shutil
        import subprocess
        import sys

        if sys.platform == "darwin":
            candidates = [["pbcopy"]]
        elif sys.platform == "win32":
            candidates = [["clip"]]
        else:
            candidates = [
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]
        for cmd in candidates:
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                    return True
                except Exception:
                    continue
        return False

    # Runtime-backed project config keys settable via `/settings <key> <value>`.
    _EDITABLE_SETTINGS = (
        "auto_compact",
        "auto_compact_threshold",
    )

    def run_once(self, message: str) -> str:
        """Run agent with a single message.

        Args:
            message: User message

        Returns:
            Agent response
        """
        return self.run_once_result(message).content

    def run_once_result(self, message: str) -> AgentTurnResult:
        """Run one turn and preserve permission denials across the model boundary."""
        self.permission_policy.consume_denials()
        if self.session:
            self.session.add_message("user", message)
        response = self.agent.run(message)
        denials = tuple(self.permission_policy.consume_denials())
        content = format_permission_denial(denials[0]) if denials else response.content
        if self.session:
            self.session.add_message("assistant", content)
        return AgentTurnResult(content=content, permission_denials=denials)
