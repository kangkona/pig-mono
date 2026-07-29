"""Explicit provider, authentication, and model-catalog runtime.

The runtime is intentionally independent from provider SDK imports. Provider
classes remain lazy and are instantiated only when a caller creates an LLM.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from ._models_generated import MODELS
from .config import Config


@dataclass(frozen=True)
class ModelCapabilities:
    """Provider/model features used to gate request construction."""

    strict_json: bool = False
    grammar: bool = False
    grammar_types: frozenset[Literal["regex", "lark"]] = field(default_factory=frozenset)
    deferred_tools: bool = False

    def merged(self, override: ModelCapabilities) -> ModelCapabilities:
        """Combine provider defaults with model-specific capabilities."""
        return ModelCapabilities(
            strict_json=self.strict_json or override.strict_json,
            grammar=self.grammar or override.grammar,
            grammar_types=self.grammar_types | override.grammar_types,
            deferred_tools=self.deferred_tools or override.deferred_tools,
        )


@dataclass(frozen=True)
class ModelMetadata:
    """A model entry owned by a provider catalog."""

    provider: str
    model_id: str
    context_window: int | None = None
    input_cost: float | None = None
    output_cost: float | None = None
    cache_read_cost: float | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)


@dataclass(frozen=True)
class AuthResolution:
    """Resolved request authentication and provider configuration."""

    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    config_overrides: dict[str, Any] = field(default_factory=dict)


class CredentialStore(ABC):
    """Storage interface for provider credentials."""

    @abstractmethod
    def get(self, provider_id: str) -> str | None:
        """Return a stored API key, if present."""

    @abstractmethod
    def set(self, provider_id: str, api_key: str) -> None:
        """Store an API key."""

    @abstractmethod
    def delete(self, provider_id: str) -> None:
        """Delete a stored API key."""


class InMemoryCredentialStore(CredentialStore):
    """Process-local credential store, useful for embedding and tests."""

    def __init__(self, credentials: Mapping[str, str] | None = None):
        self._credentials = dict(credentials or {})

    def get(self, provider_id: str) -> str | None:
        """Return the process-local credential for a provider."""
        return self._credentials.get(provider_id)

    def set(self, provider_id: str, api_key: str) -> None:
        """Set the process-local credential for a provider."""
        self._credentials[provider_id] = api_key

    def delete(self, provider_id: str) -> None:
        """Remove a process-local provider credential if it exists."""
        self._credentials.pop(provider_id, None)


class ModelStore(ABC):
    """Synchronous model-catalog storage contract."""

    @abstractmethod
    def get(self, provider_id: str, model_id: str) -> ModelMetadata | None:
        """Read one model."""

    @abstractmethod
    def list(self, provider_id: str | None = None) -> list[ModelMetadata]:
        """Read a stable catalog snapshot."""

    @abstractmethod
    def replace(self, provider_id: str, models: Iterable[ModelMetadata]) -> None:
        """Atomically replace a provider's catalog snapshot."""


class InMemoryModelStore(ModelStore):
    """Process-local model catalog with deterministic reads."""

    def __init__(self, models: Iterable[ModelMetadata] = ()):
        self._models: dict[tuple[str, str], ModelMetadata] = {}
        for model in models:
            self._models[(model.provider, model.model_id)] = model

    def get(self, provider_id: str, model_id: str) -> ModelMetadata | None:
        """Return one model from the current in-memory snapshot."""
        return self._models.get((provider_id, model_id))

    def list(self, provider_id: str | None = None) -> list[ModelMetadata]:
        """Return a deterministic snapshot, optionally scoped to one provider."""
        models = (
            model
            for (entry_provider, _), model in self._models.items()
            if provider_id is None or entry_provider == provider_id
        )
        return sorted(models, key=lambda model: (model.provider, model.model_id))

    def replace(self, provider_id: str, models: Iterable[ModelMetadata]) -> None:
        """Atomically replace one provider's in-memory model snapshot."""
        replacement: dict[tuple[str, str], ModelMetadata] = {}
        for model in models:
            if model.provider != provider_id:
                raise ValueError(
                    f"Catalog model provider '{model.provider}' does not match '{provider_id}'"
                )
            replacement[(provider_id, model.model_id)] = model
        self._models = {key: model for key, model in self._models.items() if key[0] != provider_id}
        self._models.update(replacement)


ProviderFactory = Callable[[Config], Any]
CatalogRefresher = Callable[[AuthResolution], Awaitable[Iterable[ModelMetadata]]]
AuthResolver = Callable[[Config | None, CredentialStore, Mapping[str, str]], AuthResolution]


