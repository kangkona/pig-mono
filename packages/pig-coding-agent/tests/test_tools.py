"""Tests for coding agent tools."""

import asyncio
import sys

import pytest
from pig_coding_agent.tools import FileTools, ShellTools, build_coding_tools


def _run_cmd(command: str, cwd: str | None = None, exclude_from_context: bool = False) -> str:
    """Drive run_command via the registry for tests (canonical path)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".")
    registry.register_package(schemas, handlers, is_core=True)
    args = {"command": command}
    if cwd is not None:
        args["cwd"] = cwd
    if exclude_from_context:
        args["exclude_from_context"] = True
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps(args))
    )
    result = asyncio.run(registry.execute(tool_call, "default", {}, None))
    return result.data if result.ok else result.error or ""


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


def test_shell_tools_run_command():
    """Test running shell command."""
    result = _run_cmd("echo 'Hello'")
    assert "Hello" in result


def test_shell_tools_run_command_with_error():
    """Test running command that fails."""
    result = _run_cmd("exit 1")
    assert isinstance(result, str)


def test_shell_tools_timeout():
    """Test command timeout."""
    result = _run_cmd("sleep 100")
    assert "timed out" in result.lower() or "error" in result.lower()


def test_shell_tools_truncates_large_line_output_without_counting_trailing_newline_twice():
    """Large single-line output should trim to a stable tail without phantom newline lines."""
    command = (
        f'"{sys.executable}" -c "import sys; '
        """sys.stdout.write('X' * 300000 + '\\n')"""
        '"'
    )
    result = _run_cmd(command)

    assert "[Output truncated" in result
    assert "300001" not in result
    # Strip CR as well as LF: on Windows stdout text mode turns the command's
    # trailing "\n" into "\r\n", and rstrip("\n") alone would leave a "\r".
    assert result.rstrip("\r\n").endswith("X" * 2000)


def test_shell_tools_truncates_many_lines_without_extra_trailing_newline_line():
    """Line-limited output should ignore the final trailing newline as an extra line."""
    command = (
        f'"{sys.executable}" -c "for i in range(1, 4001): '
        """print(f'line-{i:04d}')"""
        '"'
    )
    result = _run_cmd(command)

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

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".")
    registry.register_package(schemas, handlers, is_core=True)

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

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".")
    registry.register_package(schemas, handlers, is_core=True)

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

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".")
    registry.register_package(schemas, handlers, is_core=True)

    result = registry.execute_sync("run_command", {"command": "echo hi"})

    assert result.ok is True
    assert "hi" in str(result.data)


# ---------------------------------------------------------------------------
# Fake-operations tests: verify routing through the ops layer without real I/O
# ---------------------------------------------------------------------------


class _FakeFileOperations:
    """In-memory filesystem stub for unit tests."""

    def __init__(self):
        self._files: dict = {}  # path str → content str
        self._dirs: set = set()  # path strs that are directories
        self.calls: list = []  # recorded method calls

    def _record(self, method, *args):
        self.calls.append((method,) + args)

    def seed(self, path_str: str, content: str):
        from pathlib import Path

        self._files[str(Path(path_str).resolve())] = content

    def seed_dir(self, path_str: str):
        from pathlib import Path

        self._dirs.add(str(Path(path_str).resolve()))

    def exists(self, path):
        self._record("exists", path)
        return str(path) in self._files or str(path) in self._dirs

    def is_file(self, path):
        return str(path) in self._files

    def is_dir(self, path):
        return str(path) in self._dirs

    def read_text(self, path):
        self._record("read_text", path)
        return self._files.get(str(path), "")

    def write_text(self, path, content):
        self._record("write_text", path)
        self._files[str(path)] = content

    def mkdir(self, path, *, parents=True, exist_ok=True):
        self._record("mkdir", path)
        self._dirs.add(str(path))

    def iterdir(self, path):
        prefix = str(path) + "/"
        seen = set()
        results = []
        for p in list(self._files) + list(self._dirs):
            if p.startswith(prefix):
                child = p[len(prefix) :].split("/")[0]
                child_path = path / child
                if str(child_path) not in seen:
                    seen.add(str(child_path))
                    results.append(child_path)
        return results

    def glob(self, path, pattern):
        return [
            p
            for p in [__import__("pathlib").Path(f) for f in self._files]
            if p.parent == path or str(p).startswith(str(path) + "/")
        ]

    def rglob(self, path, pattern):
        import fnmatch
        from pathlib import Path as P

        return [
            P(f)
            for f in self._files
            if fnmatch.fnmatch(P(f).name, pattern) and str(f).startswith(str(path))
        ]

    def stat(self, path):
        from unittest.mock import MagicMock

        s = MagicMock()
        s.st_size = len(self._files.get(str(path), "").encode())
        s.st_mtime = 0.0
        return s


class _FakeShellOperations:
    """Subprocess stub that records calls and returns preset output."""

    def __init__(self, async_output: str = "fake output", sync_output: str = "fake sync"):
        self._async_output = async_output
        self._sync_output = sync_output
        self.async_calls: list = []
        self.sync_calls: list = []
        self.on_data_received: list = []

    async def exec_async(self, command, cwd, timeout, on_data=None):
        self.async_calls.append({"command": command, "cwd": cwd, "on_data": on_data})
        if on_data:
            on_data(self._async_output)
            self.on_data_received.append(self._async_output)
        return self._async_output

    def exec_sync(self, command, cwd, timeout):
        self.sync_calls.append({"command": command, "cwd": cwd})
        return self._sync_output


def test_file_tools_route_read_through_ops(tmp_path):
    """read_file must use ops.read_text, not Path.read_text directly."""
    fake = _FakeFileOperations()
    fake.seed(str(tmp_path / "hello.txt"), "ops content")

    tools = FileTools(str(tmp_path), ops=fake)
    result = tools.read_file("hello.txt")

    assert result == "ops content"
    methods = [c[0] for c in fake.calls]
    assert "read_text" in methods


def test_file_tools_route_write_through_ops(tmp_path):
    """write_file must use ops.write_text."""
    fake = _FakeFileOperations()
    fake.seed_dir(str(tmp_path))
    fake.seed_dir(str(tmp_path / "sub"))

    tools = FileTools(str(tmp_path), ops=fake)
    tools.write_file("sub/out.txt", "written")

    methods = [c[0] for c in fake.calls]
    assert "write_text" in methods
    assert fake._files.get(str(tmp_path / "sub" / "out.txt")) == "written"


def test_file_tools_route_exists_through_ops(tmp_path):
    """file_exists must use ops.exists."""
    fake = _FakeFileOperations()
    tools = FileTools(str(tmp_path), ops=fake)
    tools.file_exists("anything.txt")

    assert any(c[0] == "exists" for c in fake.calls)


def test_shell_tools_route_async_through_ops():
    """run_command must use ops.exec_async and return its output."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    fake = _FakeShellOperations(async_output="hello from fake")
    schemas, handlers = build_coding_tools(".", shell_ops=fake)

    registry = ToolRegistry()
    registry.register_package(schemas, handlers, is_core=True)

    tool_call = SimpleNamespace(
        function=SimpleNamespace(
            name="run_command", arguments=json.dumps({"command": "echo ignored"})
        )
    )
    result = asyncio.run(registry.execute(tool_call, "default", {}, None))

    assert result.ok is True
    assert "hello from fake" in str(result.data)
    assert len(fake.async_calls) == 1
    assert fake.async_calls[0]["command"] == "echo ignored"


def test_shell_tools_on_update_forwarded_to_exec_async():
    """on_update from registry.execute() must reach ops.exec_async as on_data."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    chunks_received: list = []
    fake = _FakeShellOperations(async_output="streaming chunk")
    schemas, handlers = build_coding_tools(".", shell_ops=fake)

    registry = ToolRegistry()
    registry.register_package(schemas, handlers, is_core=True)

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "echo hi"}))
    )

    def _on_update(chunk: str) -> None:
        chunks_received.append(chunk)

    asyncio.run(registry.execute(tool_call, "default", {}, None, on_update=_on_update))

    assert chunks_received == ["streaming chunk"]
    assert fake.async_calls[0]["on_data"] is not None


def test_shell_tools_route_sync_through_ops():
    """git_status (sync shell) must use ops.exec_sync."""
    fake = _FakeShellOperations(sync_output="M  file.txt")
    tools = ShellTools(ops=fake)
    result = tools.git_status()

    assert "file.txt" in result
    assert len(fake.sync_calls) == 1
    assert "git status" in fake.sync_calls[0]["command"]
