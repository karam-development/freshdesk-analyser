from __future__ import annotations
from typing import Optional, Tuple
from ai.llm.providers.anthropic_provider import AnthropicProvider
from ai.llm.providers.openai_provider import OpenAIProvider


class LLMGateway:
    def __init__(self, provider_name: str, api_key: str, base_url: Optional[str] = None):
        name = (provider_name or "").strip().lower()
        if name == "anthropic":
            self.provider = AnthropicProvider(api_key=api_key)
        elif name == "openai":
            self.provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")

    def complete(self, request):
        return self.provider.complete(request)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            result = self.provider.test_connection()
            if isinstance(result, tuple):
                return result
            return (bool(result), "Connected" if result else "Connection failed")
        except Exception as e:
            return (False, str(e)[:200])
