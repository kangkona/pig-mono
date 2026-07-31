"""Configuration management for coding agent."""

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _supports_secure_dir_fds() -> bool:
    """Return whether the platform supports descriptor-relative file writes."""
    return os.name != "nt"


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

    def __init__(self, workspace: Path | None = None, *, project_trusted: bool = False):
        """Initialize config manager.

        Args:
            workspace: Workspace directory
        """
        self.workspace = (Path(workspace) if workspace else Path.cwd()).expanduser().resolve()
        self.project_trusted = project_trusted
        # Values explicitly changed by the current user are safe to apply for
        # this process even when the workspace itself is not trusted.  They do
        # not make other project-local configuration readable.
        self._runtime_overrides: dict[str, Any] = {}
        self._untrusted_project_values: dict[str, Any] = {}
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
                data = json.loads(self.global_config.read_text(encoding="utf-8"))
                config = AgentConfig(**data)
            except Exception as e:
                print(f"Warning: Failed to load global config: {e}")

        # Load and merge project config
        if self.project_trusted and self.project_config.exists():
            try:
                data = json.loads(self.project_config.read_text(encoding="utf-8"))
                # Merge with existing config
                config = AgentConfig(**{**config.model_dump(), **data})
            except Exception as e:
                print(f"Warning: Failed to load project config: {e}")

        if self._runtime_overrides:
            config = AgentConfig(**{**config.model_dump(), **self._runtime_overrides})

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
            self._validate_project_config_destination()

        if (
            not global_config
            and not self.project_trusted
            and path.exists()
            and not self._untrusted_project_values
        ):
            raise PermissionError(
                "Refusing to overwrite an existing untrusted project config. "
                "Trust the workspace or save the global config instead."
            )

        content = config.model_dump_json(indent=2)
        if global_config:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        else:
            self._write_project_config(content)
        if not global_config and not self.project_trusted:
            self._untrusted_project_values = config.model_dump()

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
        if not global_config:
            self._validate_project_config_destination()

        data: dict[str, Any] = {}
        if not global_config and not self.project_trusted:
            if path.exists() and not self._untrusted_project_values:
                raise PermissionError(
                    "Refusing to read or modify an existing untrusted project config. "
                    "Trust the workspace or change the global config instead."
                )
            # Never re-read project-controlled bytes after an explicit write.
            # Subsequent edits merge only the values this process authored.
            data = dict(self._untrusted_project_values)
        elif path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Config file must contain a JSON object: {path}")
            data = loaded

        data[key] = getattr(validated, key)
        content = json.dumps(data, indent=2)
        if global_config:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        else:
            self._write_project_config(content)
        if not global_config and not self.project_trusted:
            self._untrusted_project_values = dict(data)
        self._runtime_overrides[key] = getattr(validated, key)

    def _validate_project_config_destination(self) -> None:
        """Reject project config paths that contain or terminate in symlinks."""
        workspace = self.workspace.resolve()
        agents_dir = workspace / ".agents"
        project_config = agents_dir / "config.json"

        if agents_dir.is_symlink():
            raise PermissionError(f"Refusing project config symlink component: {agents_dir}")
        if project_config.is_symlink():
            raise PermissionError(f"Refusing project config symlink target: {project_config}")

        # This also catches a parent path that resolves outside the workspace.
        resolved_parent = agents_dir.resolve(strict=False)
        try:
            resolved_parent.relative_to(workspace)
        except ValueError as exc:
            raise PermissionError(
                f"Refusing project config outside workspace: {resolved_parent}"
            ) from exc

    def _write_project_config(self, content: str) -> None:
        """Atomically write config through no-follow directory descriptors."""
        if not _supports_secure_dir_fds():
            self._write_project_config_portable(content)
            return

        self._validate_project_config_destination()
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        workspace_fd = os.open(self.workspace, os.O_RDONLY | directory | nofollow)
        agents_fd: int | None = None
        temporary_name = f".config.json.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            try:
                agents_fd = os.open(
                    ".agents",
                    os.O_RDONLY | directory | nofollow,
                    dir_fd=workspace_fd,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(".agents", mode=0o700, dir_fd=workspace_fd)
                    agents_fd = os.open(
                        ".agents",
                        os.O_RDONLY | directory | nofollow,
                        dir_fd=workspace_fd,
                    )
                except OSError as exc:
                    raise PermissionError("Refusing unsafe project config parent") from exc
            except OSError as exc:
                raise PermissionError("Refusing unsafe project config parent") from exc

            try:
                target = os.stat("config.json", dir_fd=agents_fd, follow_symlinks=False)
            except FileNotFoundError:
                target = None
            if target is not None and stat.S_ISLNK(target.st_mode):
                raise PermissionError("Refusing project config symlink target")

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
            temporary_fd = os.open(temporary_name, flags, 0o600, dir_fd=agents_fd)
            try:
                owned_fd = temporary_fd
                temporary_fd = -1
                with os.fdopen(owned_fd, "w", encoding="utf-8") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                # rename replaces a symlink entry rather than following it if a
                # race occurs after the lstat above; external targets stay safe.
                os.replace(
                    temporary_name,
                    "config.json",
                    src_dir_fd=agents_fd,
                    dst_dir_fd=agents_fd,
                )
                temporary_name = ""
                os.fsync(agents_fd)
            finally:
                if temporary_fd >= 0:
                    os.close(temporary_fd)
        finally:
            if temporary_name and agents_fd is not None:
                try:
                    os.unlink(temporary_name, dir_fd=agents_fd)
                except FileNotFoundError:
                    pass
            if agents_fd is not None:
                os.close(agents_fd)
            os.close(workspace_fd)

    def _write_project_config_portable(self, content: str) -> None:
        """Atomically write config on platforms without directory descriptors."""
        self._validate_project_config_destination()
        agents_dir = self.workspace / ".agents"
        try:
            agents_dir.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise PermissionError("Refusing unsafe project config parent") from exc
        self._validate_project_config_destination()

        temporary = agents_dir / (f".config.json.{os.getpid()}.{secrets.token_hex(8)}.tmp")
        temporary_exists = True
        temporary_fd = -1
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            temporary_fd = os.open(temporary, flags, 0o600)
            owned_fd = temporary_fd
            temporary_fd = -1
            with os.fdopen(owned_fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

            # Revalidate after creating the temporary file. Replacing a final
            # symlink swaps the entry itself rather than following its target.
            self._validate_project_config_destination()
            os.replace(temporary, self.project_config)
            temporary_exists = False
        finally:
            if temporary_fd >= 0:
                os.close(temporary_fd)
            if temporary_exists:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
