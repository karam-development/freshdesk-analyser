import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from ai.llm.gateway import LLMGateway
from ai.llm.pricing import estimate_cost
from ai.llm.providers.anthropic_provider import AnthropicProvider
from ai.llm.types import LLMMessage, LLMRequest, LLMResponse, LLMUsage


def test_types_construct():
    req = LLMRequest(model="claude-3-5-haiku-latest", messages=[LLMMessage(role="user", content="Hello")])
    resp = LLMResponse(text="Hi", model=req.model, provider="anthropic", usage=LLMUsage(input_tokens=10, output_tokens=2))
    assert req.messages[0].content == "Hello"
    assert resp.usage.input_tokens == 10


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMGateway(provider_name="unknown-provider", api_key="dummy")


def test_anthropic_provider_instantiates_without_call():
    provider = AnthropicProvider(api_key="dummy-key")
    assert provider.api_key == "dummy-key"
    assert provider.supports_tools() is True


def test_pricing_returns_number():
    value = estimate_cost("anthropic", "claude-3-5-haiku-latest", LLMUsage(input_tokens=1000, output_tokens=500))
    assert isinstance(value, float)
    assert value >= 0