@dataclass(frozen=True)
class ProviderRegistration:
    """All provider-owned runtime behavior and metadata."""

    provider_id: str
    factory: ProviderFactory
    models: tuple[ModelMetadata, ...] = ()
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    requires_api_key: bool = True
    api_key_env: tuple[str, ...] = ()
    header_env: Mapping[str, str] = field(default_factory=dict)
    config_env: Mapping[str, str] = field(default_factory=dict)
    auth_resolver: AuthResolver | None = None
    refresh_models: CatalogRefresher | None = None


@dataclass(frozen=True)
class RefreshReport:
    """Per-provider catalog refresh results."""

    updated: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class ModelRuntime:
    """Explicit runtime for providers, credentials, and model catalogs."""

    def __init__(
        self,
        *,
        credentials: CredentialStore | None = None,
        models: ModelStore | None = None,
        environment: Mapping[str, str] | None = None,
    ):
        """Initialize the runtime with pluggable credential and model stores."""
        self.credentials = credentials or InMemoryCredentialStore()
        self.models = models or InMemoryModelStore()
        self.environment = os.environ if environment is None else environment
        self._providers: dict[str, ProviderRegistration] = {}
        self._refresh_tasks: dict[str, asyncio.Task[RefreshReport]] = {}

    def register_provider(self, registration: ProviderRegistration) -> None:
        """Register or replace a provider and its static catalog."""
        if not registration.provider_id:
            raise ValueError("provider_id must not be empty")
        self._providers[registration.provider_id] = registration
        self.models.replace(registration.provider_id, registration.models)

    def get_registration(self, provider_id: str) -> ProviderRegistration | None:
        """Return the provider-owned registration, if one is installed."""
        return self._providers.get(provider_id)

    def get_auth(self, provider_id: str, config: Config | None = None) -> AuthResolution:
        """Resolve provider-owned auth without instantiating its SDK client."""
        registration = self._providers.get(provider_id)
        if registration is None:
            raise ValueError(f"Unknown provider '{provider_id}'")
        if registration.auth_resolver is not None:
            return registration.auth_resolver(config, self.credentials, self.environment)

        api_key = config.api_key if config is not None else None
        if not api_key:
            api_key = self.credentials.get(provider_id)
        if not api_key:
            api_key = next(
                (
                    self.environment[name]
                    for name in registration.api_key_env
                    if self.environment.get(name)
                ),
                None,
            )
        headers = {
            header: self.environment[env_name]
            for header, env_name in registration.header_env.items()
            if self.environment.get(env_name)
        }
        config_overrides = {
            field_name: self.environment[env_name]
            for field_name, env_name in registration.config_env.items()
            if self.environment.get(env_name)
            and (config is None or getattr(config, field_name, None) is None)
        }
        return AuthResolution(api_key, headers, config_overrides)

    def get_model(self, provider_id: str, model_id: str) -> ModelMetadata | None:
        """Return model metadata with provider capability defaults applied."""
        model = self.models.get(provider_id, model_id)
        if model is None:
            return None
        registration = self._providers.get(provider_id)
        if registration is None:
            return model
        return replace(
            model,
            capabilities=registration.capabilities.merged(model.capabilities),
        )

    def get_models(
        self,
        provider_id: str | None = None,
        *,
        predicate: Callable[[ModelMetadata], bool] | None = None,
        available_only: bool = False,
    ) -> list[ModelMetadata]:
        """Synchronously read and optionally filter the current catalog snapshot."""
        result: list[ModelMetadata] = []
        for stored in self.models.list(provider_id):
            model = self.get_model(stored.provider, stored.model_id)
            if model is None:
                continue
            registration = self._providers.get(model.provider)
            if available_only and registration and registration.requires_api_key:
                if self.get_auth(model.provider).api_key is None:
                    continue
            if predicate is None or predicate(model):
                result.append(model)
        return result

    def create_provider(self, config: Config) -> Any:
        """Create a provider SDK client from fully resolved configuration."""
        registration = self._providers.get(config.provider)
        if registration is None:
            if not config.base_url:
                raise ValueError(
                    f"Unknown provider '{config.provider}'. "
                    "Provide base_url for OpenAI-compatible custom providers."
                )
            # Preserve the legacy OpenAI-compatible path: local gateways may
            # intentionally accept an empty key, and the provider SDK may also
            # resolve its own ambient OpenAI credential.
            return _lazy_factory("openai", "OpenAIProvider")(config)
        auth = self.get_auth(config.provider, config)
        if registration.requires_api_key and not auth.api_key:
            raise ValueError(f"No API key for provider: {config.provider}")
        updates = dict(auth.config_overrides)
        if auth.api_key and auth.api_key != config.api_key:
            updates["api_key"] = auth.api_key
        if auth.headers:
            updates["headers"] = {**config.headers, **auth.headers}
        resolved_config = config.model_copy(update=updates) if updates else config
        return registration.factory(resolved_config)

    async def _refresh_provider(self, provider_id: str) -> RefreshReport:
        registration = self._providers[provider_id]
        if registration.refresh_models is None:
            return RefreshReport()
        try:
            refreshed = tuple(await registration.refresh_models(self.get_auth(provider_id)))
            self.models.replace(provider_id, refreshed)
            return RefreshReport(updated={provider_id: len(refreshed)})
        except Exception as exc:  # catalog failures are provider-scoped results
            return RefreshReport(errors={provider_id: str(exc)})

    async def _refresh_deduplicated(self, provider_id: str) -> RefreshReport:
        task = self._refresh_tasks.get(provider_id)
        if task is None or task.done():
            task = asyncio.create_task(self._refresh_provider(provider_id))
            self._refresh_tasks[provider_id] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self._refresh_tasks.get(provider_id) is task:
                self._refresh_tasks.pop(provider_id, None)

    async def refresh_models(self, provider_id: str | None = None) -> RefreshReport:
        """Explicitly refresh one or all dynamic catalogs.

        Concurrent refreshes of the same provider share one in-flight request.
        Failures are returned by provider and leave the previous snapshot intact.
        """
        if provider_id is not None:
            if provider_id not in self._providers:
                return RefreshReport(errors={provider_id: "unknown provider"})
            return await self._refresh_deduplicated(provider_id)

        provider_ids = [
            item.provider_id for item in self._providers.values() if item.refresh_models is not None
        ]
        reports = await asyncio.gather(*(self._refresh_deduplicated(item) for item in provider_ids))
        updated: dict[str, int] = {}
        errors: dict[str, str] = {}
        for report in reports:
            updated.update(report.updated)
            errors.update(report.errors)
        return RefreshReport(updated=updated, errors=errors)


