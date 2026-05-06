from anthropic import Anthropic

from ai.llm.providers.base import BaseLLMProvider
from ai.llm.types import LLMRequest, LLMResponse, LLMUsage


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = Anthropic(api_key=api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        kwargs = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system:
            kwargs["system"] = request.system

        resp = self.client.messages.create(**kwargs)
        text = ""
        if getattr(resp, "content", None):
            chunks = []
            for c in resp.content:
                if getattr(c, "type", "") == "text":
                    chunks.append(getattr(c, "text", ""))
            text = "".join(chunks)

        usage_obj = getattr(resp, "usage", None)
        usage = LLMUsage(
            input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
            output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(usage_obj, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
        )

        return LLMResponse(
            text=text,
            model=getattr(resp, "model", request.model),
            provider="anthropic",
            stop_reason=getattr(resp, "stop_reason", None),
            usage=usage,
            raw=resp,
        )

    def test_connection(self) -> bool:
        try:
            self.client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=5,
                temperature=0,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    def supports_vision(self) -> bool:
        return False

    def supports_json_mode(self) -> bool:
        return True

    def supports_tools(self) -> bool:
        return True
