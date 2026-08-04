"""Tests for coding agent tools."""

import asyncio
import sys
from typing import Any

import pytest
from pig_coding_agent import permissions
from pig_coding_agent.permissions import PermissionPolicy
from pig_coding_agent.tools import FileTools, build_coding_tools


def _run_cmd(
    command: str,
    cwd: str | None = None,
    exclude_from_context: bool = False,
    permission_policy: PermissionPolicy | None = None,
) -> str:
    """Drive run_command via the registry for tests (canonical path)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".", permission_policy=permission_policy)
    registry.register_package(schemas, handlers, is_core=True)
    args: dict[str, object] = {"command": command}
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
def temp_workspace(tmp_path: Any) -> Any:
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_file_tools_creation(temp_workspace: Any) -> None:
    """Test FileTools initialization."""
    tools = FileTools(str(temp_workspace))
    assert tools.workspace == temp_workspace


def test_read_file(temp_workspace: Any) -> None:
    """Test reading a file."""
    tools = FileTools(str(temp_workspace))

    # Create test file
    test_file = temp_workspace / "test.txt"
    test_file.write_text("Hello, World!")

    # Read file
    content = tools.read_file("test.txt")
    assert content == "Hello, World!"


def test_read_nonexistent_file(temp_workspace: Any) -> None:
    """Test reading non-existent file."""
    tools = FileTools(str(temp_workspace))

    result = tools.read_file("nonexistent.txt")
    assert "does not exist" in result


def test_file_tools_reject_prefix_sibling_outside_workspace(temp_workspace: Any) -> None:
    sibling = temp_workspace.parent / f"{temp_workspace.name}-sibling"
    sibling.mkdir()
    outside_file = sibling / "outside.txt"
    outside_file.write_text("outside")
    tools = FileTools(str(temp_workspace))

    with pytest.raises(ValueError, match="outside workspace"):
        tools.read_file(str(outside_file))


def test_write_file(temp_workspace: Any) -> None:
    """Test writing a file."""
    tools = FileTools(str(temp_workspace), permission_policy=PermissionPolicy.allow_all())

    result = tools.write_file("output.txt", "Test content")
    assert "Successfully wrote" in result

    # Verify file was created
    output_file = temp_workspace / "output.txt"
    assert output_file.exists()
    assert output_file.read_text() == "Test content"


def test_write_file_creates_directories(temp_workspace: Any) -> None:
    """Test writing file creates parent directories."""
    tools = FileTools(str(temp_workspace), permission_policy=PermissionPolicy.allow_all())

    result = tools.write_file("subdir/nested/file.txt", "Content")
    assert "Successfully wrote" in result

    # Verify nested file exists
    nested_file = temp_workspace / "subdir" / "nested" / "file.txt"
    assert nested_file.exists()


def test_list_files(temp_workspace: Any) -> None:
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


def test_list_empty_directory(temp_workspace: Any) -> None:
    """Test listing empty directory."""
    tools = FileTools(str(temp_workspace))

    result = tools.list_files(".")
    assert "Empty directory" in result


def test_list_nonexistent_directory(temp_workspace: Any) -> None:
    """Test listing non-existent directory."""
    tools = FileTools(str(temp_workspace))

    result = tools.list_files("nonexistent")
    assert "does not exist" in result


def test_file_exists(temp_workspace: Any) -> None:
    """Test checking if file exists."""
    tools = FileTools(str(temp_workspace))

    # Create file
    (temp_workspace / "exists.txt").write_text("content")

    assert tools.file_exists("exists.txt") is True
    assert tools.file_exists("notexists.txt") is False


def test_path_traversal_prevention(temp_workspace: Any) -> None:
    """Test that path traversal is prevented."""
    tools = FileTools(str(temp_workspace))

    with pytest.raises(ValueError, match="outside workspace"):
        tools.read_file("../../../etc/passwd")


def test_shell_tools_run_command() -> None:
    """Test running shell command."""
    result = _run_cmd("echo 'Hello'", permission_policy=PermissionPolicy.allow_all())
    assert "Hello" in result


def test_shell_tools_run_command_with_error() -> None:
    """Test running command that fails."""
    result = _run_cmd("exit 1", permission_policy=PermissionPolicy.allow_all())
    assert isinstance(result, str)


def test_shell_tools_timeout() -> None:
    """Test command timeout."""
    result = _run_cmd("sleep 100", permission_policy=PermissionPolicy.allow_all())
    assert "timed out" in result.lower() or "error" in result.lower()


def test_shell_tools_truncates_large_line_output_without_counting_trailing_newline_twice() -> None:
    """Large single-line output should trim to a stable tail without phantom newline lines."""
    command = (
        f'"{sys.executable}" -c "import sys; '
        """sys.stdout.write('X' * 300000 + '\\n')"""
        '"'
    )
    result = _run_cmd(command, permission_policy=PermissionPolicy.allow_all())

    assert "[Output truncated" in result
    assert "300001" not in result
    # Strip CR as well as LF: on Windows stdout text mode turns the command's
    # trailing "\n" into "\r\n", and rstrip("\n") alone would leave a "\r".
    assert result.rstrip("\r\n").endswith("X" * 2000)


def test_shell_tools_truncates_many_lines_without_extra_trailing_newline_line() -> None:
    """Line-limited output should ignore the final trailing newline as an extra line."""
    command = (
        f'"{sys.executable}" -c "for i in range(1, 4001): '
        """print(f'line-{i:04d}')"""
        '"'
    )
    result = _run_cmd(command, permission_policy=PermissionPolicy.allow_all())

    assert "[Showing lines 2001-4000 of 4000." in result
    assert "line-2001" in result
    assert "line-4000" in result
    assert "4001" not in result


def test_build_coding_tools_does_not_expose_git_mutation_or_status_tools() -> None:
    """Git-specific helpers should not be exposed as first-class model tools."""
    schemas, handlers = build_coding_tools(".", permission_policy=PermissionPolicy.allow_all())
    names = {schema["function"]["name"] for schema in schemas}

    assert "git_status" not in names
    assert "git_diff" not in names
    assert "git_commit" not in names
    assert "git_push" not in names
    assert "git_branch" not in names
    assert "git_log" not in names
    assert "git_status" not in handlers
    assert "git_commit" not in handlers


def test_file_tools_grep(temp_workspace: Any) -> None:
    """Test grep_files tool."""
    tools = FileTools(str(temp_workspace))

    # Create test files
    (temp_workspace / "file1.txt").write_text("Hello world\nFoo bar\nHello again")
    (temp_workspace / "file2.txt").write_text("No match here")

    result = tools.grep_files("Hello", ".")

    assert "file1.txt" in result
    assert "Hello world" in result
    assert "Hello again" in result


def test_file_tools_grep_no_match(temp_workspace: Any) -> None:
    """Test grep with no matches."""
    tools = FileTools(str(temp_workspace))

    (temp_workspace / "file.txt").write_text("Nothing here")

    result = tools.grep_files("NoMatch", ".")

    assert "No matches" in result


def test_file_tools_find(temp_workspace: Any) -> None:
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


def test_file_tools_ls_detailed(temp_workspace: Any) -> None:
    """Test ls_detailed tool."""
    tools = FileTools(str(temp_workspace))

    # Create files
    (temp_workspace / "file.txt").write_text("content")
    (temp_workspace / "subdir").mkdir()

    result = tools.ls_detailed(".")

    assert "file.txt" in result
    assert "subdir" in result
    assert "KB" in result or "<DIR>" in result


def test_run_command_killed_when_turn_cancelled(tmp_path: Any) -> None:
    """Cancelling the turn mid-command kills the subprocess (registry cancel-race)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".", permission_policy=PermissionPolicy.allow_all())
    registry.register_package(schemas, handlers, is_core=True)

    sentinel = tmp_path / "done.txt"
    # Sleeps, then writes the sentinel. If the process is killed first, the
    # sentinel never appears.
    cmd = f'sleep 3 && touch "{sentinel}"'
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": cmd}))
    )

    async def drive() -> Any:
        cancel = asyncio.Event()
        task = asyncio.ensure_future(registry.execute(tool_call, "default", {}, cancel))
        await asyncio.sleep(0.5)  # let the subprocess start
        cancel.set()  # user pressed Esc
        return await task

    result = asyncio.run(drive())

    assert result.ok is False
    assert not sentinel.exists()  # the sleep was killed before it could touch the file


