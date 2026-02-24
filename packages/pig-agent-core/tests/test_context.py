"""Tests for context management."""

import pytest
from pathlib import Path
from pig_agent_core.context import ContextManager


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_context_manager_creation(temp_workspace):
    """Test creating context manager."""
    ctx = ContextManager(temp_workspace)
    assert ctx.workspace == temp_workspace


def test_find_agents_md(temp_workspace):
    """Test finding AGENTS.md files."""
    ctx = ContextManager(temp_workspace)
    
    # Create AGENTS.md in workspace
    (temp_workspace / "AGENTS.md").write_text("# Project context")
    
    # Create in .agents
    agents_dir = temp_workspace / ".agents"
    agents_dir.mkdir()
    (agents_dir / "AGENTS.md").write_text("# More context")
    
    files = ctx.find_context_files("AGENTS.md")
    assert len(files) >= 1


def test_load_agents_md(temp_workspace):
    """Test loading AGENTS.md."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "AGENTS.md").write_text("# Project\nContext here")
    
    content = ctx.load_agents_md()
    assert content is not None
    assert "Project" in content


def test_load_system_md(temp_workspace):
    """Test loading SYSTEM.md."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "SYSTEM.md").write_text("Custom system prompt")
    
    content = ctx.load_system_md()
    assert content == "Custom system prompt"


def test_load_append_system_md(temp_workspace):
    """Test loading APPEND_SYSTEM.md."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "APPEND_SYSTEM.md").write_text("Additional instructions")
    
    content = ctx.load_append_system_md()
    assert content == "Additional instructions"


def test_build_system_prompt_default(temp_workspace):
    """Test building system prompt with no overrides."""
    ctx = ContextManager(temp_workspace)
    
    default = "Default prompt"
    result = ctx.build_system_prompt(default)
    
    assert result == default


def test_build_system_prompt_with_override(temp_workspace):
    """Test system prompt with SYSTEM.md override."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "SYSTEM.md").write_text("Override prompt")
    
    default = "Default prompt"
    result = ctx.build_system_prompt(default)
    
    assert "Override prompt" in result
    assert "Default prompt" not in result


def test_build_system_prompt_with_agents_md(temp_workspace):
    """Test system prompt with AGENTS.md."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "AGENTS.md").write_text("Project context")
    
    default = "Default prompt"
    result = ctx.build_system_prompt(default)
    
    assert "Default prompt" in result
    assert "Project context" in result


def test_build_system_prompt_with_append(temp_workspace):
    """Test system prompt with APPEND_SYSTEM.md."""
    ctx = ContextManager(temp_workspace)
    
    (temp_workspace / "APPEND_SYSTEM.md").write_text("Extra instructions")
    
    default = "Default prompt"
    result = ctx.build_system_prompt(default)
    
    assert "Default prompt" in result
    assert "Extra instructions" in result


def test_find_context_files_hierarchy(temp_workspace):
    """Test finding files in hierarchy."""
    ctx = ContextManager(temp_workspace)
    
    # Create nested structure
    subdir = temp_workspace / "subdir"
    subdir.mkdir()
    
    (temp_workspace / "AGENTS.md").write_text("Parent")
    (subdir / "AGENTS.md").write_text("Child")
    
    # Search from subdir
    ctx_sub = ContextManager(subdir)
    files = ctx_sub.find_context_files("AGENTS.md")
    
    # Should find both
    assert len(files) >= 2
