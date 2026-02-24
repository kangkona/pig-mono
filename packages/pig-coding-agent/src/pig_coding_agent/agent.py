"""Coding agent with file operations and code generation."""

from pathlib import Path
from typing import Optional

from pig_llm import LLM
from pig_agent_core import Agent, Session, ExtensionManager, SkillManager, ContextManager, PromptManager, SessionManager
from pig_agent_core.tools import Tool
from pig_tui import ChatUI, InteractivePrompt

from .tools import FileTools, CodeTools, ShellTools
from .file_reference import FileReferenceParser


class CodingAgent:
    """Interactive coding agent with file and code tools."""

    def __init__(
        self,
        llm: Optional[LLM] = None,
        workspace: str = ".",
        verbose: bool = True,
        session_name: Optional[str] = None,
        session_path: Optional[Path] = None,
        enable_extensions: bool = True,
        enable_skills: bool = True,
    ):
        """Initialize coding agent.

        Args:
            llm: LLM client
            workspace: Working directory
            verbose: Enable verbose output
            session_name: Session name for auto-save
            session_path: Path to load existing session
            enable_extensions: Enable extension system
            enable_skills: Enable skills system
        """
        self.workspace = Path(workspace).resolve()
        self.llm = llm or LLM()
        self.verbose = verbose

        # Initialize session
        if session_path and session_path.exists():
            self.session = Session.load(session_path)
            print(f"✓ Loaded session: {self.session.name}")
        else:
            self.session = Session(
                name=session_name or "coding-session",
                workspace=str(self.workspace),
                auto_save=True,
            )

        # Initialize tools
        file_tools = FileTools(str(self.workspace))
        code_tools = CodeTools()
        shell_tools = ShellTools()

        # Get all tool methods (descriptor protocol auto-binds self)
        tools = []
        for tool_instance in [file_tools, code_tools, shell_tools]:
            for attr_name in dir(tool_instance):
                attr = getattr(tool_instance, attr_name)
                if isinstance(attr, Tool):
                    tools.append(attr)

        # Initialize context manager (needed by _get_system_prompt)
        self.context_manager = ContextManager(self.workspace)

        # Initialize skill manager
        self.skill_manager = None
        if enable_skills:
            self.skill_manager = SkillManager()
            self.skill_manager.discover_skills([])
            if len(self.skill_manager) > 0:
                print(f"✓ Loaded {len(self.skill_manager)} skills")

        # Create agent
        self.agent = Agent(
            name="CodingAgent",
            llm=self.llm,
            tools=tools,
            system_prompt=self._get_system_prompt(),
            verbose=verbose,
        )

        # Initialize extension manager
        self.extension_manager = None
        if enable_extensions:
            self.extension_manager = ExtensionManager(self.agent)
            self._load_extensions()

        # Initialize prompt manager
        self.prompt_manager = PromptManager()
        self.prompt_manager.discover_prompts([])
        if len(self.prompt_manager) > 0:
            print(f"✓ Loaded {len(self.prompt_manager)} prompt templates")

        # Initialize file reference parser
        self.file_ref_parser = FileReferenceParser(self.workspace)

        # Create UI
        self.ui = ChatUI(title="Coding Agent", show_timestamps=False)

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

    def _get_system_prompt(self) -> str:
        """Get system prompt for coding agent."""
        # Default prompt
        default_prompt = f"""You are an expert coding assistant with access to file operations and code generation tools.

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
        "/help", "/exit", "/quit", "/clear", "/files", "/status",
        "/tree", "/fork", "/compact", "/session", "/sessions",
        "/skills", "/extensions", "/prompts", "/reload",
        "/config", "/queue", "/export", "/share", "/model",
        "/login", "/logout",
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

        # Set up interactive prompt with completion and history
        history_file = str(self.workspace / ".sessions" / ".input_history")
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
                    continue
                except EOFError:
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

                # Get agent response (with queue support)
                response = self.agent.run(user_input)

                # Display response
                self.ui.assistant(response.content)
                
                # Add to session
                if self.session:
                    self.session.add_message("user", user_input)
                    self.session.add_message("assistant", response.content)

        except KeyboardInterrupt:
            pass
        finally:
            # Clean up queued messages
            if self.agent.message_queue:
                cleared = self.agent.message_queue.clear()
                if cleared:
                    self.ui.system(f"\nCleared {len(cleared)} queued messages")
            self.ui.system("\nGoodbye!")


    def _handle_command(self, command: str) -> None:
        """Handle slash commands.

        Args:
            command: Command string
        """
        cmd = command.lower().strip()

        if cmd == "/exit" or cmd == "/quit":
            raise KeyboardInterrupt()

        elif cmd == "/clear":
            self.agent.clear_history()
            self.ui.clear()
            self.ui.system("Conversation cleared")

        elif cmd == "/help":
            self.ui.panel("""
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
            """, title="Help")

        elif cmd == "/files":
            files = FileTools(str(self.workspace)).list_files()
            self.ui.panel(files, title="Files")

        elif cmd == "/status":
            self.ui.panel(f"""