def test_run_command_cancel_none_is_unaffected() -> None:
    """With no cancel event the tool runs to completion (no-op cancel-race path)."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".", permission_policy=PermissionPolicy.allow_all())
    registry.register_package(schemas, handlers, is_core=True)

    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "echo hi"}))
    )
    result = asyncio.run(registry.execute(tool_call, "default", {}, None))

    assert result.ok is True
    assert "hi" in str(result.data)


def test_execute_sync_drives_async_run_command() -> None:
    """The synchronous run() path must drive the async run_command to a result.

    Regression: making run_command async returned an un-awaited coroutine via
    registry.execute_sync, breaking shell tools on the sync agent loop.
    """
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(".", permission_policy=PermissionPolicy.allow_all())
    registry.register_package(schemas, handlers, is_core=True)

    result = registry.execute_sync("run_command", {"command": "echo hi"})

    assert result.ok is True
    assert "hi" in str(result.data)


# ---------------------------------------------------------------------------
# Fake-operations tests: verify routing through the ops layer without real I/O
# ---------------------------------------------------------------------------


class _FakeFileOperations:
    """In-memory filesystem stub for unit tests."""

    def __init__(self: Any) -> None:
        self._files: dict = {}  # path str → content str
        self._dirs: set = set()  # path strs that are directories
        self.calls: list = []  # recorded method calls

    def _record(self: Any, method: Any, *args: Any) -> Any:
        self.calls.append((method,) + args)

    def seed(self: Any, path_str: str, content: str) -> Any:
        from pathlib import Path

        self._files[str(Path(path_str).resolve())] = content

    def seed_dir(self: Any, path_str: str) -> Any:
        from pathlib import Path

        self._dirs.add(str(Path(path_str).resolve()))

    def exists(self: Any, path: Any) -> Any:
        self._record("exists", path)
        return str(path) in self._files or str(path) in self._dirs

    def is_file(self: Any, path: Any) -> Any:
        return str(path) in self._files

    def is_dir(self: Any, path: Any) -> Any:
        return str(path) in self._dirs

    def read_text(self: Any, path: Any) -> Any:
        self._record("read_text", path)
        return self._files.get(str(path), "")

    def write_text(self: Any, path: Any, content: Any) -> Any:
        self._record("write_text", path)
        self._files[str(path)] = content

    def mkdir(self: Any, path: Any, *, parents: Any = True, exist_ok: Any = True) -> Any:
        self._record("mkdir", path)
        self._dirs.add(str(path))

    def iterdir(self: Any, path: Any) -> Any:
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

    def glob(self: Any, path: Any, pattern: Any) -> Any:
        return [
            p
            for p in [__import__("pathlib").Path(f) for f in self._files]
            if p.parent == path or str(p).startswith(str(path) + "/")
        ]

    def rglob(self: Any, path: Any, pattern: Any) -> Any:
        import fnmatch
        from pathlib import Path as P

        return [
            P(f)
            for f in self._files
            if fnmatch.fnmatch(P(f).name, pattern) and str(f).startswith(str(path))
        ]

    def stat(self: Any, path: Any) -> Any:
        from unittest.mock import MagicMock

        s = MagicMock()
        s.st_size = len(self._files.get(str(path), "").encode())
        s.st_mtime = 0.0
        return s


class _FakeShellOperations:
    """Subprocess stub that records calls and returns preset output."""

    def __init__(
        self: Any, async_output: str = "fake output", sync_output: str = "fake sync"
    ) -> None:
        self._async_output = async_output
        self._sync_output = sync_output
        self.async_calls: list = []
        self.sync_calls: list = []
        self.on_data_received: list = []

    async def exec_async(
        self: Any, command: Any, cwd: Any, timeout: Any, on_data: Any = None
    ) -> Any:
        self.async_calls.append({"command": command, "cwd": cwd, "on_data": on_data})
        if on_data:
            on_data(self._async_output)
            self.on_data_received.append(self._async_output)
        return self._async_output

    def exec_sync(self: Any, command: Any, cwd: Any, timeout: Any) -> Any:
        self.sync_calls.append({"command": command, "cwd": cwd})
        return self._sync_output


def test_file_tools_route_read_through_ops(tmp_path: Any) -> None:
    """read_file must use ops.read_text, not Path.read_text directly."""
    fake = _FakeFileOperations()
    fake.seed(str(tmp_path / "hello.txt"), "ops content")

    tools = FileTools(str(tmp_path), ops=fake)
    result = tools.read_file("hello.txt")

    assert result == "ops content"
    methods = [c[0] for c in fake.calls]
    assert "read_text" in methods


def test_file_tools_route_write_through_ops(tmp_path: Any) -> None:
    """write_file must use ops.write_text."""
    fake = _FakeFileOperations()
    fake.seed_dir(str(tmp_path))
    fake.seed_dir(str(tmp_path / "sub"))

    tools = FileTools(str(tmp_path), ops=fake, permission_policy=PermissionPolicy.allow_all())
    tools.write_file("sub/out.txt", "written")

    methods = [c[0] for c in fake.calls]
    assert "write_text" in methods
    assert fake._files.get(str(tmp_path / "sub" / "out.txt")) == "written"


def test_file_tools_route_exists_through_ops(tmp_path: Any) -> None:
    """file_exists must use ops.exists."""
    fake = _FakeFileOperations()
    tools = FileTools(str(tmp_path), ops=fake)
    tools.file_exists("anything.txt")

    assert any(c[0] == "exists" for c in fake.calls)


def test_shell_tools_route_async_through_ops() -> None:
    """run_command must use ops.exec_async and return its output."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    fake = _FakeShellOperations(async_output="hello from fake")
    schemas, handlers = build_coding_tools(
        ".",
        shell_ops=fake,
        permission_policy=PermissionPolicy.allow_all(),
    )

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


