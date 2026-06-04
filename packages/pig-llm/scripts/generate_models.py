#!/usr/bin/env python3
"""Generate the model registry from models.dev.

Fetches https://models.dev/api.json and writes a compact Python data module
(`pig_llm/_models_generated.py`) mapping model id -> (context_window,
input_cost_per_M, output_cost_per_M, cache_read_cost_per_M). Run with:

    python scripts/generate_models.py

Mirrors pi-mono's scripts/generate-models.ts (same data source).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

API_URL = "https://models.dev/api.json"

# Providers pig-llm targets, native first so their canonical pricing wins the
# bare-id index over aggregators (openrouter/azure/vercel) listed last.
PROVIDER_ORDER = [
    "openai",
    "anthropic",
    "google",
    "google-vertex",
    "groq",
    "deepseek",
    "mistral",
    "cohere",
    "xai",
    "cerebras",
    "amazon-bedrock",
    "perplexity",
    "togetherai",
    "azure",
    "openrouter",
    "vercel",
]

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "pig_llm" / "_models_generated.py"


def main() -> None:
    print(f"Fetching {API_URL} ...")
    request = urllib.request.Request(API_URL, headers={"User-Agent": "pig-mono-model-gen"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310
        data = json.loads(resp.read())

    rows: list[tuple[str, int, float, float, float]] = []
    seen: set[str] = set()
    for provider in PROVIDER_ORDER:
        models = (data.get(provider) or {}).get("models") or {}
        for model_id, info in models.items():
            limit = info.get("limit") or {}
            cost = info.get("cost") or {}
            context = limit.get("context")
            input_cost = cost.get("input")
            output_cost = cost.get("output")
            if not context or input_cost is None or output_cost is None:
                continue
            if model_id in seen:
                continue
            seen.add(model_id)
            # cache_read defaults to the input price when the provider doesn't
            # publish a discounted cached-read rate.
            cache_read = cost.get("cache_read")
            cache_read = float(cache_read) if cache_read is not None else float(input_cost)
            rows.append((model_id, int(context), float(input_cost), float(output_cost), cache_read))

    rows.sort(key=lambda r: r[0])
    lines = [
        '"""Auto-generated model registry. Do not edit — run scripts/generate_models.py."""',
        "",
        "# model id -> (context_window, input_$/M, output_$/M, cache_read_$/M)",
        "MODELS: dict[str, tuple[int, float, float, float]] = {",
    ]
    for model_id, context, inp, out, cache in rows:
        lines.append(f"    {model_id!r}: ({context}, {inp}, {out}, {cache}),")
    lines.append("}")
    OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(rows)} models to {OUTPUT}")


if __name__ == "__main__":
    main()
