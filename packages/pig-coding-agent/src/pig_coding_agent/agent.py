"""Coding agent with file operations and code generation."""

import asyncio
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
from pig_llm import LLM, Message
from pig_tui import ChatUI, InteractivePrompt, LiveInputListener, hyperlink

from .billing import CostTracker
from .config import ConfigManager
from .file_reference import FileReferenceParser
from .resilience import create_profile_manager_from_env, get_profile_status
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
        """
        self.workspace = Path(workspace).resolve()
        self.llm = llm or LLM()
        self.verbose = verbose
        self.excluded_tools = set(excluded_tools or set())
        self._extensions_shutdown_done = False
        self.config_manager = ConfigManager(self.workspace)
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

        # Initialize session
        if fork_source_path and fork_source_path.exists():
            source_session = Session.load(fork_source_path)
            conversation = source_session.get_current_conversation()
            if conversation:
                fork_name = session_name or f"{source_session.name}-fork"
                self.session = source_session.fork(conversation[-1].id, fork_name)
            else:
                self.session = Session(
                    name=session_name or f"{source_session.name}-fork",
                    workspace=str(self.workspace),
                    auto_save=True,
                    session_dir=self.sessions_dir,
                )
            if session_id:
                self.session.id = session_id
            self._session_start_reason = "fork"
            self._previous_session_file = str(fork_source_path)
        elif session_path and session_path.exists():
            self.session = Session.load(session_path)
            self._session_start_reason = "resume"
            self._previous_session_file = str(session_path)
            if verbose:
                print(f"✓ Loaded session: {self.session.name}")
        else:
            resolved_session_path = None
            if session_id:
                session_manager = SessionManager(self.workspace, session_dir=session_dir)
                resolved_session_path = session_manager.find_session(session_id)

            if resolved_session_path and resolved_session_path.exists():
                self.session = Session.load(resolved_session_path)
                self._session_start_reason = "resume"
                self._previous_session_file = str(resolved_session_path)
                if verbose:
                    print(f"✓ Loaded session: {self.session.name}")
            else:
                self.session = Session(
                    name=session_name or "coding-session",
                    workspace=str(self.workspace),
                    auto_save=True,
                    session_dir=self.sessions_dir,
                )
                if session_id:
                    self.session.id = session_id

        # Initialize tools (new-registry style: explicit schemas + handlers,
        # registered in bulk on the agent's registry once it exists below).
        coding_schemas, coding_handlers = build_coding_tools(str(self.workspace))

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
            self._rebuild_history_from_session()

        # Initialize extension manager
        self.extension_manager = None
        if enable_extensions:
            self.extension_manager = ExtensionManager(self.agent)
            self._load_extensions()

        # Initialize prompt manager
        self.prompt_manager = PromptManager()
        self.prompt_manager.discover_prompts([])
        if verbose and len(self.prompt_manager) > 0:
            print(f"✓ Loaded {len(self.prompt_manager)} prompt templates")

        # Initialize file reference parser
        self.file_ref_parser = FileReferenceParser(self.workspace)

        # Create UI
        self.ui = ChatUI(title="Coding Agent", show_timestamps=False)
        self.agent.ui = self.ui

        if self.extension_manager:
            event = {"reason": self._session_start_reason}
            if self._previous_session_file is not None:
                event["previousSessionFile"] = self._previous_session_file
            self.extension_manager.emit_event("session_start", event)

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

    def add_tool(self, tool: Tool) -> None:
        """Register a tool unless it is excluded for this agent instance."""
        if tool.name in self.excluded_tools:
            return
        Agent.add_tool(self.agent, tool)

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

Be helpful, precise, and always confirm destructive operations.
When generating code, provide clean, well-documented, production-ready code.
"""

        # Build with context files
        prompt = self.context_manager.build_system_prompt(default_prompt)

        # Add skills information if available
        if self.skill_manager and len(self.skill_manager) > 0:
            skills_prompt = self.skill_manager.get_all_skills_prompt()
            prompt += f"\n\n{skills_prompt}"

        return prompt

    # Base slash commands for tab completion
    BASE_COMMANDS = [
        "/help",
        "/exit",
        "/quit",
        "/clear",
        "/files",
        "/status",
        "/tree",
        "/fork",
        "/compact",
        "/session",
        "/sessions",
        "/skills",
        "/extensions",
        "/prompts",
        "/reload",
        "/config",
        "/queue",
        "/export",
        "/share",
        "/model",
        "/login",
        "/logout",
        "/resilience",
        "/cost",
        "/usage",
        "/new",
        "/resume",
        "/clone",
        "/name",
        "/import",
        "/copy",
        "/settings",
    ]

    def _build_commands(self) -> list[str]:
        """Build full command list including dynamic /skill: entries."""
        commands = list(self.BASE_COMMANDS)
        if self.skill_manager:
            for skill in self.skill_manager.list_skills():
                commands.append(f"/skill:{skill.name}")
        if self.prompt_manager:
            for name in self.prompt_manager.list_templates():
                commands.append(f"/{name}")
        return commands

    def run_interactive(self) -> None:
        """Run interactive chat session."""
        self.ui.system(f"Workspace: {self.workspace}")
        self.ui.separator()
        shutdown_reason = "normal"

        # One event loop for the whole session. Per-turn asyncio.run() would
        # create+close a loop each turn, but some provider SDKs (e.g. google
        # genai) cache an httpx client bound to the first loop and then fail
        # with "Event loop is closed" on the next turn.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Set up interactive prompt with completion and history
        history_file = str(self.sessions_dir / ".input_history")
        prompt = InteractivePrompt(
            commands=self._build_commands(),
            workspace=str(self.workspace),
            history_file=history_file,
        )

        try:
            while True:
                # Show queue status if messages queued
                if self.agent.message_queue:
                    queue_status = self.agent.message_queue.get_status()
                    if "Queued" in queue_status:
                        self.ui.system(f"📬 {queue_status}")

                # Get user input with tab completion
                try:
                    user_input = prompt.ask("You> ")
                except KeyboardInterrupt:
                    shutdown_reason = "interrupt"
                    break
                except EOFError:
                    shutdown_reason = "eof"
                    break

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # Check for queue commands
                if user_input.startswith("!"):
                    # !message = steering (interrupt)
                    steering_msg = user_input.lstrip("!")
                    self.agent.message_queue.add_steering(steering_msg)
                    self.ui.system(f"⚡ Queued steering message: {steering_msg[:50]}...")
                    continue

                if user_input.startswith(">>"):
                    # >>message = follow-up (wait until done)
                    followup_msg = user_input.lstrip(">").strip()
                    self.agent.message_queue.add_followup(followup_msg)
                    self.ui.system(f"📝 Queued follow-up message: {followup_msg[:50]}...")
                    continue

                # Check for file references
                if "@" in user_input:
                    preview = self.file_ref_parser.get_reference_preview(user_input)
                    if preview:
                        self.ui.system(preview)

                        # Expand references
                        expanded_input = self.file_ref_parser.expand_references(user_input)

                        # Show expansion if significant
                        if len(expanded_input) > len(user_input) + 100:
                            added = len(expanded_input) - len(user_input)
                            self.ui.system(f"→ Added {added} chars from files")

                        # Use expanded input
                        user_input = expanded_input

                # Display user message
                self.ui.user(user_input[:200] + "..." if len(user_input) > 200 else user_input)

                # Run the turn as a cancellable streaming task (uncapped, live
                # tokens, Esc to abort, type-to-steer). Ctrl-C during a turn aborts
                # that turn and returns to the prompt, preserving the session.
                cost_before = self._total_cost()
                try:
                    loop.run_until_complete(self._run_turn(user_input))
                except KeyboardInterrupt:
                    self.ui.system("[aborted]")
                    continue

                # Show context-window usage + cost for the turn, and auto-compact
                # before the context fills up.
                self._show_turn_status(cost_before)
                self._maybe_auto_compact()

        except SessionExitRequested:
            shutdown_reason = "normal"
        except KeyboardInterrupt:
            shutdown_reason = "interrupt"
        except RuntimeError as exc:
            if "lost terminal" in str(exc).lower():
                shutdown_reason = "lost_terminal"
            raise
        finally:
            self._shutdown_extensions(shutdown_reason)

            # Clean up queued messages
            if self.agent.message_queue:
                cleared = self.agent.message_queue.clear()
                if cleared:
                    self.ui.system(f"\nCleared {len(cleared)} queued messages")
            # Always surface the resume command on exit (however the user left),
            # like Claude Code — the session is auto-saved as messages arrive.
            if self.session:
                session_dir_hint = ""
                if self.sessions_dir != self.workspace / ".sessions":
                    session_dir_hint = f" --session-dir {self.sessions_dir}"
                self.ui.system(
                    f"💾 Session saved. Resume with:  "
                    f"piggy --session-id {self.session.id}{session_dir_hint}"
                )
                self.ui.system("(or piggy --continue to resume the most recent session)")
            self.ui.system("Goodbye!")

            # Tear down the session event loop (and any provider clients bound
            # to it) cleanly.
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    async def _run_turn(self, user_input: str) -> None:
        """Stream one agent turn: live tokens, Esc-abort, type-to-steer.

        Drives the cancellable streaming loop (uncapped). A LiveInputListener
        watches the keyboard during the turn — Esc sets the cancel event
        (aborting the turn and killing any in-flight tool), and a typed line is
        injected as a steering message before the next model call. The session
        records the user message plus whatever assistant text was produced
        (including a partial turn on abort).
        """
        cancel = asyncio.Event()
        parts: list[str] = []

        def on_steering(line: str) -> None:
            self.agent.message_queue.add_steering(line)
            # Lightweight ack on submit so the typed line isn't lost; the core
            # loop prints the full "⚡ Steering: …" when it actually injects it.
            self.ui.system(f"  ↳ queued: {line[:60]}")

        # The Markdown Live owns the screen; render the typed steering buffer
        # inside it (echo=False) so there's always a visible "You ›" input line
        # and the user's keystrokes show without fighting the Live cursor.
        with self.ui.assistant_stream_markdown() as writer:
            async with LiveInputListener(
                cancel,
                on_steering=on_steering,
                on_change=writer.set_input,
                completions=self._build_commands(),
                echo=False,
            ):
                # Animate the spinner / elapsed timer while the turn runs so a
                # long LLM or tool wait with no output still looks alive.
                async def _tick() -> None:
                    while True:
                        await asyncio.sleep(0.4)
                        writer.tick()

                ticker = asyncio.create_task(_tick())
                try:
                    async for chunk in self.agent.respond_stream(
                        user_input, cancel=cancel, max_iterations=0
                    ):
                        parts.append(chunk)
                        writer.write(chunk)
                finally:
                    ticker.cancel()

        if cancel.is_set():
            self.ui.system("[aborted]")

        if self.session:
            self.session.add_message("user", user_input)
            full = "".join(parts)
            if full:
                self.session.add_message("assistant", full)

    def _handle_command(self, command: str) -> None:
        """Handle slash commands.

        Args:
            command: Command string
        """
        cmd = command.lower().strip()

        if cmd == "/exit" or cmd == "/quit":
            raise SessionExitRequested()

        elif cmd == "/clear":
            self.agent.clear_history()
            self.ui.clear()
            self.ui.system("Conversation cleared")

        elif cmd == "/help":
            self.ui.panel(
                """
**Available Commands:**

/help       - Show this help
/exit       - Exit the agent
/clear      - Clear conversation
/files      - List files in workspace
/status     - Show agent status

**Tools Available:**
- read_file, write_file, list_files
- generate_code, explain_code
- run_command, git_status, git_diff
            """,
                title="Help",
            )

        elif cmd == "/files":
            files = FileTools(str(self.workspace)).list_files()
            self.ui.panel(files, title="Files")

        elif cmd == "/status":
            self.ui.panel(
                f"""
**Agent Status**

Model: {self.agent.llm.config.model}
Workspace: {self.workspace}
Messages: {len(self.agent.history)}
Tools: {len(self.agent.registry)}
            """,
                title="Status",
            )

        elif cmd.startswith("/tree"):
            self._show_tree()

        elif cmd.startswith("/fork"):
            parts = cmd.split(maxsplit=1)
            fork_name = parts[1] if len(parts) > 1 else None
            self._fork_session(fork_name)

        elif cmd.startswith("/compact"):
            parts = cmd.split(maxsplit=1)
            instructions = parts[1] if len(parts) > 1 else None
            self._compact_session(instructions)

        elif cmd.startswith("/session"):
            self._show_session_info()

        elif cmd.startswith("/sessions"):
            self._list_sessions()

        elif cmd.startswith("/skill:"):
            skill_name = cmd.split(":", 1)[1]
            self._invoke_skill(skill_name)

        elif cmd.startswith("/skills"):
            self._list_skills()

        elif cmd.startswith("/extensions"):
            self._list_extensions()

        elif cmd.startswith("/prompts"):
            self._list_prompts()

        elif cmd.startswith("/reload"):
            self._reload_resources()

        elif cmd.startswith("/config"):
            self._show_config()

        elif cmd.startswith("/queue"):
            self._show_queue()

        elif cmd.startswith("/export"):
            parts = cmd.split(maxsplit=1)
            filename = parts[1] if len(parts) > 1 else None
            self._export_session(filename)

        elif cmd.startswith("/share"):
            self._share_session()

        elif cmd.startswith("/model"):
            parts = cmd.split(maxsplit=1)
            new_model = parts[1] if len(parts) > 1 else None
            self._switch_model(new_model)

        elif cmd.startswith("/login"):
            self._login()

        elif cmd.startswith("/logout"):
            parts = cmd.split(maxsplit=1)
            provider = parts[1] if len(parts) > 1 else None
            self._logout(provider)

        elif cmd.startswith("/resilience"):
            self._show_resilience_status()

        elif cmd.startswith("/cost"):
            self._show_cost_summary(title="Cost")

        elif cmd.startswith("/usage"):
            self._show_cost_summary(title="Usage")

        elif cmd.startswith("/new"):
            self._new_session()

        elif cmd.startswith("/resume"):
            # case-preserving arg (session name or id)
            arg = command.strip().split(maxsplit=1)
            self._resume_session(arg[1].strip() if len(arg) > 1 else None)

        elif cmd.startswith("/clone"):
            self._clone_session()

        elif cmd.startswith("/name"):
            arg = command.strip().split(maxsplit=1)
            self._name_session(arg[1].strip() if len(arg) > 1 else None)

        elif cmd.startswith("/import"):
            arg = command.strip().split(maxsplit=1)
            self._import_session(arg[1].strip() if len(arg) > 1 else None)

        elif cmd.startswith("/copy"):
            self._copy_last_message()

        elif cmd.startswith("/settings"):
            arg = command.strip().split(maxsplit=1)
            self._show_settings(arg[1].strip() if len(arg) > 1 else None)

        elif cmd.startswith("/"):
            # Check if it's a prompt template
            template_name = cmd.lstrip("/").split()[0]
            if self.prompt_manager and template_name in self.prompt_manager:
                # Extract variables from rest of command
                args_str = cmd.split(maxsplit=1)[1] if " " in cmd else ""
                self._expand_prompt(template_name, args_str)
                return

            # Try extension commands
            if self.extension_manager:
                ext_cmd = cmd.lstrip("/").split()[0]
                cmd_args = cmd.split(maxsplit=1)[1] if " " in cmd else None
                try:
                    result = self.extension_manager.handle_command(ext_cmd, cmd_args)
                    self.ui.panel(str(result), title=f"/{ext_cmd}")
                    return
                except (ValueError, KeyError):
                    pass

            self.ui.error(f"Unknown command: {command}")

    def _show_tree(self):
        """Show session tree."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        tree_text = "**Session Tree**\n\n"
        path = self.session.get_current_conversation()

        for i, entry in enumerate(path):
            indent = "  " * min(i, 5)
            preview = entry.content[:60].replace("\n", " ")
            tree_text += f"{indent}• [{entry.role}] {preview}...\n"

        tree_text += f"\nTotal entries: {len(self.session.tree.entries)}"
        tree_text += f"\nCurrent path: {len(path)}"
        self.ui.panel(tree_text, title="Session Tree")

    def _fork_session(self, fork_name: str | None):
        """Fork current session."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        conversation = self.session.get_current_conversation()
        if not conversation:
            self.ui.error("No messages to fork")
            return

        # Fork from last message
        name = fork_name or f"{self.session.name}-fork"
        previous_session_file = self.session.save()
        fork = self.session.fork(conversation[-1].id, name)
        save_path = fork.save()
        if self.extension_manager:
            self.extension_manager.cleanup(
                reason="fork",
                target_session_file=str(previous_session_file),
            )

        self.session = fork
        self.agent.session = self.session

        if self.extension_manager:
            self._load_extensions()
            self.extension_manager.emit_event(
                "session_start",
                {"reason": "fork", "previousSessionFile": str(previous_session_file)},
            )

        self.ui.system(f"✓ Forked session: {name}")
        self.ui.system(f"  Copied {len(fork.tree.entries)} entries")
        self.ui.system(f"  Saved to: {save_path}")

    def _rebuild_history_from_session(self) -> None:
        """Replay the active session's conversation into the agent's LLM context.

        The session tree and the agent's in-memory history are separate stores;
        switching sessions (resume/import/new/clone) must rebuild the context so
        the model actually sees the loaded conversation.
        """
        system = None
        if self.agent.history and self.agent.history[0].role == "system":
            system = self.agent.history[0]
        history: list[Message] = []
        if system is not None:
            history.append(system)
        if self.session:
            for entry in self.session.get_current_conversation():
                # Skip plain system entries (the agent's own system prompt is
                # already first); keep compacted summaries as context.
                if entry.role == "system" and not (entry.metadata or {}).get("compacted"):
                    continue
                history.append(
                    Message(
                        role=entry.role,
                        content=entry.content,
                        metadata=entry.metadata or None,
                    )
                )
        self.agent.history = history

    def _switch_to_session(self, new_session: Session, reason: str) -> None:
        """Persist the current session, swap to ``new_session``, and run the
        extension lifecycle + context rebuild (shared by new/resume/clone/import).
        """
        previous_session_file = str(self.session.save()) if self.session else None
        if self.extension_manager:
            self.extension_manager.cleanup(reason=reason, target_session_file=previous_session_file)
        self.session = new_session
        self.agent.session = self.session
        self._rebuild_history_from_session()
        if self.extension_manager:
            self._load_extensions()
            self.extension_manager.emit_event(
                "session_start",
                {"reason": reason, "previousSessionFile": previous_session_file},
            )

    def _new_session(self) -> None:
        """Start a fresh session, leaving the current one saved on disk."""
        new_session = Session(
            name="coding-session",
            workspace=str(self.workspace),
            auto_save=True,
            session_dir=self.sessions_dir,
        )
        self._switch_to_session(new_session, reason="new")
        self.ui.system(f"✓ Started a new session: {new_session.id}")

    def _resume_session(self, name_or_id: str | None) -> None:
        """Switch to a different saved session by name or id."""
        if not name_or_id:
            self._list_sessions()
            self.ui.system("Resume one with: /resume <session-id-or-name>")
            return
        session_mgr = SessionManager(self.workspace, session_dir=self.sessions_dir)
        path = session_mgr.find_session(name_or_id)
        if not path or not path.exists():
            self.ui.error(f"Session not found: {name_or_id}")
            return
        try:
            loaded = Session.load(path)
        except Exception as e:
            self.ui.error(f"Failed to load session: {e}")
            return
        self._switch_to_session(loaded, reason="resume")
        self.ui.system(f"✓ Resumed session: {loaded.name} ({loaded.id})")
        self.ui.system(f"  {len(self.agent.history)} messages restored")

    def _clone_session(self) -> None:
        """Duplicate the current session at its current position."""
        if not self.session:
            self.ui.error("No session loaded")
            return
        conversation = self.session.get_current_conversation()
        if not conversation:
            self.ui.error("No messages to clone")
            return
        clone = self.session.fork(conversation[-1].id, f"{self.session.name}-clone")
        save_path = clone.save()
        self._switch_to_session(clone, reason="fork")
        self.ui.system(f"✓ Cloned session: {clone.name} ({clone.id})")
        self.ui.system(f"  Saved to: {save_path}")

    def _name_session(self, name: str | None) -> None:
        """Set the current session's display name."""
        if not self.session:
            self.ui.error("No session loaded")
            return
        if not name:
            self.ui.system(f"Current session name: {self.session.name}")
            self.ui.system("Set it with: /name <display name>")
            return
        self.session.name = name
        self.session.save()
        self.ui.system(f"✓ Session renamed to: {name}")

    def _import_session(self, file_path: str | None) -> None:
        """Import a session from a JSONL file and resume it."""
        if not file_path:
            self.ui.error("Usage: /import <path-to-session.jsonl>")
            return
        path = Path(file_path).expanduser()
        if not path.exists():
            self.ui.error(f"File not found: {path}")
            return
        try:
            loaded = Session.load(path)
        except Exception as e:
            self.ui.error(f"Failed to import session: {e}")
            return
        # Re-home into our sessions dir so the import is tracked and resumable.
        loaded.session_dir = self.sessions_dir
        loaded._save_path = None
        save_path = loaded.save()
        self._switch_to_session(loaded, reason="resume")
        self.ui.system(f"✓ Imported session: {loaded.name} ({loaded.id})")
        self.ui.system(f"  Saved to: {save_path}")
        self.ui.system(f"  {len(self.agent.history)} messages restored")

    def _copy_last_message(self) -> None:
        """Copy the last assistant reply to the system clipboard."""
        last = None
        for msg in reversed(self.agent.history):
            if msg.role == "assistant" and msg.content:
                last = msg.content
                break
        if not last:
            self.ui.error("No assistant message to copy")
            return
        if self._copy_to_clipboard(last):
            self.ui.system(f"✓ Copied last reply to clipboard ({len(last)} chars)")
        else:
            self.ui.error("Clipboard not available (install pbcopy/xclip/wl-copy)")

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

    # Config keys settable via `/settings <key> <value>`.
    _EDITABLE_SETTINGS = (
        "auto_compact",
        "auto_compact_threshold",
        "temperature",
        "verbose",
        "show_timestamps",
        "theme",
        "auto_save_session",
        "enable_cost_tracking",
    )

    def _show_settings(self, args: str | None = None) -> None:
        """Show settings, or set one with `/settings <key> <value>`."""
        if args:
            self._set_setting(args)
            return

        cfg = self.config_manager.load_config()
        lines = [
            "**Settings**",
            "",
            f"Model:       {self.agent.llm.config.provider}/{self.agent.llm.config.model}",
            f"Workspace:   {self.workspace}",
            f"Session dir: {self.sessions_dir}",
            f"Skills:      {'on' if self.skill_manager else 'off'}",
            f"Extensions:  {'on' if self.extension_manager else 'off'}",
            "",
            "**Editable** (`/settings <key> <value>`):",
        ]
        for key in self._EDITABLE_SETTINGS:
            lines.append(f"  {key} = {getattr(cfg, key, '?')}")
        lines += [
            "",
            "**Config files:**",
            f"  project: {self.config_manager.project_config}",
            f"  global:  {self.config_manager.global_config}",
            "",
            "Also: /model <provider/model>, /login, /logout, /name <name>",
        ]
        self.ui.panel("\n".join(lines), title="Settings")

    def _set_setting(self, args: str) -> None:
        """Parse and persist `<key> <value>` into the project config."""
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self.ui.error("Usage: /settings <key> <value>")
            return
        key, raw = parts[0], parts[1].strip()
        if key not in self._EDITABLE_SETTINGS:
            self.ui.error(
                f"Unknown or read-only setting: {key}. "
                f"Editable: {', '.join(self._EDITABLE_SETTINGS)}"
            )
            return

        current = getattr(self.config_manager.load_config(), key, None)
        try:
            if isinstance(current, bool):
                value: object = raw.lower() in ("1", "true", "yes", "on")
            elif isinstance(current, int) and not isinstance(current, bool):
                value = int(raw)
            elif isinstance(current, float):
                value = float(raw)
            else:
                value = raw
        except ValueError:
            self.ui.error(f"Invalid value for {key}: {raw!r}")
            return

        if key == "auto_compact_threshold" and not (0.0 <= float(value) <= 1.0):
            self.ui.error("auto_compact_threshold must be between 0.0 and 1.0")
            return

        self.config_manager.set_config_value(key, value)
        self.ui.system(f"✓ {key} = {value}  (saved to {self.config_manager.project_config})")
        if key not in ("auto_compact", "auto_compact_threshold"):
            self.ui.system("  (applies on next launch)")

    # Approximate context-window sizes by model-name substring (longest match wins).
    _CONTEXT_WINDOWS = {
        "gpt-4.1": 1_000_000,
        "gpt-4o": 128_000,
        "o1": 200_000,
        "o3": 200_000,
        "o4": 200_000,
        "claude": 200_000,
        "gemini-1.5": 1_000_000,
        "gemini-2": 1_000_000,
        "gemini-3": 1_000_000,
        "deepseek": 128_000,
        "llama": 128_000,
        "mixtral": 32_000,
        "qwen": 128_000,
        "grok": 128_000,
    }
    _DEFAULT_CONTEXT_WINDOW = 128_000

    def _context_window(self) -> int:
        model = self.agent.llm.config.model or ""
        # Prefer the generated model registry (real per-model context windows).
        from pig_llm import get_model_info

        info = get_model_info(model)
        if info is not None:
            return int(info["context_window"])
        # Fall back to a coarse substring table, then a default.
        lowered = model.lower()
        best = None
        for key, window in self._CONTEXT_WINDOWS.items():
            if key in lowered and (best is None or len(key) > len(best[0])):
                best = (key, window)
        return best[1] if best else self._DEFAULT_CONTEXT_WINDOW

    def _context_tokens(self) -> int | None:
        usage = self.agent.last_llm_usage
        if not usage:
            return None
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))

    @staticmethod
    def _fmt_k(n: int) -> str:
        return f"{n / 1000:.0f}k" if n >= 1000 else str(n)

    def _total_cost(self) -> float:
        if not self.cost_tracker:
            return 0.0
        try:
            return float(self.cost_tracker.get_usage_summary().get("total_cost", 0.0))
        except Exception:
            return 0.0

    def _show_turn_status(self, cost_before: float) -> None:
        """After a turn, show context-window usage and cost (delta + total)."""
        parts: list[str] = []
        ctx = self._context_tokens()
        if ctx is not None:
            window = self._context_window()
            pct = (ctx / window * 100) if window else 0
            parts.append(f"context {self._fmt_k(ctx)}/{self._fmt_k(window)} ({pct:.0f}%)")
        if self.cost_tracker:
            total = self._total_cost()
            delta = total - cost_before
            parts.append(f"+${delta:.4f} (total ${total:.4f})")
        if parts:
            self.ui.system(" · ".join(parts))

    def _maybe_auto_compact(self) -> None:
        """Auto-compact when the context window is nearly full (pi-mono parity).

        Controlled by config: auto_compact (on/off) and auto_compact_threshold
        (fraction of the context window, default 0.85).
        """
        cfg = self.config_manager.load_config()
        if not cfg.auto_compact:
            return
        ctx = self._context_tokens()
        if ctx is None:
            return
        window = self._context_window()
        if ctx <= int(window * cfg.auto_compact_threshold):
            return
        self.ui.system(
            f"⚠ Context {self._fmt_k(ctx)}/{self._fmt_k(window)} — auto-compacting to free space…"
        )
        try:
            self._compact_session(None)
            # Rebuild the agent's context from the compacted session so the next
            # turn actually sends a smaller prompt (sheds old tool-output bloat).
            self._rebuild_history_from_session()
            # Reset the stale usage estimate so the indicator reflects the compaction.
            self.agent.last_llm_usage = None
        except Exception as e:
            self.ui.error(f"Auto-compaction failed: {e}")

    def _compact_session(self, instructions: str | None):
        """Compact session messages."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        before = len(self.session.tree.entries)
        compacted = self.session.compact(instructions)

        self.ui.system(f"✓ Compacted: {before} entries → {len(compacted)} entries")
        if instructions:
            self.ui.system(f"  Instructions: {instructions}")

    def _list_sessions(self):
        """List available sessions."""
        session_mgr = SessionManager(self.workspace, session_dir=self.sessions_dir)
        sessions = session_mgr.list_sessions(limit=20)

        if not sessions:
            self.ui.system("No sessions found")
            self.ui.system(f"Sessions are saved to: {self.sessions_dir}")
            return

        sessions_text = session_mgr.format_session_list(sessions)

        if len(sessions) == 20:
            sessions_text += "\n\n... (showing most recent 20)"

        self.ui.panel(sessions_text, title=f"Available Sessions ({len(sessions)})")
        self.ui.system("Use `piggy --resume` to select a session")

    def _show_session_info(self):
        """Show session information."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        info = self.session.get_info()
        info_text = f"""
**Session Information**

ID: {info["id"][:8]}...
Name: {info["name"]}
Created: {info["created_at"][:19]}
Updated: {info["updated_at"][:19]}

Entries: {info["entries"]}
Current path: {info["current_path_length"]}
Branches: {info["branches"]}

Tokens: {info["metadata"].get("tokens_used", 0)}
Cost: ${info["metadata"].get("cost", 0.0):.4f}
        """
        self.ui.panel(info_text, title="Session")

    def _invoke_skill(self, skill_name: str):
        """Invoke a skill."""
        if not self.skill_manager:
            self.ui.error("Skills not enabled")
            return

        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            self.ui.error(f"Skill '{skill_name}' not found")
            self.ui.system("Use /skills to see available skills")
            return

        # Show skill
        skill_prompt = skill.to_prompt()
        self.ui.panel(skill_prompt, title=f"Skill: {skill_name}")
        self.ui.system("Skill context loaded. Ask your question now.")

    def _list_skills(self):
        """List available skills."""
        if not self.skill_manager:
            self.ui.error("Skills not enabled")
            return

        if len(self.skill_manager) == 0:
            self.ui.system("No skills found")
            self.ui.system("Create skills in .agents/skills/skill-name/SKILL.md")
            return

        skills_text = "**Available Skills**\n\n"
        for skill in self.skill_manager.list_skills():
            skills_text += f"• **{skill.name}**\n"
            skills_text += f"  {skill.description}\n\n"

        skills_text += "Use `/skill:name` to invoke a skill."
        self.ui.panel(skills_text, title=f"Skills ({len(self.skill_manager)})")

    def _list_extensions(self):
        """List loaded extensions."""
        if not self.extension_manager:
            self.ui.error("Extensions not enabled")
            return

        if len(self.extension_manager.extensions) == 0:
            self.ui.system("No extensions loaded")
            self.ui.system("Place extensions in .agents/extensions/")
            return

        ext_text = "**Loaded Extensions**\n\n"
        for name in self.extension_manager.extensions.keys():
            ext_text += f"• {name}\n"

        # List custom commands
        commands = self.extension_manager.api.get_commands()
        if commands:
            ext_text += "\n**Custom Commands**:\n"
            for cmd in commands.keys():
                ext_text += f"• /{cmd}\n"

        # List registered tools count
        ext_text += f"\n**Tools**: {len(self.agent.registry)} total"

        self.ui.panel(ext_text, title=f"Extensions ({len(self.extension_manager.extensions)})")

    def _show_help(self):
        """Show comprehensive help."""
        help_text = """
**Built-in Commands:**

/help       - Show this help
/exit       - Exit agent
/clear      - Clear conversation
/status     - Agent status
/config     - Show configuration
/queue      - Show message queue
/files      - List workspace files

**Session Management:**

/session    - Show current session info
/sessions   - List all available sessions
/tree       - Show conversation tree
/fork [name] - Fork session from current point
/compact [instructions] - Compact old messages
/export [file] - Export session to HTML
/share      - Share session via GitHub Gist
/reload     - Reload extensions, skills, prompts, context

**Skills & Extensions:**

/skills     - List available skills
/skill:name - Invoke a skill
/extensions - List loaded extensions
/prompts    - List prompt templates
/template   - Expand a template

**Model & Auth:**

/model [provider/model] - Switch LLM model
/login      - OAuth login (subscription accounts)
/logout <provider> - Logout from provider

**Context Files:**

• AGENTS.md - Project instructions (auto-loaded)
• SYSTEM.md - Override system prompt
• APPEND_SYSTEM.md - Append to system prompt

**Message Queue:**

While agent is working, you can queue messages:
  !message     - Steering (interrupt after current tool)
  >>message    - Follow-up (wait until agent finishes)

Use /queue to see queued messages.

**File References:**

Use @filename to auto-include file contents:
  @src/main.py - Include main.py in your message
  @README.md - Include README
  @test.py and @utils.py - Multiple files

Files are automatically read and added to context!

**Features:**

• Sessions auto-save to the resolved session directory
• Extensions auto-load from .agents/extensions/
• Skills auto-discover from .agents/skills/
• Prompts auto-load from .agents/prompts/
• Context auto-load from AGENTS.md, SYSTEM.md
• Use /tree to navigate conversation history
• Use /fork to create alternate branches
• Queue messages with ! or >>
        """
        self.ui.panel(help_text, title="Help")

    def _list_prompts(self):
        """List available prompt templates."""
        if not self.prompt_manager or len(self.prompt_manager) == 0:
            self.ui.system("No prompts found")
            self.ui.system("Create prompts in .agents/prompts/*.md")
            return

        prompts_text = "**Available Prompt Templates**\n\n"
        for template in self.prompt_manager.list_templates():
            prompts_text += f"• **/{template.name}**\n"
            if template.variables:
                prompts_text += f"  Variables: {', '.join(template.variables)}\n"
            # Show first line as description
            first_line = template.content.split("\n")[0].strip("# ").strip()
            prompts_text += f"  {first_line}\n\n"

        prompts_text += "Use `/template_name` to expand a template."
        self.ui.panel(prompts_text, title=f"Prompts ({len(self.prompt_manager)})")

    def _expand_prompt(self, template_name: str, args: str):
        """Expand a prompt template.

        Args:
            template_name: Template name
            args: Arguments string (key=value format)
        """
        template = self.prompt_manager.get_template(template_name)
        if not template:
            self.ui.error(f"Template '{template_name}' not found")
            return

        # Parse arguments (simple key=value parsing)
        kwargs = {}
        if args:
            # Support both space and comma separated
            parts = args.replace(",", " ").split()
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    # Remove quotes if present
                    value = value.strip("\"'")
                    kwargs[key] = value

        # Show template info if no args and has variables
        if template.variables and not kwargs:
            vars_text = "**Template Variables**:\n\n"
            for var in template.variables:
                vars_text += f"• {var}\n"
            usage_args = " ".join(f"{v}=value" for v in template.variables)
            vars_text += f"\n**Usage**: `/{template_name} {usage_args}`"
            vars_text += f'\n\n**Example**: `/{template_name} {template.variables[0]}="example"`'
            self.ui.panel(vars_text, title=f"Template: {template_name}")
            return

        # Render template
        rendered = template.render(**kwargs)

        # Display nicely
        self.ui.panel(rendered, title=f"Expanded: /{template_name}")

        # Automatically send to agent
        self.ui.system("Sending prompt to agent...")

        # Add to session
        if self.session:
            self.session.add_message("user", rendered)

        # Get response
        response = self.agent.run(rendered)

        # Display response
        self.ui.assistant(response.content)

    def _export_session(self, filename: str | None):
        """Export session to HTML."""
        if not self.session:
            self.ui.error("No session to export")
            return

        from pathlib import Path

        from pig_agent_core import SessionExporter

        # Determine output path
        if filename:
            output_path = Path(filename)
        else:
            # Auto-generate
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"{self.session.name}_{timestamp}.html")

        try:
            exported = SessionExporter.export_to_html(
                self.session, output_path, title=self.session.name
            )
            self.ui.system(f"✓ Exported to: {exported}")
            export_url = f"file://{exported.absolute()}"
            self.ui.system(f"  Open in browser: {hyperlink(str(exported.absolute()), export_url)}")
        except Exception as e:
            self.ui.error(f"Export failed: {e}")

    def _switch_model(self, model_name: str | None):
        """Switch LLM model.

        Args:
            model_name: New model name (format: provider/model)
        """
        if not model_name:
            # Show current model
            current = f"{self.agent.llm.config.provider}/{self.agent.llm.config.model}"
            self.ui.panel(
                f"""
**Current Model**

Provider: {self.agent.llm.config.provider}
Model: {self.agent.llm.config.model}
Full: {current}

**Switch Model**:
  /model openai/gpt-4
  /model anthropic/claude-3-sonnet
  /model groq/llama-3.1-70b

**Available Providers**:
  openai, anthropic, google, azure, groq,
  mistral, openrouter, bedrock, xai, cerebras,
  cohere, perplexity, deepseek, together
            """,
                title="Model",
            )
            return

        # Parse provider/model
        if "/" in model_name:
            provider, model = model_name.split("/", 1)
        else:
            # Assume same provider
            provider = self.agent.llm.config.provider
            model = model_name

        try:
            # Create new LLM
            from pig_llm import LLM

            new_llm = LLM(provider=provider, model=model)

            # Update agent
            self.agent.llm = new_llm
            self.llm = new_llm

            self.ui.system(f"✓ Switched to {provider}/{model}")

        except Exception as e:
            self.ui.error(f"Failed to switch model: {e}")

    def _login(self):
        """Login to a provider via OAuth."""

        # Supported providers (examples)

        self.ui.panel(
            """
**OAuth Login**

Currently, OAuth login is a framework feature.
Most providers support API keys directly.

For subscription login (Claude Pro, ChatGPT Plus):
- Set up OAuth app in provider console
- Configure client_id/secret in ~/.agents/oauth_providers.json
- Then use /login

For now, use API keys:
  export OPENAI_API_KEY=sk-...
  export ANTHROPIC_API_KEY=sk-ant-...
            """,
            title="OAuth Login",
        )

    def _logout(self, provider: str | None):
        """Logout from a provider.

        Args:
            provider: Provider name
        """
        from pig_agent_core import AuthManager

        if not provider:
            self.ui.error("Usage: /logout <provider>")
            self.ui.system("Example: /logout anthropic")
            return

        auth_mgr = AuthManager()

        if auth_mgr.logout(provider):
            self.ui.system(f"✓ Logged out from {provider}")
        else:
            self.ui.system(f"Not logged in to {provider}")

    def _share_session(self):
        """Share session via GitHub Gist."""
        if not self.session:
            self.ui.error("No session to share")
            return

        import os

        from pig_agent_core import GistSharer

        # Get GitHub token
        github_token = os.getenv("GITHUB_TOKEN")

        if not github_token:
            self.ui.error("GITHUB_TOKEN not set")
            self.ui.system("Get token from: https://github.com/settings/tokens")
            self.ui.system("Set: export GITHUB_TOKEN=your_token")
            return

        try:
            sharer = GistSharer(github_token)

            self.ui.system("Uploading to GitHub Gist...")

            info = sharer.share_session(
                self.session, public=False, description=f"pig-mono: {self.session.name}"
            )

            self.ui.system("✓ Shared as private gist!")
            self.ui.panel(
                f"""
**Gist Created**

URL: {info["url"]}
ID: {info["id"]}
Public: {info["public"]}

Share this URL to give others access.
            """,
                title="Shared",
            )

        except Exception as e:
            self.ui.error(f"Share failed: {e}")

    def _show_queue(self):
        """Show message queue status."""
        queue = self.agent.message_queue

        if not queue:
            self.ui.system("Message queue is empty")
            self.ui.system("\nQueue messages while agent is working:")
            self.ui.system("  !message    - Steering (interrupt after current tool)")
            self.ui.system("  >>message   - Follow-up (wait until done)")
            return

        queue_text = f"**Message Queue** ({len(queue)} messages)\n\n"

        steering = [m for m in queue.queue if m.type.value == "steering"]
        followup = [m for m in queue.queue if m.type.value == "followup"]

        if steering:
            queue_text += "**Steering Messages** (interrupt):\n"
            for i, msg in enumerate(steering, 1):
                preview = msg.content[:60]
                queue_text += f"{i}. {preview}...\n"
            queue_text += "\n"

        if followup:
            queue_text += "**Follow-up Messages** (after completion):\n"
            for i, msg in enumerate(followup, 1):
                preview = msg.content[:60]
                queue_text += f"{i}. {preview}...\n"

        queue_text += "\n**Modes**:\n"
        queue_text += f"• Steering: {queue.steering_mode}\n"
        queue_text += f"• Follow-up: {queue.followup_mode}"

        self.ui.panel(queue_text, title="Queue")

    def _show_config(self):
        """Show current configuration."""
        from .config import ConfigManager

        config_mgr = ConfigManager(self.workspace)
        config = config_mgr.load_config()

        config_text = f"""
**Agent Configuration**

Provider: {config.provider}
Model: {config.model or "default"}
Temperature: {config.temperature}

**Features**

Extensions: {"enabled" if config.enable_extensions else "disabled"}
Skills: {"enabled" if config.enable_skills else "disabled"}
Prompts: {"enabled" if config.enable_prompts else "disabled"}
Context: {"enabled" if config.enable_context else "disabled"}

**Session**

Auto-save: {"yes" if config.auto_save_session else "no"}
Cleanup: {config.session_cleanup_days} days

**Display**

Verbose: {config.verbose}
Theme: {config.theme}

**Config Files**

Global: ~/.agents/config.json
Project: .agents/config.json
        """

        self.ui.panel(config_text, title="Configuration")
        self.ui.system("Edit config files or use environment variables")

    def _reload_resources(self):
        """Reload extensions, skills, prompts, and context."""
        reloaded = []

        # Reload extensions
        if self.extension_manager:
            # Clear and reload
            old_count = len(self.extension_manager.extensions)
            session_file = str(self.session.save()) if self.session else None
            self.extension_manager.cleanup(
                reason="reload",
                target_session_file=session_file,
            )
            self._load_extensions()
            self.extension_manager.emit_event("session_start", {"reason": "reload"})
            new_count = len(self.extension_manager.extensions)
            reloaded.append(f"Extensions: {new_count} (was {old_count})")

        # Reload skills
        if self.skill_manager:
            old_count = len(self.skill_manager)
            self.skill_manager.skills.clear()
            self.skill_manager.discover_skills([])
            new_count = len(self.skill_manager)
            reloaded.append(f"Skills: {new_count} (was {old_count})")

        # Reload prompts
        if self.prompt_manager:
            old_count = len(self.prompt_manager)
            self.prompt_manager.templates.clear()
            self.prompt_manager.discover_prompts([])
            new_count = len(self.prompt_manager)
            reloaded.append(f"Prompts: {new_count} (was {old_count})")

        # Reload system prompt (context files)
        new_prompt = self._get_system_prompt()
        # Update agent's system prompt
        if self.agent.history and self.agent.history[0].role == "system":
            self.agent.history[0].content = new_prompt
            reloaded.append("Context: Reloaded")

        if reloaded:
            self.ui.system("✓ Reloaded resources:")
            for item in reloaded:
                self.ui.system(f"  • {item}")
        else:
            self.ui.system("No resources to reload")

    def _show_status(self):
        """Show comprehensive status."""
        status_text = f"""
**Agent Configuration**

Model: {self.agent.llm.config.model}
Provider: {self.agent.llm.config.provider}
Workspace: {self.workspace}

**Current State**

Messages in history: {len(self.agent.history)}
Tools available: {len(self.agent.registry)}
"""

        if self.session:
            info = self.session.get_info()
            status_text += f"""
**Session**

Name: {self.session.name}
Entries: {info["entries"]}
Current path: {info["current_path_length"]}
Branches: {info["branches"]}
"""

        if self.skill_manager:
            status_text += f"\n**Skills**: {len(self.skill_manager)} loaded"

        if self.extension_manager:
            ext_count = len(self.extension_manager.extensions)
            cmd_count = len(self.extension_manager.api.get_commands())
            status_text += f"\n**Extensions**: {ext_count} loaded, {cmd_count} commands"

        if self.prompt_manager:
            status_text += f"\n**Prompts**: {len(self.prompt_manager)} loaded"

        # Show context files
        agents_md = self.context_manager.find_context_files("AGENTS.md")
        if agents_md:
            status_text += f"\n**Context**: {len(agents_md)} AGENTS.md files"

        self.ui.panel(status_text, title="Status")

    def run_once(self, message: str) -> str:
        """Run agent with a single message.

        Args:
            message: User message

        Returns:
            Agent response
        """
        response = self.agent.run(message)
        return response.content

    def _show_resilience_status(self):
        """Show resilience system status."""
        if not self.profile_manager:
            self.ui.system("Resilience not enabled")
            self.ui.system("\nTo enable resilience:")
            self.ui.system("  1. Set multiple API keys:")
            self.ui.system("     export OPENAI_API_KEY=sk-...")
            self.ui.system("     export OPENAI_API_KEY_2=sk-...")
            self.ui.system("     export ANTHROPIC_API_KEY=sk-ant-...")
            self.ui.system("  2. Restart agent")
            return

        status = get_profile_status(self.profile_manager)

        status_text = f"""
**Resilience Status**

Total API keys: {status["total_profiles"]}
Available: {status["available_profiles"]}
In cooldown: {status["cooldown_profiles"]}

**Profiles:**
"""

        for i, profile in enumerate(status["profiles"], 1):
            provider = profile["provider"]
            key_idx = profile["key_index"]
            available = "✓" if profile["available"] else "✗ (cooldown)"

            status_text += f"\n{i}. {provider} (key #{key_idx}): {available}"

        status_text += "\n\n**Features:**\n"
        status_text += "• Automatic API key rotation on rate limits\n"
        status_text += "• Per-failure-type cooldowns\n"
        status_text += "• Model fallback on context overflow\n"

        self.ui.panel(status_text, title="Resilience")

    def _show_cost_summary(self, title: str = "Usage & Cost"):
        """Show cost/usage tracking summary."""
        if not self.cost_tracker:
            self.ui.system("Cost tracking not enabled")
            return

        summary_text = self.cost_tracker.format_summary()
        self.ui.panel(summary_text, title=title)

        # Show usage file location
        self.ui.system(f"\nUsage data: {self.cost_tracker.usage_file}")