def test_shell_tools_on_update_forwarded_to_exec_async() -> None:
    """on_update from registry.execute() must reach ops.exec_async as on_data."""
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    chunks_received: list = []
    fake = _FakeShellOperations(async_output="streaming chunk")
    schemas, handlers = build_coding_tools(
        ".",
        shell_ops=fake,
        permission_policy=PermissionPolicy.allow_all(),
    )

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


def test_write_file_requires_permission_by_default(tmp_path: Any) -> None:
    """Default file writes are denied unless the caller supplies a policy."""
    tools = FileTools(str(tmp_path))

    result = tools.write_file("blocked.txt", "should not write")

    assert "Permission denied" in result
    assert not (tmp_path / "blocked.txt").exists()


def test_write_file_can_be_confirmed_by_policy(tmp_path: Any) -> None:
    decisions = []

    def confirm(request: Any) -> Any:
        decisions.append((request.action, request.target))
        return True

    tools = FileTools(
        str(tmp_path),
        permission_policy=PermissionPolicy.confirm_all(confirm),
    )

    result = tools.write_file("allowed.txt", "ok")

    assert "Successfully wrote" in result
    assert (tmp_path / "allowed.txt").read_text() == "ok"
    assert decisions == [("write_file", str(tmp_path / "allowed.txt"))]


