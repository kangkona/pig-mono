"""Tests for file reference system."""

from typing import Any

import pytest
from pig_coding_agent.file_reference import FileReferenceParser


@pytest.fixture
def temp_workspace(tmp_path: Any) -> Any:
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


def test_file_reference_parser_creation(temp_workspace: Any) -> None:
    """Test creating parser."""
    parser = FileReferenceParser(temp_workspace)
    assert parser.workspace == temp_workspace


def test_parse_references(temp_workspace: Any) -> None:
    """Test parsing @references."""
    parser = FileReferenceParser(temp_workspace)

    text = "Review @main.py and @README.md"
    refs = parser.parse_references(text)

    assert len(refs) == 2
    assert "main.py" in refs
    assert "README.md" in refs


def test_parse_path_references(temp_workspace: Any) -> None:
    """Test parsing @path/file references."""
    parser = FileReferenceParser(temp_workspace)

    text = "Check @src/utils.py"
    refs = parser.parse_references(text)

    assert len(refs) == 1
    assert "src/utils.py" in refs


def test_resolve_file_exists(temp_workspace: Any) -> None:
    """Test resolving existing file."""
    parser = FileReferenceParser(temp_workspace)

    exists, path, content = parser.resolve_file("main.py")

    assert exists
    assert path.name == "main.py"
    assert "def main()" in content


def test_resolve_file_not_found(temp_workspace: Any) -> None:
    """Test resolving non-existent file."""
    parser = FileReferenceParser(temp_workspace)

    exists, path, error = parser.resolve_file("nonexistent.py")

    assert not exists
    assert "not found" in error.lower()


def test_resolve_nested_file(temp_workspace: Any) -> None:
    """Test resolving nested file."""
    parser = FileReferenceParser(temp_workspace)

    exists, path, content = parser.resolve_file("src/utils.py")

    assert exists
    assert "def util()" in content


def test_expand_references(temp_workspace: Any) -> None:
    """Test expanding references."""
    parser = FileReferenceParser(temp_workspace)

    text = "Review @main.py"
    expanded = parser.expand_references(text)

    assert "Review @main.py" in expanded
    assert "def main()" in expanded
    assert "--- File:" in expanded


def test_expand_multiple_references(temp_workspace: Any) -> None:
    """Test expanding multiple references."""
    parser = FileReferenceParser(temp_workspace)

    text = "Compare @main.py and @README.md"
    expanded = parser.expand_references(text)

    assert "def main()" in expanded
    assert "# Project" in expanded


def test_get_preview(temp_workspace: Any) -> None:
    """Test getting reference preview."""
    parser = FileReferenceParser(temp_workspace)

    text = "Review @main.py"
    preview = parser.get_reference_preview(text)

    assert "main.py" in preview
    assert "lines" in preview
    assert "bytes" in preview


def test_get_preview_hyperlinks_file_paths_when_supported(
    temp_workspace: Any, monkeypatch: Any
) -> None:
    parser = FileReferenceParser(temp_workspace)
    monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
    monkeypatch.delenv("NO_COLOR", raising=False)

    preview = parser.get_reference_preview("Review @main.py")

    assert "\033]8;;file://" in preview
    assert "main.py" in preview


def test_security_outside_workspace(temp_workspace: Any) -> None:
    """Test security - prevent accessing outside workspace."""
    parser = FileReferenceParser(temp_workspace)

    exists, path, error = parser.resolve_file("../../etc/passwd")

    assert not exists
    assert "outside workspace" in error.lower()


def test_no_references(temp_workspace: Any) -> None:
    """Test text without references."""
    parser = FileReferenceParser(temp_workspace)

    text = "Hello world"
    refs = parser.parse_references(text)

    assert len(refs) == 0

    expanded = parser.expand_references(text)
    assert expanded == text
