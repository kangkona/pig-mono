"""Built-in tools for the coding agent.

Tools are authored in the new-registry style: plain handler methods plus
explicit OpenAI function-calling schemas, registered in bulk via
``ToolRegistry.register_package``. ``build_coding_tools`` is the single entry
point that binds handler state (workspace) and returns ``(schemas, handlers)``.
"""

import asyncio
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    """File operation tools."""

    def __init__(self, workspace: str = "."):
        """Initialize file tools.

        Args:
            workspace: Workspace directory
        """
        self.workspace = Path(workspace).resolve()

    def _resolve_path(self, path: str) -> Path:
        """Resolve path within workspace."""
        full_path = (self.workspace / path).resolve()
        if not str(full_path).startswith(str(self.workspace)):
            raise ValueError(f"Path {path} is outside workspace")
        return full_path

    def read_file(self, path: str) -> str:
        """Read file contents.

        Args:
            path: File path relative to workspace

        Returns:
            File contents
        """
        file_path = self._resolve_path(path)
        if not file_path.exists():
            return f"Error: File {path} does not exist"
        return file_path.read_text()

    def write_file(self, path: str, content: str) -> str:
        """Write content to file.

        Args:
            path: File path relative to workspace
            content: Content to write

        Returns:
            Success message
        """
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"Successfully wrote to {path}"

    def list_files(self, directory: str = ".") -> str:
        """List files in directory.

        Args:
            directory: Directory path

        Returns:
            List of files
        """
        dir_path = self._resolve_path(directory)
        if not dir_path.exists():
            return f"Error: Directory {directory} does not exist"

        files = []
        for item in sorted(dir_path.iterdir()):
            if item.is_file():
                files.append(f"  📄 {item.name}")
            elif item.is_dir():
                files.append(f"  📁 {item.name}/")

        return "\n".join(files) if files else "Empty directory"

    def file_exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: File path

        Returns:
            True if exists
        """
        return self._resolve_path(path).exists()

    def grep_files(self, pattern: str, path: str = ".", recursive: bool = True) -> str:
        """Search for pattern in files.

        Args:
            pattern: Text pattern to search for
            path: Directory or file to search in
            recursive: Search recursively

        Returns:
            Matching lines with file names
        """
        import re

        search_path = self._resolve_path(path)
        results = []

        try:
            if search_path.is_file():
                # Search single file
                content = search_path.read_text()
                for i, line in enumerate(content.split("\n"), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        results.append(f"{search_path.name}:{i}: {line.strip()}")
            else:
                # Search directory
                glob_pattern = "**/*" if recursive else "*"
                for file_path in search_path.glob(glob_pattern):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        try:
                            content = file_path.read_text()
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

        # Limit results
        if len(results) > 50:
            return "\n".join(results[:50]) + f"\n... ({len(results) - 50} more matches)"

        return "\n".join(results)

    def find_files(self, pattern: str, path: str = ".") -> str:
        """Find files matching pattern.

        Args:
            pattern: File name pattern (supports wildcards)
            path: Directory to search in

        Returns:
            List of matching files
        """
        search_path = self._resolve_path(path)

        if not search_path.is_dir():
            return f"Error: {path} is not a directory"

        results = []
        try:
            for file_path in search_path.rglob(pattern):
                rel_path = file_path.relative_to(self.workspace)
                file_type = "📁" if file_path.is_dir() else "📄"
                size = file_path.stat().st_size if file_path.is_file() else 0
                results.append(f"{file_type} {rel_path} ({size} bytes)")
        except Exception as e:
            return f"Error finding files: {e}"

        if not results:
            return f"No files found matching '{pattern}'"

        return "\n".join(results)

    def ls_detailed(self, path: str = ".") -> str:
        """List files with detailed information.

        Args:
            path: Directory path

        Returns:
            Detailed file listing
        """
        import datetime

        dir_path = self._resolve_path(path)

        if not dir_path.exists():
            return f"Error: {path} does not exist"

        if not dir_path.is_dir():
            return f"Error: {path} is not a directory"

        results = []
        try:
            for item in sorted(dir_path.iterdir()):
                stat = item.stat()
                size = stat.st_size
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

                if item.is_dir():
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
    """Shell command execution tools."""

    async def run_command(
        self,
        command: str,
        cwd: str | None = None,
        exclude_from_context: bool = False,
    ) -> str:
        """Execute a shell command, killable when the turn is aborted.

        Runs the command as an async subprocess so that when the surrounding
        agent turn is cancelled (e.g. the user pressed Esc), the in-flight
        process is killed instead of lingering.

        Args:
            command: Command to execute
            cwd: Working directory
            exclude_from_context: Hint that callers should not add output to model context

        Returns:
            Command output
        """
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: Command timed out"
            output = stdout.decode(errors="replace")
            stderr_text = stderr.decode(errors="replace")
            if stderr_text:
                output += f"\nErrors:\n{stderr_text}"
            if exclude_from_context:
                return "[Output excluded from model context]"
            return _truncate_command_output(output)
        except asyncio.CancelledError:
            # Turn aborted mid-command: kill the subprocess and propagate.
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        except Exception as e:
            return f"Error: {e}"

    def _run_command_sync(
        self,
        command: str,
        cwd: str | None = None,
        exclude_from_context: bool = False,
    ) -> str:
        """Synchronous shell execution used by the git helpers (not cancellable)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nErrors:\n{result.stderr}"
            if exclude_from_context:
                return "[Output excluded from model context]"
            return _truncate_command_output(output)
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"

    def git_status(self) -> str:
        """Get git repository status.

        Returns:
            Git status output
        """
        return self._run_command_sync("git status --short")

    def git_diff(self, path: str | None = None) -> str:
        """Get git diff.

        Args:
            path: Optional path to diff

        Returns:
            Git diff output
        """
        cmd = f"git diff {path}" if path else "git diff"
        return self._run_command_sync(cmd)

    def git_commit(self, message: str, add_all: bool = False) -> str:
        """Commit changes to git.

        Args:
            message: Commit message
            add_all: Add all changes first

        Returns:
            Commit output
        """
        if add_all:
            self._run_command_sync("git add -A")

        # Escape message for shell
        import shlex

        safe_message = shlex.quote(message)
        return self._run_command_sync(f"git commit -m {safe_message}")

    def git_push(self, remote: str = "origin", branch: str | None = None) -> str:
        """Push changes to remote.

        Args:
            remote: Remote name
            branch: Branch name (current if None)

        Returns:
            Push output
        """
        if branch:
            return self._run_command_sync(f"git push {remote} {branch}")
        else:
            return self._run_command_sync(f"git push {remote}")

    def git_branch(self, branch_name: str, checkout: bool = True) -> str:
        """Create a new git branch.

        Args:
            branch_name: Branch name
            checkout: Checkout after creating

        Returns:
            Command output
        """
        if checkout:
            return self._run_command_sync(f"git checkout -b {branch_name}")
        else:
            return self._run_command_sync(f"git branch {branch_name}")

    def git_log(self, limit: int = 10) -> str:
        """Get recent git commits.

        Args:
            limit: Number of commits

        Returns:
            Git log output
        """
        return self._run_command_sync(f"git log --oneline -n {limit}")


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


