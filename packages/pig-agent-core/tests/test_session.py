"""Tests for session management."""

from pig_agent_core.session import Session, SessionTree


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

    tree.add_entry("system", "System")
    e2 = tree.add_entry("user", "User 1")
    tree.add_entry("assistant", "Response 1")

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
    session.add_message("assistant", "Response 1")

    # Branch to e1
    session.branch_to(e1.id)
    e3 = session.add_message("user", "Message 2 (branched)")

    assert e3.parent_id == e1.id


def test_session_fork():
    """Test forking a session."""
    session = Session(name="original", auto_save=False)

    session.add_message("user", "Message 1")
    e2 = session.add_message("assistant", "Response 1")
    session.add_message("user", "Message 2")

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

    # Current conversation should now be the compacted summary + recent tail
    assert compacted == session.get_current_conversation()
    assert len(compacted) < 30
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


def test_session_save_uses_session_id_in_filename_when_name_reused(tmp_path):
    session1 = Session(name="shared-name", workspace=str(tmp_path), auto_save=False)
    session2 = Session(name="shared-name", workspace=str(tmp_path), auto_save=False)

    path1 = session1.save()
    path2 = session2.save()

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_session_save_uses_env_session_dir(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(session_dir))

    session = Session(name="test", workspace=str(workspace), auto_save=False)
    path = session.save()

    assert path.parent == session_dir
    assert path.exists()


def test_session_load_preserves_workspace_from_header_with_env_session_dir(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_dir = tmp_path / "custom-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(session_dir))

    session = Session(name="test", workspace=str(workspace), auto_save=False)
    session.add_message("user", "hello")
    path = session.save()

    loaded = Session.load(path)

    assert loaded.workspace == workspace


def test_session_save_uses_explicit_session_dir_over_env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env_session_dir = tmp_path / "env-sessions"
    explicit_session_dir = tmp_path / "explicit-sessions"
    monkeypatch.setenv("PIG_CODING_AGENT_SESSION_DIR", str(env_session_dir))

    session = Session(
        name="test",
        workspace=str(workspace),
        auto_save=False,
        session_dir=str(explicit_session_dir),
    )
    path = session.save()

    assert path.parent == explicit_session_dir


def test_session_save_uses_full_explicit_session_id_in_filename(tmp_path):
    session = Session(name="shared-name", workspace=str(tmp_path), auto_save=False)
    session.id = "manual-session-id"

    path = session.save()

    assert path.name == "shared-name-manual-session-id.jsonl"


def test_session_save_preserves_loaded_legacy_path(tmp_path):
    legacy_path = tmp_path / ".sessions" / "legacy-name.jsonl"
    legacy_path.parent.mkdir()

    session = Session(name="legacy-name", workspace=str(tmp_path), auto_save=False)
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    generated = session.save()
    legacy_path.write_text(generated.read_text())
    generated.unlink()

    loaded = Session.load(legacy_path)
    loaded.add_message("user", "again")
    saved = loaded.save()

    assert saved == legacy_path
    assert legacy_path.exists()


def test_reload_after_compaction_restores_exact_tip(tmp_path):
    """A compacted session must reload to its real tip, not a stale branch leaf.

    Reload previously inferred current_id from the max-timestamp leaf, which
    resurrected an abandoned off-path branch whenever that branch had a newer
    timestamp than the active conversation. The persisted current_id/root_id
    must pin the exact tip instead.
    """
    session = Session(name="compact", workspace=str(tmp_path), auto_save=False)
    ids = [session.add_message("user", f"m{i}").id for i in range(12)]
    real_tip = session.tree.current_id

    # Abandoned branch off an early node, with a newer-than-everything timestamp.
    branch = session.tree.add_entry("assistant", "BRANCH-CHILD", parent_id=ids[1])
    session.tree.entries[branch.id].timestamp = "9999-12-31T23:59:59"
    session.tree.current_id = real_tip

    session.compact()
    after_compact = [e.content for e in session.get_current_conversation()]
    path = session.save()

    reloaded = Session.load(path)
    after_reload = [e.content for e in reloaded.get_current_conversation()]

    assert "BRANCH-CHILD" not in after_reload
    assert after_reload == after_compact
    assert reloaded.tree.current_id == session.tree.current_id
