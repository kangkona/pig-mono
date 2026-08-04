"""Active-turn transitions cancel first and never mutate live session state."""

import asyncio
import threading
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from pig_agent_core import Session
from pig_coding_agent.agent import CodingAgent
from pig_coding_agent.turn_lifecycle import ActiveTurnLifecycle, ActiveTurnTransitionError
from pig_llm import Response, TurnOutcome


@pytest.mark.asyncio
async def test_active_turn_lifecycle_requests_cancel_and_waits_for_flush() -> None:
    lifecycle = ActiveTurnLifecycle()
    started = asyncio.Event()
    flushed = asyncio.Event()
    release = asyncio.Event()

    async def turn() -> None:
        cancel = asyncio.Event()
        token = lifecycle.begin(cancel)
        try:
            started.set()
            await cancel.wait()
            await release.wait()
            flushed.set()
        finally:
            lifecycle.end(token)

    task = asyncio.create_task(turn())
    await started.wait()

    wait_task = asyncio.create_task(lifecycle.cancel_and_wait())
    await asyncio.sleep(0)
    assert lifecycle.is_active is True
    assert flushed.is_set() is False

    release.set()
    await wait_task
    await task
    assert flushed.is_set() is True
    assert lifecycle.is_active is False


def test_tree_switch_is_fail_closed_while_turn_is_active(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model")
    agent = CodingAgent(
        llm=llm,
        workspace=str(tmp_path),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )
    root = agent.session.add_message("user", "root")
    tip = agent.session.add_message("assistant", "tip")
    cancel = asyncio.Event()

    async def exercise() -> None:
        token = agent.turn_lifecycle.begin(cancel)
        try:
            result = agent.app_actions.switch_tree(root.id)
            assert result.ok is False
            assert "active turn" in (result.error or "").lower()
            assert cancel.is_set() is True
            assert agent.session.tree.current_id == tip.id
        finally:
            agent.turn_lifecycle.end(token)

    asyncio.run(exercise())
    assert agent.app_actions.switch_tree(root.id).ok is True
    assert agent.session.tree.current_id == root.id


def test_session_switch_is_fail_closed_while_turn_is_active(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model")
    agent = CodingAgent(
        llm=llm,
        workspace=str(tmp_path),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )
    original = agent.session
    replacement = Session(name="replacement", auto_save=False)
    cancel = asyncio.Event()

    async def exercise() -> None:
        token = agent.turn_lifecycle.begin(cancel)
        try:
            with pytest.raises(ActiveTurnTransitionError):
                agent.app_actions.switch_to_session(replacement, reason="resume")
            assert cancel.is_set() is True
            assert agent.session is original
            assert agent.agent.session is original
        finally:
            agent.turn_lifecycle.end(token)

    asyncio.run(exercise())


def test_sync_turn_keeps_session_and_compaction_transitions_closed_until_flush(
    tmp_path: Any,
) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model")
    agent = CodingAgent(
        llm=llm,
        workspace=str(tmp_path),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )
    original = agent.session
    started = threading.Event()
    release = threading.Event()
    result_box: list[Any] = []

    def run(message: str) -> Response:
        del message
        started.set()
        assert release.wait(timeout=5)
        agent.agent.last_turn_outcome = TurnOutcome.COMPLETED
        agent.agent.last_finish_reason = "stop"
        return Response(content="done", model="test-model", finish_reason="stop")

    cast(Any, agent.agent).run = Mock(side_effect=run)
    worker = threading.Thread(
        target=lambda: result_box.append(agent.run_once_result("hello")),
        daemon=True,
    )
    worker.start()
    assert started.wait(timeout=5)

    active_entry_id = original.tree.current_id
    assert active_entry_id is not None
    session_result = agent.app_actions.new_session()
    compact_result = agent.app_actions.compact_session(None)
    label_result = agent.app_actions.label_tree(active_entry_id, "racing label")
    name_result = agent.app_actions.name_session("racing name")

    assert session_result.ok is False
    assert "active turn" in (session_result.error or "").lower()
    assert compact_result.ok is False
    assert "active turn" in (compact_result.error or "").lower()
    assert label_result.ok is False
    assert "active turn" in (label_result.error or "").lower()
    assert name_result.ok is False
    assert "active turn" in (name_result.error or "").lower()
    assert "label" not in original.tree.entries[active_entry_id].metadata
    assert original.name != "racing name"
    assert agent.session is original

    release.set()
    worker.join(timeout=5)
    assert worker.is_alive() is False
    assert result_box[0].content == "done"
    assert agent.turn_lifecycle.is_active is False
    assert [entry.role for entry in original.get_current_conversation()][-2:] == [
        "user",
        "assistant",
    ]


def test_transition_lease_blocks_new_turn_until_session_switch_finishes(tmp_path: Any) -> None:
    llm = Mock()
    llm.config = Mock(model="test-model")
    agent = CodingAgent(
        llm=llm,
        workspace=str(tmp_path),
        verbose=False,
        enable_extensions=False,
        enable_skills=False,
    )
    original = agent.session
    replacement = Session(name="replacement", auto_save=False)
    transition_started = threading.Event()
    release_transition = threading.Event()
    switch_errors: list[BaseException] = []

    original_save = original.save

    def blocking_save() -> Any:
        transition_started.set()
        assert release_transition.wait(timeout=5)
        return original_save()

    def switch_session() -> None:
        try:
            agent.app_actions.switch_to_session(replacement, reason="resume")
        except BaseException as exc:  # pragma: no cover - assertion reports the exception
            switch_errors.append(exc)

    with patch.object(original, "save", side_effect=blocking_save):
        worker = threading.Thread(target=switch_session, daemon=True)
        worker.start()
        assert transition_started.wait(timeout=5)

        with pytest.raises(ActiveTurnTransitionError, match="transition is in progress"):
            agent.run_once_result("must not split across sessions")

        assert original.get_current_conversation() == []
        assert replacement.get_current_conversation() == []
        release_transition.set()
        worker.join(timeout=5)

    assert worker.is_alive() is False
    assert switch_errors == []
    assert agent.session is replacement
    assert agent.agent.session is replacement
