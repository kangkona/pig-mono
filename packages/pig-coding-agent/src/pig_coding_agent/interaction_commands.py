"""Command-side imperative actions for pig-coding-agent interaction runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .presentation import build_login_panel, build_model_panel, build_template_variables_panel


@dataclass
class InteractionCommands:
    """Own imperative command handlers that are neither app actions nor pure views."""

    agent_owner: Any
    runtime_owner: Any

    def invoke_skill(self, skill_name: str) -> None:
        owner = self.agent_owner
        runtime = self.runtime_owner
        if not owner.skill_manager:
            runtime.show_error("Skills not enabled")
            return

        skill = owner.skill_manager.get_skill(skill_name)
        if not skill:
            runtime.show_error(f"Skill '{skill_name}' not found")
            runtime.show_system("Use /skills to see available skills")
            return

        skill_prompt = skill.to_prompt()
        runtime.show_text_panel(f"Skill: {skill_name}", skill_prompt)
        runtime.show_system("Skill context loaded. Ask your question now.")

    def expand_prompt(self, template_name: str, args: str) -> None:
        owner = self.agent_owner
        runtime = self.runtime_owner
        template = owner.prompt_manager.get_template(template_name)
        if not template:
            runtime.show_error(f"Template '{template_name}' not found")
            return

        kwargs = {}
        if args:
            parts = args.replace(",", " ").split()
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    kwargs[key] = value.strip("\"'")

        if template.variables and not kwargs:
            runtime.show_panel(
                build_template_variables_panel(template_name, list(template.variables))
            )
            return

        rendered = template.render(**kwargs)
        runtime.show_text_panel(f"Expanded: /{template_name}", rendered)
        runtime.show_system("Sending prompt to agent...")

        if owner.session:
            owner.session.add_message("user", rendered)

        response = owner.agent.run(rendered)
        runtime.show_assistant(response.content)

    def switch_model(self, model_name: str | None) -> None:
        owner = self.agent_owner
        runtime = self.runtime_owner
        if not model_name:
            current = f"{owner.agent.llm.config.provider}/{owner.agent.llm.config.model}"
            runtime.show_panel(
                build_model_panel(
                    current,
                    owner.agent.llm.config.provider,
                    owner.agent.llm.config.model,
                )
            )
            return

        if "/" in model_name:
            provider, model = model_name.split("/", 1)
        else:
            provider = owner.agent.llm.config.provider
            model = model_name

        try:
            from pig_llm import LLM

            new_llm = LLM(provider=provider, model=model)
            owner.agent.llm = new_llm
            owner.llm = new_llm
            runtime.show_system(f"✓ Switched to {provider}/{model}")
        except Exception as e:
            runtime.show_error(f"Failed to switch model: {e}")

    def show_login(self) -> None:
        self.runtime_owner.show_panel(build_login_panel())

    def logout(self, provider: str | None) -> None:
        runtime = self.runtime_owner
        from pig_agent_core import AuthManager

        if not provider:
            runtime.show_error("Usage: /logout <provider>")
            runtime.show_system("Example: /logout anthropic")
            return

        auth_mgr = AuthManager()
        if auth_mgr.logout(provider):
            runtime.show_system(f"✓ Logged out from {provider}")
        else:
            runtime.show_system(f"Not logged in to {provider}")

    def share_session(self) -> None:
        owner = self.agent_owner
        runtime = self.runtime_owner
        if not owner.session:
            runtime.show_error("No session to share")
            return

        import os

        from pig_agent_core import GistSharer

        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            runtime.show_error("GITHUB_TOKEN not set")
            runtime.show_system("Get token from: https://github.com/settings/tokens")
            runtime.show_system("Set: export GITHUB_TOKEN=your_token")
            return

        try:
            sharer = GistSharer(github_token)
            runtime.show_system("Uploading to GitHub Gist...")
            info = sharer.share_session(
                owner.session, public=False, description=f"pig-mono: {owner.session.name}"
            )
            runtime.show_system("✓ Shared as private gist!")
            self.runtime_owner.views.show_share_result(info)
        except Exception as e:
            runtime.show_error(f"Share failed: {e}")

    def reload_resources(self) -> None:
        owner = self.agent_owner
        runtime = self.runtime_owner
        reloaded = []

        if owner.extension_manager:
            old_count = len(owner.extension_manager.extensions)
            session_file = str(owner.session.save()) if owner.session else None
            owner.extension_manager.cleanup(
                reason="reload",
                target_session_file=session_file,
            )
            owner._load_extensions()
            owner.extension_manager.emit_event("session_start", {"reason": "reload"})
            new_count = len(owner.extension_manager.extensions)
            reloaded.append(f"Extensions: {new_count} (was {old_count})")

        if owner.skill_manager:
            old_count = len(owner.skill_manager)
            owner.skill_manager.skills.clear()
            owner.skill_manager.discover_skills([])
            new_count = len(owner.skill_manager)
            reloaded.append(f"Skills: {new_count} (was {old_count})")

        if owner.prompt_manager:
            old_count = len(owner.prompt_manager)
            owner.prompt_manager.templates.clear()
            owner.prompt_manager.discover_prompts([])
            new_count = len(owner.prompt_manager)
            reloaded.append(f"Prompts: {new_count} (was {old_count})")

        new_prompt = owner._get_system_prompt()
        if owner.agent.history and owner.agent.history[0].role == "system":
            owner.agent.history[0].content = new_prompt
            reloaded.append("Context: Reloaded")

        if reloaded:
            runtime.show_system("✓ Reloaded resources:")
            for item in reloaded:
                runtime.show_system(f"  • {item}")
        else:
            runtime.show_system("No resources to reload")
