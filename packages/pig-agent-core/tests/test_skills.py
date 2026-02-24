"""Tests for skills system."""

import pytest
from pathlib import Path
from pig_agent_core.skills import Skill, SkillManager


@pytest.fixture
def sample_skill_content():
    """Sample skill content."""
    return """# Code Review

Use this skill for code reviews.

This helps analyze code quality.

## Steps

1. Read the code
2. Check for issues
3. Suggest improvements

## Example

Check for errors.
"""


@pytest.fixture
def sample_skill_file(tmp_path, sample_skill_content):
    """Create a sample skill file."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(sample_skill_content)
    
    return skill_file


def test_skill_creation(sample_skill_file, sample_skill_content):
    """Test creating a skill."""
    skill = Skill(
        name="test-skill",
        path=sample_skill_file,
        content=sample_skill_content,
    )
    
    assert skill.name == "test-skill"
    assert skill.path == sample_skill_file


def test_skill_extract_description(sample_skill_file, sample_skill_content):
    """Test extracting skill description."""
    skill = Skill("test", sample_skill_file, sample_skill_content)
    
    assert "code reviews" in skill.description.lower()
    assert "analyze code quality" in skill.description.lower()


def test_skill_extract_steps(sample_skill_file, sample_skill_content):
    """Test extracting skill steps."""
    skill = Skill("test", sample_skill_file, sample_skill_content)
    
    assert len(skill.steps) == 3
    assert "Read the code" in skill.steps[0]
    assert "Check for issues" in skill.steps[1]
    assert "Suggest improvements" in skill.steps[2]


def test_skill_to_prompt(sample_skill_file, sample_skill_content):
    """Test converting skill to prompt."""
    skill = Skill("test", sample_skill_file, sample_skill_content)
    
    prompt = skill.to_prompt()
    assert "# Skill: test" in prompt
    assert "## Steps:" in prompt
    assert "1. Read the code" in prompt


def test_skill_manager_creation():
    """Test creating skill manager."""
    manager = SkillManager()
    assert len(manager) == 0


def test_skill_manager_load_skill(sample_skill_file):
    """Test loading a skill."""
    manager = SkillManager()
    
    skill = manager.load_skill(sample_skill_file)
    assert skill.name == "test-skill"
    assert len(manager) == 1


def test_skill_manager_get_skill(sample_skill_file):
    """Test getting a skill by name."""
    manager = SkillManager()
    manager.load_skill(sample_skill_file)
    
    skill = manager.get_skill("test-skill")
    assert skill is not None
    assert skill.name == "test-skill"


def test_skill_manager_get_missing_skill():
    """Test getting non-existent skill."""
    manager = SkillManager()
    
    skill = manager.get_skill("nonexistent")
    assert skill is None


def test_skill_manager_list_skills(sample_skill_file):
    """Test listing skills."""
    manager = SkillManager()
    manager.load_skill(sample_skill_file)
    
    skills = manager.list_skills()
    assert len(skills) == 1
    assert skills[0].name == "test-skill"


def test_skill_manager_get_skill_prompt(sample_skill_file):
    """Test getting skill prompt."""
    manager = SkillManager()
    manager.load_skill(sample_skill_file)
    
    prompt = manager.get_skill_prompt("test-skill")
    assert prompt is not None
    assert "Code Review" in prompt


def test_skill_manager_get_all_skills_prompt(sample_skill_file):
    """Test getting all skills prompt."""
    manager = SkillManager()
    manager.load_skill(sample_skill_file)
    
    prompt = manager.get_all_skills_prompt()
    assert "Available Skills" in prompt
    assert "test-skill" in prompt


def test_skill_manager_contains(sample_skill_file):
    """Test checking if skill exists."""
    manager = SkillManager()
    
    assert "test-skill" not in manager
    
    manager.load_skill(sample_skill_file)
    
    assert "test-skill" in manager


def test_skill_manager_discover_skills(tmp_path):
    """Test discovering skills."""
    # Create skills directory
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    
    # Create sample skills
    (skills_dir / "skill1").mkdir()
    (skills_dir / "skill1" / "SKILL.md").write_text("# Skill 1\nDescription")
    
    (skills_dir / "skill2").mkdir()
    (skills_dir / "skill2" / "SKILL.md").write_text("# Skill 2\nDescription")
    
    # Discover with custom directory
    manager = SkillManager()
    manager.discover_skills([skills_dir])
    
    assert len(manager) == 2
    assert "skill1" in manager
    assert "skill2" in manager
