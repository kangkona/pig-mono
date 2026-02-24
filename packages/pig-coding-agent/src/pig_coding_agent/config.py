"""Configuration management for coding agent."""

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for coding agent."""

    # Model settings
    provider: str = "openai"
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Feature toggles
    enable_extensions: bool = True
    enable_skills: bool = True
    enable_prompts: bool = True
    enable_context: bool = True

    # Session settings
    auto_save_session: bool = True
    session_cleanup_days: int = 30

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
            "git_status",
            "git_diff",
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

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize config manager.

        Args:
            workspace: Workspace directory
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()

        # Config file paths
        self.global_config = Path.home() / ".agents" / "config.json"
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

    def get_config_value(self, key: str) -> Optional[Any]:
        """Get a specific config value.

        Args:
            key: Config key (dot notation supported)

        Returns:
            Config value or None
        """
        config = self.load_config()
        return getattr(config, key, None)

    def set_config_value(
        self, key: str, value: Any, global_config: bool = False
    ) -> None:
        """Set a specific config value.

        Args:
            key: Config key
            value: Value to set
            global_config: Set in global config
        """
        config = self.load_config()
        setattr(config, key, value)
        self.save_config(config, global_config)
