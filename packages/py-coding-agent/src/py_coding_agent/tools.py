"""Built-in tools for coding agent."""

import os
import subprocess
from pathlib import Path
from typing import Optional

from py_agent_core import tool


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

    @tool(description="Read contents of a file")
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

    @tool(description="Write content to a file")
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

    @tool(description="List files in a directory")
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

    @tool(description="Check if file exists")
    def file_exists(self, path: str) -> bool:
        """Check if file exists.

        Args:
            path: File path

        Returns:
            True if exists
        """
        return self._resolve_path(path).exists()

    @tool(description="Search for text in files (grep)")
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

    @tool(description="Find files by name pattern")
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

    @tool(description="List files with details (ls -la)")
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
                    results.append(
                        f"📄 {item.name:<30} {mtime_str}  {size_kb:>8.1f} KB"
                    )
        except Exception as e:
            return f"Error listing directory: {e}"

        if not results:
            return "Empty directory"

        header = f"Directory: {path}\n" + "-" * 60 + "\n"
        return header + "\n".join(results)


class CodeTools:
    """Code generation and analysis tools."""

    @tool(description="Generate code from description")
    def generate_code(self, description: str, language: str = "python") -> str:
        """Generate code from natural language description.

        Args:
            description: What the code should do
            language: Programming language

        Returns:
            Generated code
        """
        # This is a placeholder - actual implementation would use LLM
        return f"# Generated {language} code for: {description}\n# TODO: Implement"

    @tool(description="Explain what code does")
    def explain_code(self, code: str) -> str:
        """Explain what code does.

        Args:
            code: Code to explain

        Returns:
            Explanation
        """
        # Placeholder
        return f"This code appears to be {len(code.split())} lines long."

    @tool(description="Add type hints to Python code")
    def add_type_hints(self, code: str) -> str:
        """Add type hints to Python code.

        Args:
            code: Python code

        Returns:
            Code with type hints
        """
        # Placeholder
        return f"# Type hints added:\n{code}"


class ShellTools:
    """Shell command execution tools."""

    @tool(description="Execute a shell command")
    def run_command(self, command: str, cwd: Optional[str] = None) -> str:
        """Execute shell command safely.

        Args:
            command: Command to execute
            cwd: Working directory

        Returns:
            Command output
        """
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
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"

    @tool(description="Get git status")
    def git_status(self) -> str:
        """Get git repository status.

        Returns:
            Git status output
        """
        return self.run_command("git status --short")

    @tool(description="Get git diff")
    def git_diff(self, path: Optional[str] = None) -> str:
        """Get git diff.

        Args:
            path: Optional path to diff

        Returns:
            Git diff output
        """
        cmd = f"git diff {path}" if path else "git diff"
        return self.run_command(cmd)

    @tool(description="Git commit changes")
    def git_commit(self, message: str, add_all: bool = False) -> str:
        """Commit changes to git.

        Args:
            message: Commit message
            add_all: Add all changes first

        Returns:
            Commit output
        """
        if add_all:
            self.run_command("git add -A")

        # Escape message for shell
        import shlex

        safe_message = shlex.quote(message)
        return self.run_command(f"git commit -m {safe_message}")

    @tool(description="Git push changes")
    def git_push(self, remote: str = "origin", branch: Optional[str] = None) -> str:
        """Push changes to remote.

        Args:
            remote: Remote name
            branch: Branch name (current if None)

        Returns:
            Push output
        """
        if branch:
            return self.run_command(f"git push {remote} {branch}")
        else:
            return self.run_command(f"git push {remote}")

    @tool(description="Create git branch")
    def git_branch(self, branch_name: str, checkout: bool = True) -> str:
        """Create a new git branch.

        Args:
            branch_name: Branch name
            checkout: Checkout after creating

        Returns:
            Command output
        """
        if checkout:
            return self.run_command(f"git checkout -b {branch_name}")
        else:
            return self.run_command(f"git branch {branch_name}")

    @tool(description="Get git log")
    def git_log(self, limit: int = 10) -> str:
        """Get recent git commits.

        Args:
            limit: Number of commits

        Returns:
            Git log output
        """
        return self.run_command(f"git log --oneline -n {limit}")
