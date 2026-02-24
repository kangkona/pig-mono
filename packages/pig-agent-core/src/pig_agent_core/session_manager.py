"""Session manager for listing and selecting sessions."""

from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .session import Session


class SessionInfo:
    """Information about a session file."""

    def __init__(self, path: Path):
        """Initialize session info.

        Args:
            path: Path to session file
        """
        self.path = path
        self.name = path.stem
        self.modified = datetime.fromtimestamp(path.stat().st_mtime)
        self.size = path.stat().st_size

        # Try to load header for more info
        try:
            import json
            with open(path) as f:
                header = json.loads(f.readline())
                self.session_name = header.get("name", self.name)
                self.created = datetime.fromisoformat(header["created_at"])
                self.entries = header.get("metadata", {}).get("entries", 0)
        except Exception:
            self.session_name = self.name
            self.created = self.modified
            self.entries = 0

    def __repr__(self) -> str:
        return f"SessionInfo(name={self.name}, modified={self.modified})"


class SessionManager:
    """Manages multiple sessions."""

    def __init__(self, workspace: Optional[Path] = None):
        """Initialize session manager.

        Args:
            workspace: Workspace directory
        """
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.sessions_dir = self.workspace / ".sessions"

    def list_sessions(self, limit: Optional[int] = None) -> List[SessionInfo]:
        """List available sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session info, sorted by modified time (newest first)
        """
        if not self.sessions_dir.exists():
            return []

        sessions = []
        for session_file in self.sessions_dir.glob("*.jsonl"):
            try:
                info = SessionInfo(session_file)
                sessions.append(info)
            except Exception as e:
                print(f"Warning: Failed to load session info from {session_file}: {e}")

        # Sort by modified time (newest first)
        sessions.sort(key=lambda s: s.modified, reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_most_recent(self) -> Optional[SessionInfo]:
        """Get the most recently modified session.

        Returns:
            Most recent session info or None
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def find_session(self, name_or_id: str) -> Optional[Path]:
        """Find a session by name or partial ID.

        Args:
            name_or_id: Session name or partial UUID

        Returns:
            Path to session file if found
        """
        sessions = self.list_sessions()

        for info in sessions:
            # Match by name
            if info.session_name == name_or_id or info.name == name_or_id:
                return info.path

            # Match by partial ID (from header)
            try:
                import json
                with open(info.path) as f:
                    header = json.loads(f.readline())
                    session_id = header.get("id", "")
                    if session_id.startswith(name_or_id):
                        return info.path
            except Exception:
                continue

        return None

    def delete_session(self, path: Path) -> bool:
        """Delete a session file.

        Args:
            path: Path to session file

        Returns:
            True if deleted successfully
        """
        try:
            path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    def cleanup_old_sessions(self, keep_days: int = 30) -> int:
        """Delete sessions older than specified days.

        Args:
            keep_days: Number of days to keep

        Returns:
            Number of sessions deleted
        """
        if not self.sessions_dir.exists():
            return 0

        cutoff = datetime.now().timestamp() - (keep_days * 24 * 3600)
        deleted = 0

        for session_file in self.sessions_dir.glob("*.jsonl"):
            if session_file.stat().st_mtime < cutoff:
                if self.delete_session(session_file):
                    deleted += 1

        return deleted

    def format_session_list(self, sessions: List[SessionInfo]) -> str:
        """Format session list for display.

        Args:
            sessions: List of session info

        Returns:
            Formatted string
        """
        if not sessions:
            return "No sessions found"

        lines = []
        for i, info in enumerate(sessions, 1):
            age = self._format_age(info.modified)
            lines.append(
                f"{i}. {info.session_name:<30} {age:<15} ({info.entries} entries)"
            )

        return "\n".join(lines)

    def _format_age(self, dt: datetime) -> str:
        """Format time difference as human-readable string.

        Args:
            dt: Datetime to format

        Returns:
            Human-readable age (e.g., "2 hours ago")
        """
        now = datetime.now()
        diff = now - dt

        if diff.days > 1:
            return f"{diff.days} days ago"
        elif diff.days == 1:
            return "yesterday"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} min ago"
        else:
            return "just now"
