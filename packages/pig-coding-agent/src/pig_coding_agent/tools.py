"""Built-in tools for the coding agent.

Tools are authored in the new-registry style: plain handler methods plus
explicit OpenAI function-calling schemas, registered in bulk via
``ToolRegistry.register_package``. ``build_coding_tools`` is the single entry
point that binds handler state (workspace) and returns ``(schemas, handlers)``.

I/O is routed through ``FileOperations`` / ``ShellOperations`` protocols so the
same tool logic can be exercised against a fake backend in tests, or redirected
to a remote / sandboxed backend without modifying tool code.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .operations import FileOperations, LocalFileOperations, LocalShellOperations, ShellOperations
from .permissions import PermissionPolicy

MAX_COMMAND_OUTPUT_BYTES = 64_000
MAX_COMMAND_OUTPUT_LINES = 2_000


def _truncate_command_output(output: str) -> str:
    """Truncate shell output to a predictable tail-focused summary."""
    if not output:
        return output

    had_trailing_newline = output.endswith("\n")
    logical_output = output[:-1] if had_trailing_newline else output
    lines = logical_output.split("\n") if logical_output else []

    if len(lines) > MAX_COMMAND_OUTPUT_LINES:
        kept = lines[-MAX_COMMAND_OUTPUT_LINES:]
        start_line = len(lines) - MAX_COMMAND_OUTPUT_LINES + 1
        truncated = "\n".join(kept)
        return (
            f"{truncated}\n"
            f"[Showing lines {start_line}-{len(lines)} of {len(lines)}. Full output truncated.]"
        )

    encoded = logical_output.encode("utf-8")
    if len(encoded) > MAX_COMMAND_OUTPUT_BYTES:
        tail = encoded[-MAX_COMMAND_OUTPUT_BYTES:]
        while tail and (tail[0] & 0xC0) == 0x80:
            tail = tail[1:]
        truncated = tail.decode("utf-8", errors="ignore")
        return f"[Output truncated to last {MAX_COMMAND_OUTPUT_BYTES} bytes]\n{truncated}"

    return output


class FileTools:
    """File operation tools backed by a pluggable FileOperations backend."""

    def __init__(
        self,
        workspace: str = ".",
        ops: FileOperations | None = None,
        permission_policy: PermissionPolicy | None = None,
    ):
        """Initialize file tools.

        Args:
            workspace: Workspace directory (all paths are sandboxed inside it).
            ops: Filesystem backend. Defaults to ``LocalFileOperations()`` which
                uses the real local filesystem. Pass a fake/stub for testing or a
                custom backend for remote execution.
        """
        self.workspace = Path(workspace).resolve()
        self.ops: FileOperations = ops if ops is not None else LocalFileOperations()
        self.permission_policy = permission_policy or PermissionPolicy.deny_all()

    def _resolve_path(self, path: str) -> Path:
        """Resolve path within workspace."""
        full_path = (self.workspace / path).resolve()
        if not str(full_path).startswith(str(self.workspace)):
            raise ValueError(f"Path {path} is outside workspace")
        return full_path

    def check_write_permission(self, path: str, content: str) -> tuple[bool, str | None, Path]:
        """Check whether writing *path* is allowed under the current policy."""
        file_path = self._resolve_path(path)
        allowed, reason = self.permission_policy.check(
            "write_file",
            str(file_path),
            path=path,
            bytes=len(content.encode("utf-8")),
        )
        return allowed, reason, file_path

    def read_file(self, path: str) -> str:
        file_path = self._resolve_path(path)
        if not self.ops.exists(file_path):
            return f"Error: File {path} does not exist"
        return self.ops.read_text(file_path)

    def write_file(self, path: str, content: str) -> str:
        allowed, reason, file_path = self.check_write_permission(path, content)
        if not allowed:
            return reason or "Permission denied"
        self.ops.mkdir(file_path.parent)
        self.ops.write_text(file_path, content)
        return f"Successfully wrote to {path}"

    def list_files(self, directory: str = ".") -> str:
        dir_path = self._resolve_path(directory)
        if not self.ops.exists(dir_path):
            return f"Error: Directory {directory} does not exist"

        files = []
        for item in sorted(self.ops.iterdir(dir_path)):
            if self.ops.is_file(item):
                files.append(f"  📄 {item.name}")
            elif self.ops.is_dir(item):
                files.append(f"  📁 {item.name}/")

        return "\n".join(files) if files else "Empty directory"

    def file_exists(self, path: str) -> bool:
        return self.ops.exists(self._resolve_path(path))

    def grep_files(self, pattern: str, path: str = ".", recursive: bool = True) -> str:
        import re

        search_path = self._resolve_path(path)
        results = []

        try:
            if self.ops.is_file(search_path):
                content = self.ops.read_text(search_path)
                for i, line in enumerate(content.split("\n"), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        results.append(f"{search_path.name}:{i}: {line.strip()}")
            else:
                glob_pattern = "**/*" if recursive else "*"
                for file_path in self.ops.glob(search_path, glob_pattern):
                    if self.ops.is_file(file_path) and not file_path.name.startswith("."):
                        try:
                            content = self.ops.read_text(file_path)
                            for i, line in enumerate(content.split("\n"), 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    rel_path = file_path.relative_to(self.workspace)
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                        except (UnicodeDecodeError, PermissionError):
                            continue
        except Exception as e:
            return f"Error searching: {e}"

        if not results:
            return f"No matches found for '{pattern}'"
        if len(results) > 50:
            return "\n".join(results[:50]) + f"\n... ({len(results) - 50} more matches)"
        return "\n".join(results)

    def find_files(self, pattern: str, path: str = ".") -> str:
        search_path = self._resolve_path(path)

        if not self.ops.is_dir(search_path):
            return f"Error: {path} is not a directory"

        results = []
        try:
            for file_path in self.ops.rglob(search_path, pattern):
                rel_path = file_path.relative_to(self.workspace)
                file_type = "📁" if self.ops.is_dir(file_path) else "📄"
                size = self.ops.stat(file_path).st_size if self.ops.is_file(file_path) else 0
                results.append(f"{file_type} {rel_path} ({size} bytes)")
        except Exception as e:
            return f"Error finding files: {e}"

        if not results:
            return f"No files found matching '{pattern}'"
        return "\n".join(results)

    def ls_detailed(self, path: str = ".") -> str:
        import datetime

        dir_path = self._resolve_path(path)

        if not self.ops.exists(dir_path):
            return f"Error: {path} does not exist"
        if not self.ops.is_dir(dir_path):
            return f"Error: {path} is not a directory"

        results = []
        try:
            for item in sorted(self.ops.iterdir(dir_path)):
                stat = self.ops.stat(item)
                size = stat.st_size
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

                if self.ops.is_dir(item):
                    results.append(f"📁 {item.name:<30} {mtime_str}  <DIR>")
                else:
                    size_kb = size / 1024
                    results.append(f"📄 {item.name:<30} {mtime_str}  {size_kb:>8.1f} KB")
        except Exception as e:
            return f"Error listing directory: {e}"

        if not results:
            return "Empty directory"

        header = f"Directory: {path}\n" + "-" * 60 + "\n"
        return header + "\n".join(results)


class ShellTools:
    """Shell command execution tools backed by a pluggable ShellOperations backend."""

    def __init__(
        self,
        ops: ShellOperations | None = None,
        permission_policy: PermissionPolicy | None = None,
    ):
        """Initialize shell tools.

        Args:
            ops: Shell execution backend. Defaults to ``LocalShellOperations()``
                which runs real subprocesses. Pass a fake/stub for testing.
        """
        self.ops: ShellOperations = ops if ops is not None else LocalShellOperations()
        self.permission_policy = permission_policy or PermissionPolicy.deny_all()

    async def run_command(
        self,
        args: dict[str, Any],
        user_id: str,
        meta: dict[str, Any],
        cancel: Any,
    ) -> Any:
        """Execute a shell command (context-aware registry signature).

        Uses the 4-argument context-aware handler signature so the registry
        passes the ``meta`` dict, which may contain ``on_update`` — a callable
        injected by callers of ``registry.execute(on_update=cb)`` for real-time
        streaming of command output to the TUI.
        """
        from pig_agent_core.tools.base import ToolResult

        command: str = args.get("command", "")
        cwd: str | None = args.get("cwd")
        exclude_from_context: bool = bool(args.get("exclude_from_context", False))
        on_update: Callable[[str], None] | None = meta.get("on_update")

        if not command:
            return ToolResult(ok=False, error="command is required")

        allowed, reason = self.permission_policy.check(
            "run_command",
            command,
            cwd=cwd,
            exclude_from_context=exclude_from_context,
        )
        if not allowed:
            return ToolResult(ok=False, error=reason or "Permission denied")

        try:
            output = await self.ops.exec_async(command, cwd, timeout=30, on_data=on_update)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return ToolResult(ok=False, error=f"Error: {e}")

        if exclude_from_context:
            return ToolResult(ok=True, data="[Output excluded from model context]")
        return ToolResult(ok=True, data=_truncate_command_output(output))

    def _run_command_sync(
        self,
        command: str,
        cwd: str | None = None,
        exclude_from_context: bool = False,
    ) -> str:
        """Synchronous shell execution used by the git helpers (not cancellable)."""
        allowed, reason = self.permission_policy.check(
            "run_command",
            command,
            cwd=cwd,
            exclude_from_context=exclude_from_context,
        )
        if not allowed:
            return reason or "Permission denied"
        output = self.ops.exec_sync(command, cwd, timeout=30)
        if exclude_from_context:
            return "[Output excluded from model context]"
        return _truncate_command_output(output)


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict[str, Any]:
    """Build an OpenAI function-calling schema (matches the registry's expected shape)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


CODING_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn(
        "read_file",
        "Read contents of a file",
        {"path": {"type": "string", "description": "File path relative to workspace"}},
        ["path"],
    ),
    _fn(
        "write_file",
        "Write content to a file",
        {
            "path": {"type": "string", "description": "File path relative to workspace"},
            "content": {"type": "string", "description": "Content to write"},
        },
        ["path", "content"],
    ),
    _fn(
        "list_files",
        "List files in a directory",
        {"directory": {"type": "string", "description": "Directory path (default '.')"}},
        [],
    ),
    _fn(
        "file_exists",
        "Check if a file exists",
        {"path": {"type": "string", "description": "File path"}},
        ["path"],
    ),
    _fn(
        "grep_files",
        "Search for text in files (grep)",
        {
            "pattern": {"type": "string", "description": "Text pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in"},
            "recursive": {"type": "boolean", "description": "Search recursively (default true)"},
        },
        ["pattern"],
    ),
    _fn(
        "find_files",
        "Find files by name pattern",
        {
            "pattern": {"type": "string", "description": "File name pattern (supports wildcards)"},
            "path": {"type": "string", "description": "Directory to search in"},
        },
        ["pattern"],
    ),
    _fn(
        "ls_detailed",
        "List files with details (ls -la)",
        {"path": {"type": "string", "description": "Directory path (default '.')"}},
        [],
    ),
    _fn(
        "run_command",
        "Execute a shell command",
        {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
            "exclude_from_context": {
                "type": "boolean",
                "description": "Do not add output to model context",
            },
        },
        ["command"],
    ),
]


