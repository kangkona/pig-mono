"""Tests for session manager."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from pig_agent_core import Session, SessionManager, SessionInfo


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with sessions."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    sessions_dir = workspace / ".sessions"
    sessions_dir.mkdir()
    
    return workspace


def test_session_info_creation(temp_workspace):
    """Test creating session info."""
    # Create a session file
    session = Session(name="test", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "Hello")
    path = session.save()
    
    info = SessionInfo(path)
    assert info.name == "test"
    assert info.path == path


def test_session_manager_creation(temp_workspace):
    """Test creating session manager."""
    mgr = SessionManager(temp_workspace)
    assert mgr.workspace == temp_workspace
    assert mgr.sessions_dir == temp_workspace / ".sessions"


def test_session_manager_list_empty(temp_workspace):
    """Test listing with no sessions."""
    mgr = SessionManager(temp_workspace)
    sessions = mgr.list_sessions()
    assert len(sessions) == 0


def test_session_manager_list_sessions(temp_workspace):
    """Test listing sessions."""
    # Create some sessions
    for i in range(3):
        session = Session(name=f"session-{i}", workspace=str(temp_workspace), auto_save=False)
        session.add_message("user", f"Message {i}")
        session.save()
    
    mgr = SessionManager(temp_workspace)
    sessions = mgr.list_sessions()
    
    assert len(sessions) == 3


def test_session_manager_list_sorted(temp_workspace):
    """Test sessions are sorted by modified time."""
    import time
    
    # Create sessions with delays
    session1 = Session(name="old", workspace=str(temp_workspace), auto_save=False)
    session1.save()
    
    time.sleep(0.1)
    
    session2 = Session(name="new", workspace=str(temp_workspace), auto_save=False)
    session2.save()
    
    mgr = SessionManager(temp_workspace)
    sessions = mgr.list_sessions()
    
    # Newest first
    assert sessions[0].name == "new"
    assert sessions[1].name == "old"


def test_session_manager_list_limit(temp_workspace):
    """Test limiting session list."""
    # Create many sessions
    for i in range(10):
        session = Session(name=f"s{i}", workspace=str(temp_workspace), auto_save=False)
        session.save()
    
    mgr = SessionManager(temp_workspace)
    sessions = mgr.list_sessions(limit=5)
    
    assert len(sessions) == 5


def test_session_manager_get_most_recent(temp_workspace):
    """Test getting most recent session."""
    import time
    
    session1 = Session(name="first", workspace=str(temp_workspace), auto_save=False)
    session1.save()
    
    time.sleep(0.1)
    
    session2 = Session(name="second", workspace=str(temp_workspace), auto_save=False)
    session2.save()
    
    mgr = SessionManager(temp_workspace)
    recent = mgr.get_most_recent()
    
    assert recent is not None
    assert recent.name == "second"


def test_session_manager_find_by_name(temp_workspace):
    """Test finding session by name."""
    session = Session(name="findme", workspace=str(temp_workspace), auto_save=False)
    path = session.save()
    
    mgr = SessionManager(temp_workspace)
    found = mgr.find_session("findme")
    
    assert found == path


def test_session_manager_find_missing(temp_workspace):
    """Test finding non-existent session."""
    mgr = SessionManager(temp_workspace)
    found = mgr.find_session("missing")
    
    assert found is None


def test_session_manager_delete(temp_workspace):
    """Test deleting a session."""
    session = Session(name="delete-me", workspace=str(temp_workspace), auto_save=False)
    path = session.save()
    
    assert path.exists()
    
    mgr = SessionManager(temp_workspace)
    success = mgr.delete_session(path)
    
    assert success
    assert not path.exists()


def test_session_manager_format_list(temp_workspace):
    """Test formatting session list."""
    session = Session(name="test", workspace=str(temp_workspace), auto_save=False)
    session.add_message("user", "Hello")
    session.save()
    
    mgr = SessionManager(temp_workspace)
    sessions = mgr.list_sessions()
    
    formatted = mgr.format_session_list(sessions)
    
    assert "test" in formatted
    assert "ago" in formatted or "just now" in formatted


def test_session_manager_format_empty():
    """Test formatting empty list."""
    mgr = SessionManager()
    formatted = mgr.format_session_list([])
    
    assert "No sessions" in formatted


def test_session_manager_cleanup_old(temp_workspace):
    """Test cleaning up old sessions."""
    # Create old session (mock by setting mtime)
    session = Session(name="old", workspace=str(temp_workspace), auto_save=False)
    path = session.save()
    
    # Set modified time to 40 days ago
    old_time = (datetime.now() - timedelta(days=40)).timestamp()
    path.touch()
    import os
    os.utime(path, (old_time, old_time))
    
    mgr = SessionManager(temp_workspace)
    deleted = mgr.cleanup_old_sessions(keep_days=30)
    
    assert deleted == 1
    assert not path.exists()
