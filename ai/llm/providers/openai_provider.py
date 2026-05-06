from __future__ import annotations
from typing import Optional
from ai.llm.providers.base import BaseLLMProvider
from ai.llm.types import LLMRequest, LLMResponse, LLMUsage


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        from openai import OpenAI
        self.api_key = api_key
        self.base_url = base_url
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def complete(self, request: LLMRequest) -> LLMResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        kwargs = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.system:
            kwargs["messages"] = [{"role": "system", "content": request.system}] + messages
        if request.metadata.get("json_mode"):
            kwargs["response_format"] = {"type": "json_object"}

        resp = self.client.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content if resp.choices and resp.choices[0].message else "") or ""
        usage_obj = getattr(resp, "usage", None)
        usage = LLMUsage(
            input_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
        )
        return LLMResponse(
            text=text,
            model=getattr(resp, "model", request.model),
            provider="openai",
            stop_reason=(resp.choices[0].finish_reason if resp.choices else None),
            usage=usage,
            raw=resp,
        )

    def test_connection(self) -> bool:
        try:
            self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return True
        except Exception:
            return False

    def supports_json_mode(self) -> bool:
        return True

    def supports_tools(self) -> bool:
        return True
