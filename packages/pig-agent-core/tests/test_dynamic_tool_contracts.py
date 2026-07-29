"""Contracts for transcript-anchored and provider-constrained tools."""

from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import Mock

import pytest
from pig_agent_core import Agent
from pig_agent_core.models import ToolModelCapabilities
from pig_agent_core.session import Session, SessionTree
from pig_agent_core.tools import ToolResult, handlers_core, tool
from pig_agent_core.tools.contracts import ToolCapabilityError
from pig_agent_core.tools.registry import ToolRegistry


def _schema(name: str, **function_metadata: object) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
            **function_metadata,
        },
    }


def _handler() -> ToolResult:
    return ToolResult(ok=True)


def test_tool_result_serializes_added_tool_names_without_breaking_legacy_shape() -> None:
    legacy = ToolResult(ok=True, data="done")
    assert legacy.added_tool_names == []
    assert legacy.serialize() == '{"ok": true, "data": "done"}'

    dynamic = ToolResult(ok=True, data="loaded", added_tool_names=["search", "fetch"])
    assert '"added_tool_names": ["search", "fetch"]' in dynamic.serialize()

    truncated = ToolResult(
        ok=True,
        data="x" * 10_000,
        added_tool_names=["search"],
    ).serialize(max_chars=200)
    assert '"added_tool_names": ["search"]' in truncated


@pytest.mark.asyncio
async def test_discover_tools_returns_a_transcript_activation_anchor(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        handlers_core,
        "get_all_schemas",
        lambda: {
            "search_web": {
                "function": {"description": "Search the public web"},
            }
        },
    )
    result = await handlers_core.handle_discover_tools({"query": "web"}, "user", {}, None)

    assert result.ok is True
    assert result.added_tool_names
    assert set(result.added_tool_names) == {item["name"] for item in result.data["loaded"]}


def test_tool_decorator_emits_portable_constraint_metadata() -> None:
    @tool(
        strict_json="require",
        grammar={"type": "regex", "value": "[a-z]+"},
        deferred=True,
    )
    def constrained(value: str) -> str:
        return value

    function = constrained.to_openai_schema()["function"]
    assert function["strict_json"] == "require"
    assert function["grammar"] == {"type": "regex", "value": "[a-z]+"}
    assert function["defer_loading"] is True


def test_agent_registers_deferred_tools_outside_the_initial_active_set() -> None:
    @tool(deferred=True)
    def later() -> str:
        return "later"

    llm = Mock()
    llm.config = Mock(provider="test", model="test-model")
    llm.runtime.get_model.return_value = None
    agent = Agent(llm=llm, tools=[later])

    assert "later" in agent.registry.list_tools()
    assert "later" not in agent.registry.list_core_tools()


@pytest.mark.asyncio
async def test_direct_deferred_call_returns_its_activation_anchor() -> None:
    registry = ToolRegistry()
    registry.register("later", _handler, _schema("later"), is_core=False)

    result = await registry.execute(
        SimpleNamespace(
            function=SimpleNamespace(name="later", arguments="{}"),
        ),
        "user",
        {},
    )

    assert result.ok is True
    assert result.added_tool_names == ["later"]


def test_sync_direct_deferred_call_returns_its_activation_anchor() -> None:
    registry = ToolRegistry()
    registry.register("later", lambda: "ok", _schema("later"), is_core=False)

    result = registry.execute_sync("later")

    assert result.ok is True
    assert result.added_tool_names == ["later"]


def test_session_restores_available_tools_from_the_selected_transcript_branch() -> None:
    tree = SessionTree()
    root = tree.add_entry("system", "start")
    anchor = tree.add_entry("tool", "loaded", added_tool_names=["search"])
    search_branch = tree.add_entry("assistant", "continue")

    tree.switch_to(root.id)
    clean_branch = tree.add_entry("assistant", "other branch")

    assert tree.available_tool_names_at(anchor.id, initial_tool_names=["core"]) == {
        "core",
        "search",
    }
    assert tree.available_tool_names_at(search_branch.id, initial_tool_names=["core"]) == {
        "core",
        "search",
    }
    assert tree.available_tool_names_at(clean_branch.id, initial_tool_names=["core"]) == {"core"}


def test_session_add_tool_result_persists_activation_anchor(tmp_path: Any) -> None:
    session = Session(name="dynamic", workspace=str(tmp_path), auto_save=False)
    session.add_message("system", "start")
    entry = session.add_tool_result(
        ToolResult(ok=True, data="ready", added_tool_names=["search"]),
        name="discover_tools",
    )
    path = session.save()

    loaded = Session.load(path)
    assert loaded.available_tool_names_at(entry.id, initial_tool_names=["core"]) == {
        "core",
        "search",
    }


