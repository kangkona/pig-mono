"""Prompt template system."""

import re
from pathlib import Path
from typing import Optional


class PromptTemplate:
    """Represents a prompt template."""

    def __init__(self, name: str, path: Path, content: str):
        """Initialize prompt template.

        Args:
            name: Template name
            path: Path to template file
            content: Template content
        """
        self.name = name
        self.path = path
        self.content = content
        self.variables = self._extract_variables()

    def _extract_variables(self) -> list[str]:
        """Extract template variables.

        Returns:
            List of variable names
        """
        # Find {{variable}} patterns
        pattern = r"\{\{(\w+)\}\}"
        matches = re.findall(pattern, self.content)
        return list(set(matches))

    def render(self, **kwargs) -> str:
        """Render template with variables.

        Args:
            **kwargs: Variable values

        Returns:
            Rendered template
        """
        rendered = self.content

        # Replace variables
        for var in self.variables:
            value = kwargs.get(var, "")
            rendered = rendered.replace(f"{{{{{var}}}}}", str(value))

        return rendered

    def __repr__(self) -> str:
        return f"PromptTemplate(name={self.name}, vars={self.variables})"


class PromptManager:
    """Manages prompt templates."""

    def __init__(self):
        """Initialize prompt manager."""
        self.templates: dict[str, PromptTemplate] = {}

    def discover_prompts(self, directories: list[Path]) -> None:
        """Discover prompt templates in directories.

        Args:
            directories: List of directories to search

        Looks for .md files in:
        - ~/.agents/prompts/
        - .agents/prompts/
        - .pi/prompts/
        - Any provided directories
        """
        search_paths = []

        # Add standard paths
        home = Path.home()
        if (home / ".agents" / "prompts").exists():
            search_paths.append(home / ".agents" / "prompts")
        if (home / ".pi" / "agent" / "prompts").exists():
            search_paths.append(home / ".pi" / "agent" / "prompts")

        cwd = Path.cwd()
        if (cwd / ".agents" / "prompts").exists():
            search_paths.append(cwd / ".agents" / "prompts")
        if (cwd / ".pi" / "prompts").exists():
            search_paths.append(cwd / ".pi" / "prompts")

        # Add provided directories
        search_paths.extend(directories)

        # Discover templates
        for directory in search_paths:
            if not directory.exists():
                continue

            for template_file in directory.glob("*.md"):
                if template_file.name.startswith("_"):
                    continue  # Skip private files

                self.load_template(template_file)

    def load_template(self, path: Path) -> PromptTemplate:
        """Load a prompt template.

        Args:
            path: Path to template file (.md)

        Returns:
            Loaded template
        """
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        content = path.read_text()
        name = path.stem  # Use filename without extension

        template = PromptTemplate(name=name, path=path, content=content)
        self.templates[name] = template

        return template

    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """Get a template by name.

        Args:
            name: Template name

        Returns:
            Template if found
        """
        return self.templates.get(name)

    def list_templates(self) -> list[PromptTemplate]:
        """List all templates.

        Returns:
            List of templates
        """
        return list(self.templates.values())

    def render_template(self, name: str, **kwargs) -> Optional[str]:
        """Render a template with variables.

        Args:
            name: Template name
            **kwargs: Variable values

        Returns:
            Rendered template or None if not found
        """
        template = self.get_template(name)
        if not template:
            return None

        return template.render(**kwargs)

    def __len__(self) -> int:
        """Get number of loaded templates."""
        return len(self.templates)

    def __contains__(self, name: str) -> bool:
        """Check if template exists."""
        return name in self.templates
