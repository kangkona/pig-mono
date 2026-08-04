"""Application-layer presentation builders for pig-coding-agent."""

from __future__ import annotations

from typing import Any

from pig_tui import PanelContent, render_bullet_panel, render_info_panel, render_select_panel


def build_session_tree_panel(
    items: list[tuple[str, str | None]],
    *,
    total_entries: int,
    current_path_length: int,
) -> PanelContent:
    footer = [
        ("Total entries", str(total_entries)),
        ("Current path", str(current_path_length)),
    ]
    return render_select_panel("Session Tree", items, footer_rows=footer)


def build_sessions_panel(
    items: list[tuple[str, str | None]],
    *,
    session_dir: str,
    truncated: bool,
) -> PanelContent:
    note = "... (showing most recent 20)" if truncated else None
    return render_select_panel(
        f"Available Sessions ({len(items)})",
        items,
        footer_rows=[("Session dir", session_dir)],
        note=note,
    )


def build_session_info_panel(info: dict[str, Any]) -> PanelContent:
    return render_info_panel(
        "Session",
        [
            ("ID", f"{info['id'][:8]}..."),
            ("Name", str(info["name"])),
            ("Created", info["created_at"][:19]),
            ("Updated", info["updated_at"][:19]),
            ("Entries", str(info["entries"])),
            ("Current path", str(info["current_path_length"])),
            ("Branches", str(info["branches"])),
            ("Tokens", str(info["metadata"].get("tokens_used", 0))),
            ("Cost", f"${info['metadata'].get('cost', 0.0):.4f}"),
        ],
    )


def build_skills_panel(skills: list[tuple[str, str]]) -> PanelContent:
    bullets = [f"{name} — {description}" for name, description in skills]
    return render_bullet_panel(
        f"Skills ({len(skills)})",
        bullets,
        note="Use `/skill:name` to invoke a skill.",
    )


def build_extensions_panel(
    extension_names: list[str],
    command_names: list[str],
    *,
    tool_count: int,
) -> PanelContent:
    bullets = extension_names + [f"/{name}" for name in command_names]
    return render_bullet_panel(
        f"Extensions ({len(extension_names)})",
        bullets,
        note=f"Tools: {tool_count} total",
    )


def build_prompts_panel(prompts: list[str]) -> PanelContent:
    return render_bullet_panel(
        f"Prompts ({len(prompts)})",
        prompts,
        note="Use `/template_name` to expand a template.",
    )


def build_config_panel(config: Any) -> PanelContent:
    return render_info_panel(
        "Configuration",
        [
            ("Provider", config.provider),
            ("Model", config.model or "default"),
            ("Temperature", str(config.temperature)),
            ("Extensions", "enabled" if config.enable_extensions else "disabled"),
            ("Skills", "enabled" if config.enable_skills else "disabled"),
            ("Prompts", "enabled" if config.enable_prompts else "disabled"),
            ("Context", "enabled" if config.enable_context else "disabled"),
            ("Auto-save", "yes" if config.auto_save_session else "no"),
            ("Cleanup", f"{config.session_cleanup_days} days"),
            ("Verbose", str(config.verbose)),
            ("Theme", config.theme),
            ("Global config", "~/.agents/config.json"),
            ("Project config", ".agents/config.json"),
        ],
    )


def build_status_panel(
    *,
    model: str,
    provider: str,
    workspace: str,
    messages: int,
    tools: int,
    session_name: str | None = None,
    session_entries: int | None = None,
    session_path_length: int | None = None,
    session_branches: int | None = None,
    skills: int | None = None,
    extensions: tuple[int, int] | None = None,
    prompts: int | None = None,
    context_files: int | None = None,
) -> PanelContent:
    rows = [
        ("Model", str(model)),
        ("Provider", str(provider)),
        ("Workspace", str(workspace)),
        ("Messages", str(messages)),
        ("Tools", str(tools)),
    ]
    if session_name is not None:
        rows.extend(
            [
                ("Session", str(session_name)),
                ("Entries", str(session_entries or 0)),
                ("Current path", str(session_path_length or 0)),
                ("Branches", str(session_branches or 0)),
            ]
        )
    if skills is not None:
        rows.append(("Skills", f"{skills} loaded"))
    if extensions is not None:
        ext_count, cmd_count = extensions
        rows.append(("Extensions", f"{ext_count} loaded, {cmd_count} commands"))
    if prompts is not None:
        rows.append(("Prompts", f"{prompts} loaded"))
    if context_files is not None:
        rows.append(("Context", f"{context_files} AGENTS.md files"))
    return render_info_panel("Status", rows)


def build_queue_panel(
    steering: list[str],
    followup: list[str],
    *,
    steering_mode: str,
    followup_mode: str,
) -> PanelContent:
    bullets = [f"steer: {item}" for item in steering]
    bullets.extend([f"follow-up: {item}" for item in followup])
    return render_bullet_panel(
        "Queue",
        bullets,
        note=f"Modes: steering={steering_mode}, follow-up={followup_mode}",
    )


