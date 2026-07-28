"""Configuration management for coding agent."""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for coding agent."""

    # Model settings
    provider: str = "openai"
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Feature toggles
    enable_extensions: bool = True
    enable_skills: bool = True
    enable_prompts: bool = True
    enable_context: bool = True
    enable_resilience: bool = True
    enable_cost_tracking: bool = True

    # Session settings
    auto_save_session: bool = True
    session_cleanup_days: int = 30
    session_dir: str | None = None

    # Context / compaction settings
    auto_compact: bool = True
    auto_compact_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    # Display settings
    verbose: bool = True
    show_timestamps: bool = False
    theme: str = "dark"

    # Tool settings
    tools_enabled: list[str] = Field(
        default_factory=lambda: [
            "read_file",
            "write_file",
            "list_files",
            "grep_files",
            "find_files",
            "ls_detailed",
            "run_command",
        ]
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "provider": "openai",
                "model": "gpt-4",
                "enable_extensions": True,
                "auto_save_session": True,
            }
        }


class ConfigManager:
    """Manages agent configuration."""

    def __init__(self, workspace: Path | None = None):
        """Initialize config manager.

        Args:
            workspace: Workspace directory
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()
        home_dir = Path(os.environ.get("HOME", Path.home())).expanduser()

        # Config file paths
        self.global_config = home_dir / ".agents" / "config.json"
        self.project_config = self.workspace / ".agents" / "config.json"

    def load_config(self) -> AgentConfig:
        """Load configuration.

        Merges global and project configs, with project taking precedence.

        Returns:
            Loaded configuration
        """
        config = AgentConfig()

        # Load global config
        if self.global_config.exists():
            try:
                data = json.loads(self.global_config.read_text())
                config = AgentConfig(**data)
            except Exception as e:
                print(f"Warning: Failed to load global config: {e}")

        # Load and merge project config
        if self.project_config.exists():
            try:
                data = json.loads(self.project_config.read_text())
                # Merge with existing config
                config = AgentConfig(**{**config.model_dump(), **data})
            except Exception as e:
                print(f"Warning: Failed to load project config: {e}")

        return config

    def save_config(self, config: AgentConfig, global_config: bool = False) -> Path:
        """Save configuration.

        Args:
            config: Configuration to save
            global_config: Save to global config instead of project

        Returns:
            Path to saved config file
        """
        if global_config:
            path = self.global_config
        else:
            path = self.project_config

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        path.write_text(config.model_dump_json(indent=2))

        return path

    def get_config_value(self, key: str) -> Any | None:
        """Get a specific config value.

        Args:
            key: Config key (dot notation supported)

        Returns:
            Config value or None
        """
        config = self.load_config()
        return getattr(config, key, None)

    def get_session_dir(self) -> str | None:
        """Get configured session directory if present."""
        config = self.load_config()
        return config.session_dir

    def set_config_value(self, key: str, value: Any, global_config: bool = False) -> None:
        """Set a specific config value.

        Args:
            key: Config key
            value: Value to set
            global_config: Set in global config
        """
        if key not in AgentConfig.model_fields:
            raise ValueError(f"Unknown config key: {key}")

        merged = self.load_config()
        validated = AgentConfig(**{**merged.model_dump(), key: value})
        path = self.global_config if global_config else self.project_config

        data: dict[str, Any] = {}
        if path.exists():
            loaded = json.loads(path.read_text())
            if not isinstance(loaded, dict):
                raise ValueError(f"Config file must contain a JSON object: {path}")
            data = loaded

        data[key] = getattr(validated, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
