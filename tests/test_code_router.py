import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents


def test_code_agent_without_router_legacy_path(monkeypatch):
    monkeypatch.setattr(agents, "_call_with_retry", lambda *args, **kwargs: ("legacy code analysis", {"input_tokens": 1, "output_tokens": 2}))
    result, usage = agents.code_agent(
        client=object(),
        ticket_subject="subject",
        ticket_summary="summary",
        full_code_context="liquid code",
    )
    assert result == "legacy code analysis"
    assert usage["output_tokens"] == 2


def test_code_agent_uses_router_when_provided():
    class DummyResp:
        text = "router code analysis"
        model = "test-model"
        usage = type("Usage", (), {"input_tokens": 3, "output_tokens": 4})()

    class DummyRouter:
        def complete(self, **kwargs):
            assert kwargs["agent_name"] == "code_agent"
            return DummyResp()

    result, usage = agents.code_agent(
        client=object(),
        ticket_subject="subject",
        ticket_summary="summary",
        full_code_context="liquid code",
        llm_router=DummyRouter(),
    )
    assert result == "router code analysis"
    assert usage["input_tokens"] == 3
    assert usage["model"] == "test-model"


def test_code_agent_router_failure_returns_safe_fallback():
    class BoomRouter:
        def complete(self, **kwargs):
            raise RuntimeError("provider down")

    result, usage = agents.code_agent(
        client=object(),
        ticket_subject="subject",
        ticket_summary="summary",
        full_code_context="secret_variable_name = x",
        llm_router=BoomRouter(),
    )
    assert result == "[Code Agent unavailable — no template analysis available. Assess based on ticket description only.]"
    assert usage == {}
    assert "secret_variable_name" not in result