def build_resilience_panel(status: dict[str, Any]) -> PanelContent:
    panel = render_info_panel(
        "Resilience",
        [
            ("Total API keys", str(status["total_profiles"])),
            ("Available", str(status["available_profiles"])),
            ("In cooldown", str(status["cooldown_profiles"])),
        ],
    )
    bullets = [
        f"{profile['provider']} (key #{profile['key_index']}): "
        f"{'available' if profile['available'] else 'cooldown'}"
        for profile in status["profiles"]
    ]
    detail = render_bullet_panel(
        "Resilience",
        bullets,
        note="Automatic API key rotation, cooldowns, and model fallback are enabled.",
    )
    return PanelContent(title=panel.title, content=panel.content + "\n\n" + detail.content)


def build_cost_panel(title: str, summary_text: str, usage_file: str) -> PanelContent:
    return PanelContent(title=title, content=summary_text + f"\n\nUsage data: {usage_file}")


def build_help_panel() -> PanelContent:
    bullets = [
        "/help — Show this help",
        "/exit — Exit agent",
        "/clear — Clear conversation",
        "/status — Agent status",
        "/config — Show configuration",
        "/queue — Show message queue",
        "/files — List workspace files",
        "/session — Show current session info",
        "/sessions — List all available sessions",
        "/tree — Show or navigate conversation tree",
        "/fork [name] — Fork session from current point",
        "/compact [instructions] — Compact old messages",
        "/export [file] — Export session to HTML",
        "/share — Share session via GitHub Gist",
        "/reload — Reload extensions, skills, prompts, context",
        "/skills — List available skills",
        "/skill:name — Invoke a skill",
        "/extensions — List loaded extensions",
        "/prompts — List prompt templates",
        "/template — Expand a template",
        "/model [provider/model] — Switch LLM model",
        "/login — Show API key setup help",
        "/logout <provider> — Remove stored provider credentials",
    ]
    note = (
        "Context files: AGENTS.md, SYSTEM.md, APPEND_SYSTEM.md\n"
        "Queue while running: !message for steering, >>message for follow-up\n"
        "File references: use @filename to include file contents in context"
    )
    return render_bullet_panel("Help", bullets, note=note)


def build_files_panel(file_listing: str) -> PanelContent:
    return PanelContent(title="Files", content=file_listing)


def build_settings_panel(
    *,
    provider: str,
    model: str,
    workspace: str,
    session_dir: str,
    skills_enabled: bool,
    extensions_enabled: bool,
    editable_rows: list[tuple[str, str, str]],
    project_config: str,
    global_config: str,
) -> PanelContent:
    """Build the read-only settings summary and supported edit contract."""
    lines = [
        "**Settings**",
        "",
        f"Model:       {provider}/{model}",
        f"Workspace:   {workspace}",
        f"Session dir: {session_dir}",
        f"Skills:      {'on' if skills_enabled else 'off'}",
        f"Extensions:  {'on' if extensions_enabled else 'off'}",
        "",
        "**Editable in project config** (`/settings <key> <value>`):",
    ]
    for key, value, apply_mode in editable_rows:
        lines.append(f"  {key} = {value}  [{apply_mode}]")
    lines += [
        "",
        "**Config files:**",
        f"  project: {project_config}",
        f"  global:  {global_config}",
        "",
        "Also: /model <provider/model>, /login, /logout, /name <name>",
    ]
    return PanelContent(title="Settings", content="\n".join(lines))


def build_template_variables_panel(
    template_name: str,
    variables: list[str],
) -> PanelContent:
    bullets = list(variables)
    usage_args = " ".join(f"{v}=value" for v in variables)
    example = f'/{template_name} {variables[0]}="example"' if variables else f"/{template_name}"
    note = f"Usage: /{template_name} {usage_args}\nExample: {example}"
    return render_bullet_panel(f"Template: {template_name}", bullets, note=note)


def build_model_panel(current: str, provider: str, model: str) -> PanelContent:
    return render_info_panel(
        "Model",
        [
            ("Provider", provider),
            ("Model", model),
            ("Full", current),
            ("Examples", "/model openai/gpt-4; /model anthropic/claude-3-sonnet"),
        ],
    )


def build_login_panel() -> PanelContent:
    bullets = [
        "Use provider API keys through environment variables",
        "OPENAI_API_KEY=sk-...",
        "ANTHROPIC_API_KEY=sk-ant-...",
        "OPENROUTER_API_KEY=sk-or-...",
        "For rotation, also set OPENAI_API_KEY_2 / ANTHROPIC_API_KEY_2",
    ]
    return render_bullet_panel(
        "Login",
        bullets,
        note="`/login` does not open a browser-based login flow in pig-coding-agent.",
    )


def build_share_panel(info: dict[str, Any]) -> PanelContent:
    return render_info_panel(
        "Shared",
        [
            ("URL", str(info["url"])),
            ("ID", str(info["id"])),
            ("Public", str(info["public"])),
        ],
    )
