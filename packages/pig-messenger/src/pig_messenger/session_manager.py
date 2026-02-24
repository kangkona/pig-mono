"""Multi-platform session management."""

from pathlib import Path
from typing import Dict, Optional

from pig_agent_core import Session


class MultiPlatformSessionManager:
    """Manage sessions across multiple platforms and channels."""

    def __init__(self, workspace: Path):
        """Initialize session manager.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.sessions: Dict[str, Session] = {}
        self.sessions_dir = workspace / "sessions"
        self.sessions_dir.mkdir(exist_ok=True)

    def get_session_key(self, platform: str, channel_id: str) -> str:
        """Generate session key.

        Args:
            platform: Platform name
            channel_id: Channel ID

        Returns:
            Session key
        """
        return f"{platform}:{channel_id}"

    def get_session(
        self, platform: str, channel_id: str, auto_create: bool = True
    ) -> Optional[Session]:
        """Get or create session for a platform+channel.

        Args:
            platform: Platform name
            channel_id: Channel ID
            auto_create: Create if doesn't exist

        Returns:
            Session instance or None
        """
        key = self.get_session_key(platform, channel_id)

        # Return cached session
        if key in self.sessions:
            return self.sessions[key]

        # Try to load from disk
        session_file = self.sessions_dir / f"{key.replace(':', '_')}.jsonl"

        if session_file.exists():
            try:
                session = Session.load(session_file)
                self.sessions[key] = session
                return session
            except Exception as e:
                print(f"Warning: Failed to load session {key}: {e}")

        # Create new session
        if auto_create:
            session = Session(
                name=f"{platform}_{channel_id}",
                workspace=str(self.workspace),
                auto_save=True,
            )

            # Set custom save path
            session._save_path = session_file

            self.sessions[key] = session
            return session

        return None

    def list_sessions(self) -> Dict[str, Session]:
        """List all active sessions.

        Returns:
            Dictionary of session key -> session
        """
        return self.sessions.copy()

    def save_all(self) -> None:
        """Save all sessions."""
        for key, session in self.sessions.items():
            try:
                session.save()
            except Exception as e:
                print(f"Error saving session {key}: {e}")

    def clear_session(self, platform: str, channel_id: str) -> bool:
        """Clear a session.

        Args:
            platform: Platform name
            channel_id: Channel ID

        Returns:
            True if cleared
        """
        key = self.get_session_key(platform, channel_id)

        if key in self.sessions:
            del self.sessions[key]

            # Delete file
            session_file = self.sessions_dir / f"{key.replace(':', '_')}.jsonl"
            if session_file.exists():
                session_file.unlink()

            return True

        return False