def _lazy_factory(module_name: str, class_name: str) -> ProviderFactory:
    def factory(config: Config) -> Any:
        module = importlib.import_module(f".providers.{module_name}", package="pig_llm")
        return getattr(module, class_name)(config)

    return factory


_BUILTIN_PROVIDERS = {
    "openai": ("openai", "OpenAIProvider", ("OPENAI_API_KEY",)),
    "anthropic": ("anthropic", "AnthropicProvider", ("ANTHROPIC_API_KEY",)),
    "google": ("google", "GoogleProvider", ("GOOGLE_API_KEY", "GEMINI_API_KEY")),
    "azure": ("azure", "AzureOpenAIProvider", ("AZURE_OPENAI_API_KEY",)),
    "groq": ("groq", "GroqProvider", ("GROQ_API_KEY",)),
    "mistral": ("mistral", "MistralProvider", ("MISTRAL_API_KEY",)),
    "openrouter": ("openrouter", "OpenRouterProvider", ("OPENROUTER_API_KEY",)),
    "xai": ("xai", "XAIProvider", ("XAI_API_KEY",)),
    "cerebras": ("cerebras", "CerebrasProvider", ("CEREBRAS_API_KEY",)),
    "cohere": ("cohere", "CohereProvider", ("COHERE_API_KEY",)),
    "perplexity": ("perplexity", "PerplexityProvider", ("PERPLEXITY_API_KEY",)),
    "deepseek": ("deepseek", "DeepSeekProvider", ("DEEPSEEK_API_KEY",)),
    "together": ("together", "TogetherProvider", ("TOGETHER_API_KEY",)),
}


def _generated_models(provider_id: str) -> tuple[ModelMetadata, ...]:
    """Convert provider-prefixed generated entries into a native catalog."""
    prefix = f"{provider_id}/"
    return tuple(
        ModelMetadata(
            provider=provider_id,
            model_id=model_key.removeprefix(prefix),
            context_window=values[0],
            input_cost=values[1],
            output_cost=values[2],
            cache_read_cost=values[3],
        )
        for model_key, values in MODELS.items()
        if model_key.startswith(prefix)
    )


def create_default_runtime() -> ModelRuntime:
    """Create the backwards-compatible built-in provider runtime."""
    runtime = ModelRuntime()
    for provider_id, (module_name, class_name, api_key_env) in _BUILTIN_PROVIDERS.items():
        runtime.register_provider(
            ProviderRegistration(
                provider_id=provider_id,
                factory=_lazy_factory(module_name, class_name),
                models=_generated_models(provider_id),
                api_key_env=api_key_env,
            )
        )
    runtime.register_provider(
        ProviderRegistration(
            provider_id="bedrock",
            factory=_lazy_factory("bedrock", "BedrockProvider"),
            requires_api_key=False,
        )
    )
    return runtime


_DEFAULT_RUNTIME: ModelRuntime | None = None


def get_default_runtime() -> ModelRuntime:
    """Return the process-wide built-in runtime used by legacy ``LLM`` calls."""
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = create_default_runtime()
    return _DEFAULT_RUNTIME
