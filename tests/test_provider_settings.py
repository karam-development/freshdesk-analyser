import sys
from pathlib import Path
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_openai_provider_instantiates_without_api_call(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_mod = types.SimpleNamespace(OpenAI=DummyOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_mod)

    from ai.llm.providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(api_key="dummy", base_url="https://api.openai.com/v1")
    assert p.api_key == "dummy"


def test_gateway_supports_anthropic_and_openai(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_mod = types.SimpleNamespace(OpenAI=DummyOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_mod)

    from ai.llm.gateway import LLMGateway
    g1 = LLMGateway("anthropic", "dummy")
    g2 = LLMGateway("openai", "dummy")
    assert g1.provider is not None
    assert g2.provider is not None


def test_llm_settings_fallback_from_anthropic_key(monkeypatch):
    values = {
        "llm_provider": "",
        "llm_api_key": "",
        "llm_base_url": "",
        "anthropic_api_key": "legacy-ant-key",
        "llm_fast_model": "",
        "llm_main_model": "",
    }

    import app
    monkeypatch.setattr(app, "get_setting", lambda key, default="", db=None: values.get(key, default))
    cfg = app.get_llm_config(object())
    assert cfg["provider"] == "anthropic"
    assert cfg["api_key"] == "legacy-ant-key"
