"""Context file management (AGENTS.md, SYSTEM.md, etc.)."""

from pathlib import Path
from typing import Optional


class ContextManager:
    """Manages context files like AGENTS.md, SYSTEM.md."""

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize context manager.

        Args:
            workspace: Working directory (defaults to cwd)
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def find_context_files(self, filename: str) -> list[Path]:
        """Find context files in directory hierarchy.

        Searches from current directory up to home, plus global config.

        Args:
            filename: File to search for (e.g., "AGENTS.md")

        Returns:
            List of found files (ordered: global, parents, cwd)
        """
        found = []

        # Global config
        global_file = Path.home() / ".agents" / filename
        if global_file.exists():
            found.append(global_file)

        # Alternative global (for pi compatibility)
        pi_global = Path.home() / ".pi" / "agent" / filename
        if pi_global.exists() and pi_global not in found:
            found.append(pi_global)

        # Walk up from workspace
        current = self.workspace
        visited = set()

        while current != current.parent:
            if current in visited:
                break
            visited.add(current)

            # Check current directory
            file_path = current / filename
            if file_path.exists() and file_path not in found:
                found.append(file_path)

            # Check .agents directory
            agents_file = current / ".agents" / filename
            if agents_file.exists() and agents_file not in found:
                found.append(agents_file)

            # Check .pi directory
            pi_file = current / ".pi" / filename
            if pi_file.exists() and pi_file not in found:
                found.append(pi_file)

            # Move to parent
            current = current.parent

        return found

    def load_agents_md(self) -> Optional[str]:
        """Load all AGENTS.md files.

        Returns:
            Combined content of all AGENTS.md files
        """
        files = self.find_context_files("AGENTS.md")

        if not files:
            return None

        content_parts = []
        for file_path in files:
            try:
                content = file_path.read_text()
                content_parts.append(f"# From: {file_path}\n\n{content}")
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")

        return "\n\n---\n\n".join(content_parts) if content_parts else None

    def load_system_md(self) -> Optional[str]:
        """Load SYSTEM.md (replaces default system prompt).

        Returns:
            Content of SYSTEM.md if found
        """
        files = self.find_context_files("SYSTEM.md")

        if not files:
            return None

        # Use the most specific (last in list)
        try:
            return files[-1].read_text()
        except Exception as e:
            print(f"Warning: Failed to load SYSTEM.md: {e}")
            return None

    def load_append_system_md(self) -> Optional[str]:
        """Load APPEND_SYSTEM.md (appends to system prompt).

        Returns:
            Combined content of all APPEND_SYSTEM.md files
        """
        files = self.find_context_files("APPEND_SYSTEM.md")

        if not files:
            return None

        content_parts = []
        for file_path in files:
            try:
                content = file_path.read_text()
                content_parts.append(content)
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")

        return "\n\n".join(content_parts) if content_parts else None

    def build_system_prompt(self, default_prompt: str) -> str:
        """Build final system prompt from context files.

        Args:
            default_prompt: Default system prompt

        Returns:
            Final system prompt with context files applied
        """
        # Check for SYSTEM.md override
        system_md = self.load_system_md()
        if system_md:
            base_prompt = system_md
        else:
            base_prompt = default_prompt

        # Append AGENTS.md if exists
        agents_md = self.load_agents_md()
        if agents_md:
            base_prompt += f"\n\n# Project Context\n\n{agents_md}"

        # Append APPEND_SYSTEM.md if exists
        append_md = self.load_append_system_md()
        if append_md:
            base_prompt += f"\n\n{append_md}"

        return base_prompt

    def watch_for_changes(self) -> None:
        """Watch context files for changes (for hot-reload).

        Note: Actual implementation would use file watching.
        This is a placeholder for the API.
        """
        # TODO: Implement file watching
        pass
