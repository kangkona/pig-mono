"""Tests for session management."""

import pytest
from pathlib import Path
from py_agent_core.session import Session, SessionTree, SessionEntry


def test_session_tree_creation():
    """Test creating a session tree."""
    tree = SessionTree()
    assert len(tree.entries) == 0
    assert tree.current_id is None
    assert tree.root_id is None


def test_session_tree_add_entry():
    """Test adding entries to tree."""
    tree = SessionTree()
    
    entry1 = tree.add_entry("system", "You are helpful")
    assert entry1.role == "system"
    assert tree.root_id == entry1.id
    assert tree.current_id == entry1.id
    
    entry2 = tree.add_entry("user", "Hello")
    assert entry2.parent_id == entry1.id
    assert tree.current_id == entry2.id


def test_session_tree_get_path():
    """Test getting path to entry."""
    tree = SessionTree()
    
    e1 = tree.add_entry("system", "System")
    e2 = tree.add_entry("user", "User 1")
    e3 = tree.add_entry("assistant", "Response 1")
    
    path = tree.get_path_to_entry(e3.id)
    assert len(path) == 3
    assert path[0].id == e1.id
    assert path[1].id == e2.id
    assert path[2].id == e3.id


def test_session_tree_branching():
    """Test branching in tree."""
    tree = SessionTree()
    
    e1 = tree.add_entry("system", "System")
    e2 = tree.add_entry("user", "User 1")
    e3 = tree.add_entry("assistant", "Response 1")
    
    # Branch from e2
    tree.switch_to(e2.id)
    e4 = tree.add_entry("user", "User 2 (branched)")
    
    # e4 should have e2 as parent
    assert e4.parent_id == e2.id
    
    # Two children of e2
    children = tree.get_children(e2.id)
    assert len(children) == 2


def test_session_tree_jsonl():
    """Test JSONL export/import."""
    tree = SessionTree()
    
    tree.add_entry("system", "System")
    tree.add_entry("user", "User")
    tree.add_entry("assistant", "Assistant")
    
    # Export to JSONL
    jsonl = tree.to_jsonl()
    assert len(jsonl.split("\n")) == 3
    
    # Import from JSONL
    loaded = SessionTree.from_jsonl(jsonl)
    assert len(loaded.entries) == len(tree.entries)


def test_session_creation():
    """Test creating a session."""
    session = Session(name="test", workspace="/tmp")
    assert session.name == "test"
    assert len(session.tree.entries) == 0


def test_session_add_message():
    """Test adding messages to session."""
    session = Session(name="test", auto_save=False)
    
    entry = session.add_message("user", "Hello")
    assert entry.role == "user"
    assert len(session.tree.entries) == 1


def test_session_get_current_conversation():
    """Test getting current conversation."""
    session = Session(name="test", auto_save=False)
    
    session.add_message("system", "System")
    session.add_message("user", "User")
    session.add_message("assistant", "Assistant")
    
    conversation = session.get_current_conversation()
    assert len(conversation) == 3


def test_session_branch():
    """Test branching in session."""
    session = Session(name="test", auto_save=False)
    
    e1 = session.add_message("user", "Message 1")
    e2 = session.add_message("assistant", "Response 1")
    
    # Branch to e1
    session.branch_to(e1.id)
    e3 = session.add_message("user", "Message 2 (branched)")
    
    assert e3.parent_id == e1.id


def test_session_fork():
    """Test forking a session."""
    session = Session(name="original", auto_save=False)
    
    e1 = session.add_message("user", "Message 1")
    e2 = session.add_message("assistant", "Response 1")
    e3 = session.add_message("user", "Message 2")
    
    # Fork from e2
    fork = session.fork(e2.id, "forked")
    
    assert fork.name == "forked"
    assert len(fork.tree.entries) == 2  # Only up to e2


def test_session_compact():
    """Test session compaction."""
    session = Session(name="test", auto_save=False)
    
    # Add many messages
    for i in range(15):
        session.add_message("user", f"Message {i}")
        session.add_message("assistant", f"Response {i}")
    
    # Compact
    compacted = session.compact("Summarize")
    
    # Should have summary + recent messages
    assert len(compacted) < len(session.get_current_conversation())
    assert any("Compacted" in e.content for e in compacted)


def test_session_save_load(tmp_path):
    """Test saving and loading session."""
    session = Session(name="test", workspace=str(tmp_path), auto_save=False)
    
    session.add_message("user", "Message 1")
    session.add_message("assistant", "Response 1")
    
    # Save
    save_path = session.save()
    assert save_path.exists()
    
    # Load
    loaded = Session.load(save_path)
    assert loaded.name == "test"
    assert len(loaded.tree.entries) == 2


def test_session_get_info():
    """Test getting session info."""
    session = Session(name="test", auto_save=False)
    
    session.add_message("user", "Message")
    
    info = session.get_info()
    assert info["name"] == "test"
    assert info["entries"] == 1
    assert "created_at" in info
