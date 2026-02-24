"""Skills system following Agent Skills standard."""

from pathlib import Path
from typing import Optional


class Skill:
    """Represents an agent skill."""

    def __init__(self, name: str, path: Path, content: str):
        """Initialize skill.

        Args:
            name: Skill name
            path: Path to SKILL.md
            content: Skill content (markdown)
        """
        self.name = name
        self.path = path
        self.content = content

        # Parse skill metadata
        self.title = self._extract_title()
        self.description = self._extract_description()
        self.steps = self._extract_steps()

    def _extract_title(self) -> str:
        """Extract title from skill content.

        Returns:
            Skill title (from first # heading, or name)
        """
        for line in self.content.split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
        return self.name

    def _extract_description(self) -> str:
        """Extract description from skill content.

        Returns:
            Skill description
        """
        lines = self.content.split("\n")

        # Look for first paragraph after title
        description_lines = []
        in_description = False

        for line in lines:
            if line.startswith("# "):  # Skip title
                in_description = True
                continue

            if in_description:
                if line.strip() == "":
                    continue
                if line.startswith("#"):  # Stop at next heading
                    break
                description_lines.append(line.strip())

        return " ".join(description_lines)

    def _extract_steps(self) -> list[str]:
        """Extract steps from skill content.

        Returns:
            List of steps
        """
        lines = self.content.split("\n")
        steps = []
        in_steps = False

        for line in lines:
            if "## Steps" in line or "## Instructions" in line:
                in_steps = True
                continue

            if in_steps:
                if line.startswith("#"):  # Next section
                    break

                line = line.strip()
                if line and (
                    line.startswith("-")
                    or line.startswith("*")
                    or (len(line) > 1 and line[0].isdigit() and "." in line.split()[0])
                ):
                    # Remove list markers
                    step = line.lstrip("-*0123456789. ")
                    if step:
                        steps.append(step)

        return steps

    def to_prompt(self) -> str:
        """Convert skill to prompt text.

        Returns:
            Skill as prompt text
        """
        prompt = f"# Skill: {self.name} — {self.title}\n\n"
        prompt += f"{self.description}\n\n"

        if self.steps:
            prompt += "## Steps:\n"
            for i, step in enumerate(self.steps, 1):
                prompt += f"{i}. {step}\n"

        return prompt

    def __repr__(self) -> str:
        return f"Skill(name={self.name}, path={self.path})"


class SkillManager:
    """Manages agent skills."""

    def __init__(self):
        """Initialize skill manager."""
        self.skills: dict[str, Skill] = {}

    def discover_skills(self, directories: list[Path | str]) -> None:
        """Discover skills in directories.

        Args:
            directories: List of directories to search

        Looks for:
        - Any provided directories
        - If no directories provided, also searches standard paths:
          ~/.agents/skills/, .agents/skills/, .pi/skills/
        """
        search_paths = []

        # Only add standard paths when no explicit directories given
        if not directories:
            home = Path.home()
            if (home / ".agents" / "skills").exists():
                search_paths.append(home / ".agents" / "skills")

            cwd = Path.cwd()
            if (cwd / ".agents" / "skills").exists():
                search_paths.append(cwd / ".agents" / "skills")
            if (cwd / ".pi" / "skills").exists():
                search_paths.append(cwd / ".pi" / "skills")

        # Add provided directories
        search_paths.extend([Path(d) for d in directories])

        # Discover skills
        for directory in search_paths:
            if not directory.exists():
                continue

            for skill_dir in directory.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                self.load_skill(skill_file)

    def load_skill(self, path: Path | str) -> Skill:
        """Load a skill from SKILL.md.

        Args:
            path: Path to SKILL.md

        Returns:
            Loaded skill
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Skill not found: {path}")

        content = path.read_text()
        name = path.parent.name  # Use directory name as skill name

        skill = Skill(name=name, path=path, content=content)
        self.skills[name] = skill

        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        return self.skills.get(name)

    def list_skills(self) -> list[Skill]:
        """List all loaded skills.

        Returns:
            List of skills
        """
        return list(self.skills.values())

    def get_skill_prompt(self, name: str) -> Optional[str]:
        """Get skill prompt text.

        Args:
            name: Skill name

        Returns:
            Skill prompt text if found
        """
        skill = self.get_skill(name)
        return skill.to_prompt() if skill else None

    def get_all_skills_prompt(self) -> str:
        """Get prompt text for all skills.

        Returns:
            Combined skills prompt
        """
        if not self.skills:
            return ""

        prompt = "# Available Skills\n\n"
        prompt += "You have access to the following skills:\n\n"

        for skill in self.skills.values():
            prompt += f"- **{skill.name}**: {skill.description}\n"

        prompt += "\nUse `/skill:{skill_name}` to invoke a skill.\n"

        return prompt

    def __len__(self) -> int:
        """Get number of loaded skills."""
        return len(self.skills)

    def __contains__(self, name: str) -> bool:
        """Check if skill is loaded."""
        return name in self.skills