def build_coding_tools(
    workspace: str = ".",
    file_ops: FileOperations | None = None,
    shell_ops: ShellOperations | None = None,
    permission_policy: PermissionPolicy | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Callable]]:
    """Build the coding tools' schemas and name→handler map.

    Args:
        workspace: Workspace directory for the file tools.
        file_ops: Optional custom filesystem backend (testing / remote).
        shell_ops: Optional custom shell backend (testing / remote).

    Returns:
        A ``(CODING_TOOL_SCHEMAS, handlers)`` tuple.
    """
    file_tools = FileTools(workspace, ops=file_ops, permission_policy=permission_policy)
    shell_tools = ShellTools(ops=shell_ops, permission_policy=permission_policy)

    def _write_file_handler(path: str, content: str) -> Any:
        from pig_agent_core.tools.base import ToolResult

        allowed, reason, file_path = file_tools.check_write_permission(path, content)
        if not allowed:
            return ToolResult(ok=False, error=reason or "Permission denied")
        file_tools.ops.mkdir(file_path.parent)
        file_tools.ops.write_text(file_path, content)
        return f"Successfully wrote to {path}"

    handlers: dict[str, Callable] = {
        "read_file": file_tools.read_file,
        "write_file": _write_file_handler,
        "list_files": file_tools.list_files,
        "file_exists": file_tools.file_exists,
        "grep_files": file_tools.grep_files,
        "find_files": file_tools.find_files,
        "ls_detailed": file_tools.ls_detailed,
        "run_command": shell_tools.run_command,
    }
    return CODING_TOOL_SCHEMAS, handlers