# Explicit schemas for the coding tools (replaces the old @tool Pydantic auto-gen).
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
    _fn("git_status", "Get git status", {}, []),
    _fn(
        "git_diff",
        "Get git diff",
        {"path": {"type": "string", "description": "Optional path to diff"}},
        [],
    ),
    _fn(
        "git_commit",
        "Commit changes to git",
        {
            "message": {"type": "string", "description": "Commit message"},
            "add_all": {"type": "boolean", "description": "Add all changes first"},
        },
        ["message"],
    ),
    _fn(
        "git_push",
        "Push changes to a remote",
        {
            "remote": {"type": "string", "description": "Remote name (default 'origin')"},
            "branch": {"type": "string", "description": "Branch name (current if omitted)"},
        },
        [],
    ),
    _fn(
        "git_branch",
        "Create a git branch",
        {
            "branch_name": {"type": "string", "description": "Branch name"},
            "checkout": {
                "type": "boolean",
                "description": "Checkout after creating (default true)",
            },
        },
        ["branch_name"],
    ),
    _fn(
        "git_log",
        "Get recent git commits",
        {"limit": {"type": "integer", "description": "Number of commits (default 10)"}},
        [],
    ),
]


def build_coding_tools(workspace: str = ".") -> tuple[list[dict[str, Any]], dict[str, Callable]]:
    """Build the coding tools' schemas and name→handler map.

    Instantiates the stateful tool classes (FileTools needs the workspace) and
    returns ``(schemas, handlers)`` ready for ``ToolRegistry.register_package``.

    Args:
        workspace: Workspace directory for the file tools.

    Returns:
        A ``(CODING_TOOL_SCHEMAS, handlers)`` tuple.
    """
    file_tools = FileTools(workspace)
    shell_tools = ShellTools()

    handlers: dict[str, Callable] = {
        "read_file": file_tools.read_file,
        "write_file": file_tools.write_file,
        "list_files": file_tools.list_files,
        "file_exists": file_tools.file_exists,
        "grep_files": file_tools.grep_files,
        "find_files": file_tools.find_files,
        "ls_detailed": file_tools.ls_detailed,
        "run_command": shell_tools.run_command,
        "git_status": shell_tools.git_status,
        "git_diff": shell_tools.git_diff,
        "git_commit": shell_tools.git_commit,
        "git_push": shell_tools.git_push,
        "git_branch": shell_tools.git_branch,
        "git_log": shell_tools.git_log,
    }
    return CODING_TOOL_SCHEMAS, handlers
