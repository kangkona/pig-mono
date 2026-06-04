"""Tests for coding agent tools."""

import asyncio
import sys

import pytest
from pig_coding_agent.tools import CodeTools, FileTools, ShellTools


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_file_tools_creation(temp_workspace):
    """Test FileTools initialization."""
    tools = FileTools(str(temp_workspace))
    assert tools.workspace == temp_workspace


def test_read_file(temp_workspace):
    """Test reading a file."""
    tools = FileTools(str(temp_workspace))

    # Create test file
    test_file = temp_workspace / "test.txt"
    test_file.write_text("Hello, World!")

    # Read file
    content = tools.read_file("test.txt")
    assert content == "Hello, World!"


def test_read_nonexistent_file(temp_workspace):
    """Test reading non-existent file."""
    tools = FileTools(str(temp_workspace))

    result = tools.read_file("nonexistent.txt")
    assert "does not exist" in result


def test_write_file(temp_workspace):
    """Test writing a file."""
    tools = FileTools(str(temp_workspace))

    result = tools.write_file("output.txt", "Test content")
    assert "Successfully wrote" in result

    # Verify file was created
    output_file = temp_workspace / "output.txt"
    assert output_file.exists()
    assert output_file.read_text() == "Test content"


def test_write_file_creates_directories(temp_workspace):
    """Test writing file creates parent directories."""
    tools = FileTools(str(temp_workspace))

    result = tools.write_file("subdir/nested/file.txt", "Content")
    assert "Successfully wrote" in result

    # Verify nested file exists
    nested_file = temp_workspace / "subdir" / "nested" / "file.txt"
    assert nested_file.exists()


def test_list_files(temp_workspace):
    """Test listing files."""
    tools = FileTools(str(temp_workspace))

    # Create some files and directories
    (temp_workspace / "file1.txt").write_text("content")
    (temp_workspace / "file2.py").write_text("code")
    (temp_workspace / "subdir").mkdir()

    result = tools.list_files(".")
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir" in result


def test_list_empty_directory(temp_workspace):
    """Test listing empty directory."""
    tools = FileTools(str(temp_workspace))

    result = tools.list_files(".")
    assert "Empty directory" in result


def test_list_nonexistent_directory(temp_workspace):
    """Test listing non-existent directory."""
    tools = FileTools(str(temp_workspace))

    result = tools.list_files("nonexistent")
    assert "does not exist" in result


def test_file_exists(temp_workspace):
    """Test checking if file exists."""
    tools = FileTools(str(temp_workspace))

    # Create file
    (temp_workspace / "exists.txt").write_text("content")

    assert tools.file_exists("exists.txt") is True
    assert tools.file_exists("notexists.txt") is False


def test_path_traversal_prevention(temp_workspace):
    """Test that path traversal is prevented."""
    tools = FileTools(str(temp_workspace))

    with pytest.raises(ValueError, match="outside workspace"):
        tools.read_file("../../../etc/passwd")


def test_code_tools_generate():
    """Test code generation tool."""
    tools = CodeTools()

    result = tools.generate_code("Hello world function", "python")
    assert "python" in result.lower()
    assert "TODO" in result or "hello world" in result.lower()


def test_code_tools_explain():
    """Test code explanation tool."""
    tools = CodeTools()

    code = "def add(a, b):\n    return a + b"
    result = tools.explain_code(code)
    assert isinstance(result, str)
    assert len(result) > 0


def test_code_tools_add_type_hints():
    """Test adding type hints."""
    tools = CodeTools()

    code = "def add(a, b):\n    return a + b"
    result = tools.add_type_hints(code)
    assert "Type hints added" in result or code in result


def test_shell_tools_run_command():
    """Test running shell command."""
    tools = ShellTools()

    # Run simple command
    result = asyncio.run(tools.run_command("echo 'Hello'"))
    assert "Hello" in result


def test_shell_tools_run_command_with_error():
    """Test running command that fails."""
    tools = ShellTools()

    result = asyncio.run(tools.run_command("exit 1"))
    # Should not raise, just return output
    assert isinstance(result, str)


def test_shell_tools_timeout():
    """Test command timeout."""
    tools = ShellTools()

    # This should timeout
    result = asyncio.run(tools.run_command("sleep 100"))
    assert "timed out" in result.lower() or "error" in result.lower()


def test_shell_tools_truncates_large_line_output_without_counting_trailing_newline_twice():
    """Large single-line output should trim to a stable tail without phantom newline lines."""
    tools = ShellTools()

    command = (
        f'"{sys.executable}" -c "import sys; '
        """sys.stdout.write('X' * 300000 + '\\n')"""
        '"'
    )
    result = asyncio.run(tools.run_command(command))

    assert "[Output truncated" in result
    assert "300001" not in result
    assert result.rstrip("\n").endswith("X" * 2000)


