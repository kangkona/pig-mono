"""Pluggable I/O backend protocols for the coding-agent tools.

Separating tool logic from its I/O operations makes tools testable without a
real filesystem or subprocess, and redirectable to remote / sandbox backends
(analogous to the ``*Operations`` interfaces in pi-mono's coding tools).

Usage::

    # default: real local I/O
    file_tools = FileTools(workspace)

    # test: fully controlled fake
    file_tools = FileTools(workspace, ops=FakeFileOperations())
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# FileOperations
# ---------------------------------------------------------------------------


@runtime_checkable
class FileOperations(Protocol):
    """Filesystem operations required by FileTools.

    Any object implementing all methods is a valid FileOperations backend —
    no inheritance required.
    """

    def exists(self, path: Path) -> bool: ...
    def is_file(self, path: Path) -> bool: ...
    def is_dir(self, path: Path) -> bool: ...
    def read_text(self, path: Path) -> str: ...
    def write_text(self, path: Path, content: str) -> None: ...
    def mkdir(self, path: Path, *, parents: bool = True, exist_ok: bool = True) -> None: ...
    def iterdir(self, path: Path) -> list[Path]: ...
    def glob(self, path: Path, pattern: str) -> list[Path]: ...
    def rglob(self, path: Path, pattern: str) -> list[Path]: ...
    def stat(self, path: Path) -> os.stat_result: ...


class LocalFileOperations:
    """Default FileOperations backed by the real local filesystem."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def read_text(self, path: Path) -> str:
        return path.read_text()

    def write_text(self, path: Path, content: str) -> None:
        path.write_text(content)

    def mkdir(self, path: Path, *, parents: bool = True, exist_ok: bool = True) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def iterdir(self, path: Path) -> list[Path]:
        return list(path.iterdir())

    def glob(self, path: Path, pattern: str) -> list[Path]:
        return list(path.glob(pattern))

    def rglob(self, path: Path, pattern: str) -> list[Path]:
        return list(path.rglob(pattern))

    def stat(self, path: Path) -> os.stat_result:
        return path.stat()


# ---------------------------------------------------------------------------
# ShellOperations
# ---------------------------------------------------------------------------


@runtime_checkable
class ShellOperations(Protocol):
    """Shell execution operations required by ShellTools."""

    async def exec_async(
        self,
        command: str,
        cwd: str | None,
        timeout: float,
        on_data: Callable[[str], None] | None = None,
    ) -> str:
        """Execute *command* asynchronously and return combined stdout+stderr.

        If *on_data* is provided it is called with each chunk of decoded output
        as it arrives, enabling real-time streaming to a UI layer. The full
        (pre-truncation) output is still returned for inclusion in context.
        """
        ...

    def exec_sync(self, command: str, cwd: str | None, timeout: float) -> str:
        """Execute *command* synchronously and return combined stdout+stderr."""
        ...


class LocalShellOperations:
    """Default ShellOperations backed by asyncio subprocess and subprocess.run."""

    async def exec_async(
        self,
        command: str,
        cwd: str | None,
        timeout: float,
        on_data: Callable[[str], None] | None = None,
    ) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if on_data is None:
            # Fast path: no streaming needed — wait for both streams at once.
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: Command timed out"
            output = stdout_bytes.decode(errors="replace")
            if stderr_bytes:
                output += f"\nErrors:\n{stderr_bytes.decode(errors='replace')}"
            return output

        # Streaming path: read stdout line-by-line, call on_data per chunk.
        # stderr is still collected separately (piped) to avoid interleaving.
        stdout_chunks: list[str] = []

        async def _drain_stdout() -> None:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                chunk = line.decode(errors="replace")
                stdout_chunks.append(chunk)
                on_data(chunk)

        async def _drain_stderr() -> bytes:
            assert proc.stderr is not None
            return await proc.stderr.read()

        try:
            stdout_task = asyncio.create_task(_drain_stdout())
            stderr_task = asyncio.create_task(_drain_stderr())
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=timeout,
            )
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: Command timed out"

        output = "".join(stdout_chunks)
        stderr_bytes = stderr_task.result() if stderr_task.done() else b""
        if stderr_bytes:
            output += f"\nErrors:\n{stderr_bytes.decode(errors='replace')}"
        return output

    def exec_sync(self, command: str, cwd: str | None, timeout: float) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nErrors:\n{result.stderr}"
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {e}"
