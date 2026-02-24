"""Share sessions via GitHub Gist."""

import json
from pathlib import Path
from typing import Optional
import httpx

from .session import Session
from .export import SessionExporter


class GistSharer:
    """Share sessions via GitHub Gist."""

    GIST_API = "https://api.github.com/gists"

    def __init__(self, github_token: Optional[str] = None):
        """Initialize gist sharer.

        Args:
            github_token: GitHub personal access token
                         (get from https://github.com/settings/tokens)
        """
        self.github_token = github_token

    def share_session(
        self,
        session: Session,
        public: bool = False,
        description: Optional[str] = None,
    ) -> dict:
        """Share session as GitHub Gist.

        Args:
            session: Session to share
            public: Make gist public (default: private)
            description: Gist description

        Returns:
            Gist info with URL

        Raises:
            ValueError: If no GitHub token provided
            httpx.HTTPError: If GitHub API fails
        """
        if not self.github_token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass to constructor.\n"
                "Get token from: https://github.com/settings/tokens"
            )

        # Export session to HTML (in-memory)
        html_path = Path(f"/tmp/{session.name}.html")
        SessionExporter.export_to_html(session, html_path, title=session.name)
        html_content = html_path.read_text()
        html_path.unlink()  # Clean up

        # Also export as markdown
        md_path = Path(f"/tmp/{session.name}.md")
        SessionExporter.export_to_markdown(session, md_path)
        md_content = md_path.read_text()
        md_path.unlink()  # Clean up

        # Create gist payload
        files = {
            f"{session.name}.html": {"content": html_content},
            f"{session.name}.md": {"content": md_content},
        }

        payload = {
            "description": description or f"pig-mono session: {session.name}",
            "public": public,
            "files": files,
        }

        # Create gist
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        response = httpx.post(
            self.GIST_API, json=payload, headers=headers, timeout=30
        )

        response.raise_for_status()

        gist_data = response.json()

        return {
            "id": gist_data["id"],
            "url": gist_data["html_url"],
            "raw_url": gist_data["files"][f"{session.name}.html"]["raw_url"],
            "public": public,
            "created_at": gist_data["created_at"],
        }

    def get_shareable_link(self, gist_url: str) -> str:
        """Get shareable HTML preview link.

        Args:
            gist_url: GitHub gist URL

        Returns:
            HTML preview URL
        """
        # GitHub gist HTML files can be previewed via htmlpreview.github.io
        gist_id = gist_url.split("/")[-1]

        # Extract username and gist_id
        # URL format: https://gist.github.com/username/gist_id

        # For now, return the gist URL
        # In production, could use a preview service
        return gist_url
