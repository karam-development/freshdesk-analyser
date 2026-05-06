from ai.llm.types import LLMUsage

# USD per token (approx): input/output per 1M tokens converted to token units.
_ANTHROPIC_MODEL_PRICING = {
    "claude-3-5-sonnet-latest": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-3-5-haiku-latest": {"input": 0.8 / 1_000_000, "output": 4.0 / 1_000_000},
    "claude-3-opus-latest": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
}


def estimate_cost(provider: str, model: str, usage: LLMUsage) -> float:
    if provider != "anthropic":
        return 0.0
    pricing = _ANTHROPIC_MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    return float((usage.input_tokens * pricing["input"]) + (usage.output_tokens * pricing["output"]))
