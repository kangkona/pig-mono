"""Coding agent with file operations and code generation."""

import os
from pathlib import Path

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
from pig_agent_core.tools import Tool
from pig_llm import LLM

from .app_actions import AppActions
from .billing import CostTracker
from .config import ConfigManager
from .file_reference import FileReferenceParser
from .interaction_catalog import InteractionCatalog
from .interaction_runtime import InteractionRuntime
from .interactive_mode import InteractiveMode
from .permissions import PermissionPolicy, PermissionRequest
from .resilience import create_profile_manager_from_env, get_profile_status
from .results import ResultFactory
from .tools import FileTools, build_coding_tools


class SessionExitRequested(Exception):
    """Raised for explicit user-driven session exits like /exit and /quit."""


class CodingAgent:
    """Interactive coding agent with file and code tools."""

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
    ):
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
        """
        self.workspace = Path(workspace).resolve()
        self.llm = llm or LLM()
        self.verbose = verbose
        self.excluded_tools = set(excluded_tools or set())
        self.permission_policy = permission_policy or self._build_interactive_permission_policy()
        self._extensions_shutdown_done = False
        self.config_manager = ConfigManager(self.workspace)
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
        if enable_cost_tracking:
            self.cost_tracker = CostTracker(self.workspace)
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
        self.context_manager = ContextManager(self.workspace)

        # Initialize skill manager
        self.skill_manager = None
        if enable_skills:
            self.skill_manager = SkillManager()
            self.skill_manager.discover_skills([])
            if verbose and len(self.skill_manager) > 0:
                print(f"✓ Loaded {len(self.skill_manager)} skills")

        # Create agent
        self.agent = Agent(
            name="CodingAgent",
            llm=self.llm,
            system_prompt=self._get_system_prompt(),
            verbose=verbose,
            profile_manager=self.profile_manager,
            billing_hook=self.cost_tracker,
            # No iteration cap (pi-mono parity): turns run until natural
            # completion, a terminate tool result, or user abort (Esc/Ctrl-C).
            max_rounds=0,
        )

        # Register the coding tools on the agent's registry, then drop any tools
        # excluded for this agent instance. (Web search is handled natively by
        # the model provider when enabled, not as a locally-dispatched tool.)
        self.agent.registry.register_package(coding_schemas, coding_handlers, is_core=True)
        for name in self.excluded_tools:
            self.agent.registry.unregister(name)

        self.agent.session = self.session
        self.agent.add_tool = self.add_tool

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

    def _load_extensions(self):
        """Load extensions from standard directories."""
        if not self.extension_manager:
            return

        # Standard extension paths
        ext_paths = [
            self.workspace / ".agents" / "extensions",
            self.workspace / ".pi" / "extensions",
            Path.home() / ".agents" / "extensions",
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
        manager.discover_prompts([])
        if verbose and len(manager) > 0:
            print(f"✓ Loaded {len(manager)} prompt templates")
        return manager

    def add_tool(self, tool: Tool) -> None:
        """Register a tool unless it is excluded for this agent instance."""
        if tool.name in self.excluded_tools:
            return
        Agent.add_tool(self.agent, tool)

    @property
    def ui(self):
        return self.interaction_runtime.ui

    @ui.setter
    def ui(self, value) -> None:
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
            runtime = getattr(self, "interaction_runtime", None)
            if runtime is None:
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
        response = self.agent.run(message)
        return response.content