def test_compaction_checkpoint_preserves_prior_tool_activations() -> None:
    session = Session(name="dynamic", auto_save=False)
    session.add_message("system", "start")
    session.add_tool_result(
        ToolResult(ok=True, added_tool_names=["search"]),
        name="discover_tools",
    )
    for index in range(12):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"answer {index}")

    session.compact()

    assert session.available_tool_names_at(initial_tool_names=["core"]) == {
        "core",
        "search",
    }


def test_strict_json_prefer_degrades_but_require_is_gated() -> None:
    registry = ToolRegistry()
    registry.register(
        "preferred",
        _handler,
        _schema("preferred", strict_json="prefer"),
        is_core=True,
    )
    registry.register(
        "required",
        _handler,
        _schema("required", strict_json="require"),
        is_core=True,
    )

    supported = registry.get_provider_schemas(ToolModelCapabilities(supports_strict_tools=True))
    assert all(schema["function"]["strict"] is True for schema in supported)
    assert all("strict_json" not in schema["function"] for schema in supported)

    with pytest.raises(ToolCapabilityError, match="required.*strict JSON"):
        registry.get_provider_schemas(ToolModelCapabilities())

    preferred_only = ToolRegistry()
    preferred_only.register(
        "preferred",
        _handler,
        _schema("preferred", strict_json="prefer"),
        is_core=True,
    )
    assert (
        "strict" not in preferred_only.get_provider_schemas(ToolModelCapabilities())[0]["function"]
    )


@pytest.mark.parametrize("grammar_type", ["regex", "lark"])
def test_grammar_constraints_are_gated_and_rendered(grammar_type: str) -> None:
    registry = ToolRegistry()
    registry.register(
        "constrained",
        _handler,
        _schema(
            "constrained",
            grammar={"type": grammar_type, "value": "[a-z]+"},
        ),
        is_core=True,
    )

    with pytest.raises(ToolCapabilityError, match=f"{grammar_type} grammar"):
        registry.get_provider_schemas(ToolModelCapabilities())

    rendered = registry.get_provider_schemas(
        ToolModelCapabilities(
            supported_grammar_tools={cast(Literal["regex", "lark"], grammar_type)}
        )
    )[0]
    assert rendered["function"]["grammar"] == {
        "type": grammar_type,
        "value": "[a-z]+",
    }


def test_deferred_tools_are_marked_when_supported_and_hidden_when_unsupported() -> None:
    registry = ToolRegistry()
    registry.register("core", _handler, _schema("core"), is_core=True)
    registry.register("later", _handler, _schema("later"), is_core=False)

    deferred = registry.get_provider_schemas(
        ToolModelCapabilities(supports_deferred_tools=True),
        available_tool_names={"core"},
    )
    assert [schema["function"]["name"] for schema in deferred] == ["core", "later"]
    assert "defer_loading" not in deferred[0]["function"]
    assert deferred[1]["function"]["defer_loading"] is True

    fallback = registry.get_provider_schemas(
        ToolModelCapabilities(supports_deferred_tools=False),
        available_tool_names={"core"},
    )
    assert [schema["function"]["name"] for schema in fallback] == ["core"]
    assert all("defer_loading" not in schema["function"] for schema in fallback)


def test_transcript_anchor_makes_deferred_tool_eager_at_that_point() -> None:
    registry = ToolRegistry()
    registry.register("core", _handler, _schema("core"), is_core=True)
    registry.register("later", _handler, _schema("later"), is_core=False)
    session = Session(name="dynamic", auto_save=False)
    session.add_message("system", "start")
    anchor = session.add_tool_result(
        ToolResult(ok=True, added_tool_names=["later"]),
        name="discover_tools",
    )

    available = session.available_tool_names_at(
        anchor.id, initial_tool_names=registry.list_core_tools()
    )
    schemas = registry.get_provider_schemas(
        ToolModelCapabilities(supports_deferred_tools=True),
        available_tool_names=available,
    )
    assert all("defer_loading" not in schema["function"] for schema in schemas)


def test_compaction_does_not_leak_tool_activation_to_a_sibling_branch() -> None:
    session = Session(name="branches", auto_save=False)
    root = session.add_message("system", "start")
    clean_branch = session.add_message("user", "clean", parent_id=root.id)

    session.branch_to(root.id)
    session.add_tool_result(
        ToolResult(
            ok=True,
            data="SECRET-BRANCH-DATA",
            added_tool_names=["private_tool"],
        ),
        name="discover_tools",
    )
    for index in range(12):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"answer {index}")

    session.compact()

    assert session.available_tool_names_at() == {"private_tool"}
    assert session.available_tool_names_at(clean_branch.id) == set()
    clean_content = "\n".join(
        entry.content for entry in session.tree.get_path_to_entry(clean_branch.id)
    )
    assert "SECRET-BRANCH-DATA" not in clean_content