def test_write_file_custom_deny_reason_surfaces_as_tool_failure() -> None:
    """Custom deny reasons must still propagate as ok=False at registry level."""
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    schemas, handlers = build_coding_tools(
        ".",
        permission_policy=PermissionPolicy.deny_all("blocked by policy"),
    )
    registry.register_package(schemas, handlers, is_core=True)

    result = registry.execute_sync("write_file", {"path": "blocked.txt", "content": "x"})

    assert result.ok is False
    assert result.error == "blocked by policy"
    assert result.meta["permission_denial"]["code"] == permissions.PERMISSION_DENIED_CODE
    assert result.meta["permission_denial"]["action"] == "write_file"


def test_run_command_requires_permission_by_default() -> None:
    """Default shell execution is denied unless the caller supplies a policy."""
    result = _run_cmd("echo denied")

    assert "Permission denied" in result


def test_run_command_can_be_denied_by_policy() -> None:
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    fake = _FakeShellOperations(async_output="should not run")
    schemas, handlers = build_coding_tools(
        ".",
        shell_ops=fake,
        permission_policy=PermissionPolicy.deny_all("test deny"),
    )
    registry = ToolRegistry()
    registry.register_package(schemas, handlers, is_core=True)
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "echo hi"}))
    )

    result = asyncio.run(registry.execute(tool_call, "default", {}, None))

    assert result.ok is False
    assert "test deny" in (result.error or "")
    assert result.meta["permission_denial"]["code"] == permissions.PERMISSION_DENIED_CODE
    assert result.meta["permission_denial"]["action"] == "run_command"
    assert fake.async_calls == []


def test_run_command_can_be_confirmed_by_policy() -> None:
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.registry import ToolRegistry

    decisions = []

    def confirm(request: Any) -> Any:
        decisions.append((request.action, request.target))
        return True

    fake = _FakeShellOperations(sync_output="M  file.txt")
    schemas, handlers = build_coding_tools(
        ".",
        shell_ops=fake,
        permission_policy=PermissionPolicy.confirm_all(confirm),
    )
    registry = ToolRegistry()
    registry.register_package(schemas, handlers, is_core=True)
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="run_command", arguments=json.dumps({"command": "echo hi"}))
    )

    result = asyncio.run(registry.execute(tool_call, "default", {}, None))

    assert result.ok is True
    assert "fake output" in str(result.data)
    assert decisions == [("run_command", "echo hi")]
