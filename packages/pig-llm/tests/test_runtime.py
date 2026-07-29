"""Explicit provider/model runtime contracts."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pig_llm import LLM, Config, Message, StreamChunk
from pig_llm.runtime import (
    AuthResolution,
    InMemoryCredentialStore,
    InMemoryModelStore,
    ModelCapabilities,
    ModelMetadata,
    ModelRuntime,
    ProviderRegistration,
    create_default_runtime,
)


def _factory(config: Config):
    return {"config": config}


def test_provider_owned_auth_resolution_precedence_and_overrides():
    credentials = InMemoryCredentialStore()
    credentials.set("demo", "stored-key")
    runtime = ModelRuntime(
        credentials=credentials,
        environment={
            "DEMO_API_KEY": "env-key",
            "DEMO_ORG": "org-1",
            "DEMO_BASE_URL": "https://example.test/v1",
        },
    )
    runtime.register_provider(
        ProviderRegistration(
            provider_id="demo",
            factory=_factory,
            api_key_env=("DEMO_API_KEY",),
            header_env={"X-Organization": "DEMO_ORG"},
            config_env={"base_url": "DEMO_BASE_URL"},
        )
    )

    stored = runtime.get_auth("demo")
    assert stored == AuthResolution(
        api_key="stored-key",
        headers={"X-Organization": "org-1"},
        config_overrides={"base_url": "https://example.test/v1"},
    )

    explicit = runtime.get_auth("demo", Config(provider="demo", api_key="explicit"))
    assert explicit.api_key == "explicit"

    credentials.delete("demo")
    assert runtime.get_auth("demo").api_key == "env-key"


def test_model_catalog_supports_registration_filtering_and_capabilities():
    runtime = ModelRuntime(models=InMemoryModelStore())
    runtime.register_provider(
        ProviderRegistration(
            provider_id="demo",
            factory=_factory,
            capabilities=ModelCapabilities(strict_json=True, deferred_tools=True),
            models=(
                ModelMetadata(provider="demo", model_id="small"),
                ModelMetadata(
                    provider="demo",
                    model_id="grammar",
                    capabilities=ModelCapabilities(grammar=True),
                ),
            ),
        )
    )

    assert [model.model_id for model in runtime.get_models("demo")] == [
        "grammar",
        "small",
    ]
    assert [
        model.model_id
        for model in runtime.get_models("demo", predicate=lambda model: "m" in model.model_id)
    ] == ["grammar", "small"]
    small = runtime.get_model("demo", "small")
    assert small is not None
    assert small.capabilities.strict_json is True
    grammar = runtime.get_model("demo", "grammar")
    assert grammar is not None
    capabilities = grammar.capabilities
    assert capabilities.strict_json is True
    assert capabilities.grammar is True
    assert capabilities.deferred_tools is True


def test_default_runtime_exposes_generated_provider_catalog():
    runtime = create_default_runtime()

    model = runtime.get_model("openai", "gpt-4o-mini")
    assert model is not None
    assert model.context_window is not None
    assert model.input_cost is not None
    assert any(item.model_id == "gpt-4o-mini" for item in runtime.get_models("openai"))


def test_reregistering_provider_replaces_empty_catalog_without_touching_others():
    runtime = ModelRuntime()
    runtime.register_provider(
        ProviderRegistration(
            "first",
            _factory,
            models=(ModelMetadata(provider="first", model_id="stale"),),
        )
    )
    runtime.register_provider(
        ProviderRegistration(
            "second",
            _factory,
            models=(ModelMetadata(provider="second", model_id="kept"),),
        )
    )

    runtime.register_provider(ProviderRegistration("first", _factory, models=()))

    assert runtime.get_models("first") == []
    assert [model.model_id for model in runtime.get_models("second")] == ["kept"]


def test_refresh_deduplicates_in_flight_work_and_reports_provider_errors():
    calls = 0

    async def refresh_ok(_auth):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [ModelMetadata(provider="ok", model_id="fresh")]

    async def refresh_bad(_auth):
        raise RuntimeError("catalog unavailable")

    runtime = ModelRuntime()
    runtime.register_provider(ProviderRegistration("ok", _factory, refresh_models=refresh_ok))
    runtime.register_provider(ProviderRegistration("bad", _factory, refresh_models=refresh_bad))

    async def run():
        first, second = await asyncio.gather(
            runtime.refresh_models("ok"),
            runtime.refresh_models("ok"),
        )
        report = await runtime.refresh_models()
        return first, second, report

    first, second, report = asyncio.run(run())
    assert calls == 2  # one deduplicated pair, then one explicit all-provider refresh
    assert first.updated == {"ok": 1}
    assert second.updated == {"ok": 1}
    assert report.updated == {"ok": 1}
    assert report.errors == {"bad": "catalog unavailable"}
    assert runtime.get_model("ok", "fresh") is not None


def test_runtime_creates_provider_with_resolved_config():
    runtime = ModelRuntime(environment={"DEMO_KEY": "env-key", "DEMO_ORG": "org-1"})
    runtime.register_provider(
        ProviderRegistration(
            "demo",
            _factory,
            api_key_env=("DEMO_KEY",),
            header_env={"X-Organization": "DEMO_ORG"},
            requires_api_key=True,
        )
    )

    provider = runtime.create_provider(Config(provider="demo", model="m"))
    assert provider["config"].api_key == "env-key"
    assert provider["config"].headers == {"X-Organization": "org-1"}


def test_runtime_rejects_missing_required_auth():
    runtime = ModelRuntime(environment={})
    runtime.register_provider(ProviderRegistration("demo", _factory, requires_api_key=True))
    with pytest.raises(ValueError, match="No API key for provider: demo"):
        runtime.create_provider(Config(provider="demo", model="m"))


def test_unknown_openai_compatible_provider_preserves_keyless_legacy_path():
    runtime = ModelRuntime(environment={})
    config = Config(provider="local", model="m", base_url="http://localhost:11434/v1")
    provider_class = Mock()

    with patch(
        "pig_llm.runtime.importlib.import_module",
        return_value=SimpleNamespace(OpenAIProvider=provider_class),
    ):
        runtime.create_provider(config)

    provider_class.assert_called_once_with(config)


def test_legacy_llm_constructor_uses_default_runtime_and_lazy_factory():
    provider_class = Mock(return_value=Mock())
    with patch(
        "pig_llm.runtime.importlib.import_module",
        return_value=SimpleNamespace(OpenAIProvider=provider_class),
    ):
        llm = LLM(provider="openai", api_key="test", model="gpt-4o-mini")

    provider_class.assert_called_once_with(llm.config)


def test_llm_accepts_an_explicit_runtime():
    runtime = ModelRuntime()
    runtime.register_provider(ProviderRegistration("demo", _factory, requires_api_key=False))

    llm = LLM(provider="demo", model="m", runtime=runtime)
    assert llm._provider["config"].provider == "demo"


def test_llm_profile_clone_rebuilds_provider_with_selected_key():
    runtime = ModelRuntime()
    runtime.register_provider(ProviderRegistration("demo", _factory, requires_api_key=True))
    llm = LLM(provider="demo", model="m1", api_key="key-one", runtime=runtime)

    rotated = llm.with_profile(api_key="key-two", model="m2")

    assert rotated is not llm
    assert rotated.config.api_key == "key-two"
    assert rotated.config.model == "m2"
    assert rotated._provider["config"].api_key == "key-two"
    assert llm.config.api_key == "key-one"


def test_llm_chat_stream_uses_provider_public_stream_contract():
    calls = []

    class StreamingProvider:
        def __init__(self, config: Config) -> None:
            self.config = config

        async def astream(self, **kwargs):
            calls.append(kwargs)
            yield StreamChunk(content="hello")
            yield StreamChunk(content=" world", finish_reason="stop")

    runtime = ModelRuntime()
    runtime.register_provider(
        ProviderRegistration(
            "stream-demo",
            StreamingProvider,
            requires_api_key=False,
        )
    )
    llm = LLM(provider="stream-demo", model="stream-model", runtime=runtime)

    async def collect():
        return [
            chunk
            async for chunk in llm.achat_stream(
                messages=[Message(role="user", content="hi")],
                temperature=0.2,
            )
        ]

    chunks = asyncio.run(collect())

    assert [chunk.content for chunk in chunks] == ["hello", " world"]
    assert calls[0]["model"] == "stream-model"
    assert calls[0]["temperature"] == 0.2
    assert calls[0]["messages"] == [Message(role="user", content="hi")]
