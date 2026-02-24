"""Tests for file reference system."""

import pytest
from pathlib import Path
from pig_coding_agent.file_reference import FileReferenceParser


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temp workspace with files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    # Create test files
    (workspace / "main.py").write_text("def main():\n    print('hello')")
    (workspace / "README.md").write_text("# Project\nDescription")
    
    src_dir = workspace / "src"
    src_dir.mkdir()
    (src_dir / "utils.py").write_text("def util():\n    pass")
    
    return workspace


def test_file_reference_parser_creation(temp_workspace):
    """Test creating parser."""
    parser = FileReferenceParser(temp_workspace)
    assert parser.workspace == temp_workspace


def test_parse_references(temp_workspace):
    """Test parsing @references."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Review @main.py and @README.md"
    refs = parser.parse_references(text)
    
    assert len(refs) == 2
    assert "main.py" in refs
    assert "README.md" in refs


def test_parse_path_references(temp_workspace):
    """Test parsing @path/file references."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Check @src/utils.py"
    refs = parser.parse_references(text)
    
    assert len(refs) == 1
    assert "src/utils.py" in refs


def test_resolve_file_exists(temp_workspace):
    """Test resolving existing file."""
    parser = FileReferenceParser(temp_workspace)
    
    exists, path, content = parser.resolve_file("main.py")
    
    assert exists
    assert path.name == "main.py"
    assert "def main()" in content


def test_resolve_file_not_found(temp_workspace):
    """Test resolving non-existent file."""
    parser = FileReferenceParser(temp_workspace)
    
    exists, path, error = parser.resolve_file("nonexistent.py")
    
    assert not exists
    assert "not found" in error.lower()


def test_resolve_nested_file(temp_workspace):
    """Test resolving nested file."""
    parser = FileReferenceParser(temp_workspace)
    
    exists, path, content = parser.resolve_file("src/utils.py")
    
    assert exists
    assert "def util()" in content


def test_expand_references(temp_workspace):
    """Test expanding references."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Review @main.py"
    expanded = parser.expand_references(text)
    
    assert "Review @main.py" in expanded
    assert "def main()" in expanded
    assert "--- File:" in expanded


def test_expand_multiple_references(temp_workspace):
    """Test expanding multiple references."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Compare @main.py and @README.md"
    expanded = parser.expand_references(text)
    
    assert "def main()" in expanded
    assert "# Project" in expanded


def test_get_preview(temp_workspace):
    """Test getting reference preview."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Review @main.py"
    preview = parser.get_reference_preview(text)
    
    assert "main.py" in preview
    assert "lines" in preview
    assert "bytes" in preview


def test_security_outside_workspace(temp_workspace):
    """Test security - prevent accessing outside workspace."""
    parser = FileReferenceParser(temp_workspace)
    
    exists, path, error = parser.resolve_file("../../etc/passwd")
    
    assert not exists
    assert "outside workspace" in error.lower()


def test_no_references(temp_workspace):
    """Test text without references."""
    parser = FileReferenceParser(temp_workspace)
    
    text = "Hello world"
    refs = parser.parse_references(text)
    
    assert len(refs) == 0
    
    expanded = parser.expand_references(text)
    assert expanded == text
