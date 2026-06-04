"""Model metadata lookup (context window + pricing) from the generated registry."""

from __future__ import annotations

from ._models_generated import MODELS

_BY_BARE: dict[str, tuple[int, float, float, float]] | None = None


def _by_bare() -> dict[str, tuple[int, float, float, float]]:
    global _BY_BARE
    if _BY_BARE is None:
        index: dict[str, tuple[int, float, float, float]] = {}
        # MODELS is ordered native-provider-first, so setdefault keeps canonical
        # pricing over aggregator (openrouter/azure) duplicates of the same name.
        for key, value in MODELS.items():
            index.setdefault(key.rsplit("/", 1)[-1], value)
        _BY_BARE = index
    return _BY_BARE


def get_model_info(model: str | None) -> dict[str, float] | None:
    """Return ``{context_window, input_cost, output_cost, cache_read_cost}``, or None.

    Costs are USD per million tokens. Looks up the exact id first, then the bare
    model name (after the last ``/``) so OpenRouter-style ``vendor/model`` ids
    resolve to their underlying model.
    """
    if not model:
        return None
    entry = MODELS.get(model) or _by_bare().get(model.rsplit("/", 1)[-1])
    if entry is None:
        return None
    context_window, input_cost, output_cost, cache_read_cost = entry
    return {
        "context_window": context_window,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "cache_read_cost": cache_read_cost,
    }