**Agent Status**

Model: {self.agent.llm.config.model}
Workspace: {self.workspace}
Messages: {len(self.agent.history)}
Tools: {len(self.agent.registry)}
            """, title="Status")

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

    def _fork_session(self, fork_name: Optional[str]):
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
        fork = self.session.fork(conversation[-1].id, name)

        save_path = fork.save()
        self.ui.system(f"✓ Forked session: {name}")
        self.ui.system(f"  Copied {len(fork.tree.entries)} entries")
        self.ui.system(f"  Saved to: {save_path}")

    def _compact_session(self, instructions: Optional[str]):
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
        session_mgr = SessionManager(self.workspace)
        sessions = session_mgr.list_sessions(limit=20)
        
        if not sessions:
            self.ui.system("No sessions found")
            self.ui.system(f"Sessions are saved to: {self.workspace}/.sessions/")
            return
        
        sessions_text = session_mgr.format_session_list(sessions)
        
        if len(sessions) == 20:
            sessions_text += "\n\n... (showing most recent 20)"
        
        self.ui.panel(sessions_text, title=f"Available Sessions ({len(sessions)})")
        self.ui.system("Use `pig-code --resume` to select a session")

    def _show_session_info(self):
        """Show session information."""
        if not self.session:
            self.ui.error("No session loaded")
            return

        info = self.session.get_info()
        info_text = f"""
**Session Information**

ID: {info['id'][:8]}...
Name: {info['name']}
Created: {info['created_at'][:19]}
Updated: {info['updated_at'][:19]}

Entries: {info['entries']}
Current path: {info['current_path_length']}
Branches: {info['branches']}

Tokens: {info['metadata'].get('tokens_used', 0)}
Cost: ${info['metadata'].get('cost', 0.0):.4f}
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

• Sessions auto-save to .sessions/
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
            vars_text += f"\n**Usage**: `/{template_name} {' '.join(f'{v}=value' for v in template.variables)}`"
            vars_text += f"\n\n**Example**: `/{template_name} {template.variables[0]}=\"example\"`"
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

    def _export_session(self, filename: Optional[str]):
        """Export session to HTML."""
        if not self.session:
            self.ui.error("No session to export")
            return

        from pig_agent_core import SessionExporter
        from pathlib import Path

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
            self.ui.system(f"  Open in browser: file://{exported.absolute()}")
        except Exception as e:
            self.ui.error(f"Export failed: {e}")

    def _switch_model(self, model_name: Optional[str]):
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
        from pig_agent_core import AuthManager, OAuthProvider
        from pig_tui import Prompt

        # Supported providers (examples)
        providers_config = {
            "anthropic": {
                "name": "anthropic",
                "client_id": "your-client-id",  # Users need to configure
                "auth_url": "https://console.anthropic.com/oauth/authorize",
                "token_url": "https://console.anthropic.com/oauth/token",
                "scope": "read write",
            },
            # Add more providers as they become available
        }

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

    def _logout(self, provider: Optional[str]):
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

            self.ui.system(f"✓ Shared as private gist!")
            self.ui.panel(
                f"""
**Gist Created**

URL: {info['url']}
ID: {info['id']}
Public: {info['public']}

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
        
        queue_text += f"\n**Modes**:\n"
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
Model: {config.model or 'default'}
Temperature: {config.temperature}

**Features**

Extensions: {'enabled' if config.enable_extensions else 'disabled'}
Skills: {'enabled' if config.enable_skills else 'disabled'}
Prompts: {'enabled' if config.enable_prompts else 'disabled'}
Context: {'enabled' if config.enable_context else 'disabled'}

**Session**

Auto-save: {'yes' if config.auto_save_session else 'no'}
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
            self.extension_manager.extensions.clear()
            self._load_extensions()
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
Entries: {info['entries']}
Current path: {info['current_path_length']}
Branches: {info['branches']}
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
