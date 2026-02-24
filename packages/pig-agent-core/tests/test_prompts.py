"""Tests for prompt templates."""

import pytest
from pathlib import Path
from pig_agent_core.prompts import PromptTemplate, PromptManager


@pytest.fixture
def sample_template_content():
    """Sample template content."""
    return """# Code Review

Review this code for {{focus}}.

Provide {{detail_level}} feedback.
"""


@pytest.fixture
def sample_template_file(tmp_path, sample_template_content):
    """Create sample template file."""
    template_file = tmp_path / "review.md"
    template_file.write_text(sample_template_content)
    return template_file


def test_template_creation(sample_template_file, sample_template_content):
    """Test creating a template."""
    template = PromptTemplate(
        name="review",
        path=sample_template_file,
        content=sample_template_content,
    )
    
    assert template.name == "review"
    assert template.path == sample_template_file


def test_template_extract_variables(sample_template_file, sample_template_content):
    """Test extracting template variables."""
    template = PromptTemplate("review", sample_template_file, sample_template_content)
    
    assert "focus" in template.variables
    assert "detail_level" in template.variables
    assert len(template.variables) == 2


def test_template_render(sample_template_file, sample_template_content):
    """Test rendering template."""
    template = PromptTemplate("review", sample_template_file, sample_template_content)
    
    rendered = template.render(focus="security", detail_level="high")
    
    assert "security" in rendered
    assert "high" in rendered
    assert "{{focus}}" not in rendered
    assert "{{detail_level}}" not in rendered


def test_template_render_partial(sample_template_file, sample_template_content):
    """Test rendering with missing variables."""
    template = PromptTemplate("review", sample_template_file, sample_template_content)
    
    rendered = template.render(focus="performance")
    
    assert "performance" in rendered
    # Missing variable becomes empty string
    assert "{{detail_level}}" not in rendered


def test_prompt_manager_creation():
    """Test creating prompt manager."""
    manager = PromptManager()
    assert len(manager) == 0


def test_prompt_manager_load_template(sample_template_file):
    """Test loading a template."""
    manager = PromptManager()
    
    template = manager.load_template(sample_template_file)
    
    assert template.name == "review"
    assert len(manager) == 1


def test_prompt_manager_get_template(sample_template_file):
    """Test getting a template."""
    manager = PromptManager()
    manager.load_template(sample_template_file)
    
    template = manager.get_template("review")
    assert template is not None
    assert template.name == "review"


def test_prompt_manager_get_missing_template():
    """Test getting non-existent template."""
    manager = PromptManager()
    
    template = manager.get_template("missing")
    assert template is None


def test_prompt_manager_list_templates(sample_template_file):
    """Test listing templates."""
    manager = PromptManager()
    manager.load_template(sample_template_file)
    
    templates = manager.list_templates()
    assert len(templates) == 1
    assert templates[0].name == "review"


def test_prompt_manager_render_template(sample_template_file):
    """Test rendering via manager."""
    manager = PromptManager()
    manager.load_template(sample_template_file)
    
    rendered = manager.render_template("review", focus="bugs", detail_level="medium")
    
    assert rendered is not None
    assert "bugs" in rendered
    assert "medium" in rendered


def test_prompt_manager_render_missing():
    """Test rendering non-existent template."""
    manager = PromptManager()
    
    rendered = manager.render_template("missing")
    assert rendered is None


def test_prompt_manager_contains(sample_template_file):
    """Test checking if template exists."""
    manager = PromptManager()
    
    assert "review" not in manager
    
    manager.load_template(sample_template_file)
    
    assert "review" in manager


def test_prompt_manager_discover(tmp_path):
    """Test discovering templates."""
    # Create prompts directory
    prompts_dir = tmp_path / ".agents" / "prompts"
    prompts_dir.mkdir(parents=True)
    
    # Create templates
    (prompts_dir / "template1.md").write_text("# Template 1\n{{var1}}")
    (prompts_dir / "template2.md").write_text("# Template 2\n{{var2}}")
    (prompts_dir / "_private.md").write_text("# Should be skipped")
    
    # Discover
    manager = PromptManager()
    manager.discover_prompts([prompts_dir])
    
    assert len(manager) == 2  # Should skip _private.md
    assert "template1" in manager
    assert "template2" in manager


def test_template_no_variables():
    """Test template without variables."""
    content = "# Simple Template\nNo variables here."
    template = PromptTemplate("simple", Path("test.md"), content)
    
    assert len(template.variables) == 0
    assert template.render() == content