def test_shell_tools_truncates_many_lines_without_extra_trailing_newline_line():
    """Line-limited output should ignore the final trailing newline as an extra line."""
    tools = ShellTools()

    command = (
        f'"{sys.executable}" -c "for i in range(1, 4001): '
        """print(f'line-{i:04d}')"""
        '"'
    )
    result = asyncio.run(tools.run_command(command))

    assert "[Showing lines 2001-4000 of 4000." in result
    assert "line-2001" in result
    assert "line-4000" in result
    assert "4001" not in result


def test_shell_tools_git_status():
    """Test git status command."""
    tools = ShellTools()

    result = tools.git_status()
    assert isinstance(result, str)


def test_shell_tools_git_diff():
    """Test git diff command."""
    tools = ShellTools()

    result = tools.git_diff()
    assert isinstance(result, str)


def test_shell_tools_git_diff_with_path():
    """Test git diff with specific path."""
    tools = ShellTools()

    result = tools.git_diff("README.md")
    assert isinstance(result, str)


def test_file_tools_grep(temp_workspace):
    """Test grep_files tool."""
    tools = FileTools(str(temp_workspace))

    # Create test files
    (temp_workspace / "file1.txt").write_text("Hello world\nFoo bar\nHello again")
    (temp_workspace / "file2.txt").write_text("No match here")

    result = tools.grep_files("Hello", ".")

    assert "file1.txt" in result
    assert "Hello world" in result
    assert "Hello again" in result


def test_file_tools_grep_no_match(temp_workspace):
    """Test grep with no matches."""
    tools = FileTools(str(temp_workspace))

    (temp_workspace / "file.txt").write_text("Nothing here")

    result = tools.grep_files("NoMatch", ".")

    assert "No matches" in result


def test_file_tools_find(temp_workspace):
    """Test find_files tool."""
    tools = FileTools(str(temp_workspace))

    # Create test files
    (temp_workspace / "test.py").write_text("code")
    (temp_workspace / "test.txt").write_text("text")
    subdir = temp_workspace / "subdir"
    subdir.mkdir()
    (subdir / "nested.py").write_text("more code")

    result = tools.find_files("*.py", ".")

    assert "test.py" in result
    assert "nested.py" in result
    assert "test.txt" not in result


def test_file_tools_ls_detailed(temp_workspace):
    """Test ls_detailed tool."""
    tools = FileTools(str(temp_workspace))

    # Create files
    (temp_workspace / "file.txt").write_text("content")
    (temp_workspace / "subdir").mkdir()

    result = tools.ls_detailed(".")

    assert "file.txt" in result
    assert "subdir" in result
    assert "KB" in result or "<DIR>" in result


def test_run_command_killed_when_turn_cancelled(tmp_path):
    """Cancelling the turn mid-command kills the subprocess (registry cancel-race)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    tools = ShellTools()
    bound = tools.run_command  # descriptor returns a bound Tool
    registry = ToolRegistry()
    registry.register("run_command", bound.func, bound.to_openai_schema())

    sentinel = tmp_path / "done.txt"
    # Sleeps, then writes the sentinel. If the process is killed first, the
    # sentinel never appears.
    cmd = f'sleep 3 && touch "{sentinel}"'
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": cmd}))
    )

    async def drive():
        cancel = asyncio.Event()
        task = asyncio.ensure_future(registry.execute(tool_call, "default", {}, cancel))
        await asyncio.sleep(0.5)  # let the subprocess start
        cancel.set()  # user pressed Esc
        return await task

    result = asyncio.run(drive())

    assert result.ok is False
    assert not sentinel.exists()  # the sleep was killed before it could touch the file


def test_run_command_cancel_none_is_unaffected():
    """With no cancel event the tool runs to completion (no-op cancel-race path)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    tools = ShellTools()
    bound = tools.run_command
    registry = ToolRegistry()
    registry.register("run_command", bound.func, bound.to_openai_schema())

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "echo hi"}))
    )
    result = asyncio.run(registry.execute(tool_call, "default", {}, None))

    assert result.ok is True
    assert "hi" in str(result.data)


def test_execute_sync_drives_async_run_command():
    """The synchronous run() path must drive the async run_command to a result.

    Regression: making run_command async returned an un-awaited coroutine via
    registry.execute_sync, breaking shell tools on the sync agent loop.
    """
    from pig_agent_core.tools.registry import ToolRegistry

    tools = ShellTools()
    bound = tools.run_command
    registry = ToolRegistry()
    registry.register("run_command", bound.func, bound.to_openai_schema())

    result = registry.execute_sync("run_command", {"command": "echo hi"})

    assert result.ok is True
    assert "hi" in str(result.data)
