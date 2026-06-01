"""Regression tests for export/share behavior absorbed from pi-mono."""

from pathlib import Path
from unittest.mock import Mock, patch

from pig_agent_core.export import SessionExporter
from pig_agent_core.session import Session
from pig_agent_core.share import GistSharer


def test_export_html_escapes_session_metadata_and_preserves_tool_indentation(
    tmp_path: Path,
) -> None:
    session = Session(name='danger"><script>', workspace=str(tmp_path), auto_save=False)
    session.add_message("user", "<b>Hello</b>")
    session.add_message("tool", "line1\n  line2", name="read_file")

    export_path = tmp_path / "session.html"
    SessionExporter.export_to_html(session, export_path)

    html = export_path.read_text()
    assert "<script>" not in html
    assert "&lt;b&gt;Hello&lt;/b&gt;" in html
    assert "line1<br>\n  line2" in html


def test_share_session_uses_exported_safe_names(tmp_path: Path) -> None:
    session = Session(name="demo-session", workspace=str(tmp_path), auto_save=False)
    session.add_message("user", "hello")

    fake_response = Mock()
    fake_response.json.return_value = {
        "id": "gist123",
        "html_url": "https://gist.github.com/example/gist123",
        "created_at": "2026-06-02T00:00:00Z",
        "files": {"demo-session.html": {"raw_url": "https://gist.githubusercontent.com/raw"}},
    }
    fake_response.raise_for_status = Mock()

    fake_httpx = Mock()
    fake_httpx.post.return_value = fake_response
    sharer = GistSharer(github_token="token")
    with patch.dict("sys.modules", {"httpx": fake_httpx}):
        result = sharer.share_session(session, public=False)

    payload = fake_httpx.post.call_args.kwargs["json"]
    assert "demo-session.html" in payload["files"]
    assert "demo-session.md" in payload["files"]
    assert result["id"] == "gist123"


def test_share_session_raises_clear_error_without_httpx(tmp_path: Path) -> None:
    sharer = GistSharer(github_token="token")
    session = Session(name="demo", workspace=str(tmp_path), auto_save=False)

    with patch("builtins.__import__", side_effect=ModuleNotFoundError("httpx")):
        try:
            sharer.share_session(session)
        except ModuleNotFoundError as exc:
            assert "httpx is required for session sharing" in str(exc)
