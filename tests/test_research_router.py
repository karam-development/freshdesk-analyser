import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents


def test_research_agent_without_router_legacy_path(monkeypatch):
    monkeypatch.setattr(agents, "_find_similar_tickets", lambda *args, **kwargs: [{"ticket_id": 1, "subject": "s", "classification": "bug"}])
    monkeypatch.setattr(agents, "_find_relevant_lessons", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents, "_call_with_retry", lambda *args, **kwargs: ("legacy research", {"input_tokens": 1, "output_tokens": 2}))

    result, usage = agents.research_agent(
        client=object(),
        db=object(),
        ticket_id=1,
        ticket_subject="subject",
        ticket_summary="summary",
    )
    assert result == "legacy research"
    assert usage["output_tokens"] == 2


def test_research_agent_uses_router_when_provided(monkeypatch):
    monkeypatch.setattr(agents, "_find_similar_tickets", lambda *args, **kwargs: [{"ticket_id": 1, "subject": "s", "classification": "bug"}])
    monkeypatch.setattr(agents, "_find_relevant_lessons", lambda *args, **kwargs: [])

    class DummyResp:
        text = "router research"
        usage = type("Usage", (), {"input_tokens": 3, "output_tokens": 4})()

    class DummyRouter:
        def complete(self, **kwargs):
            assert kwargs["agent_name"] == "research_agent"
            return DummyResp()

    result, usage = agents.research_agent(
        client=object(),
        db=object(),
        ticket_id=1,
        ticket_subject="subject",
        ticket_summary="summary",
        llm_router=DummyRouter(),
    )
    assert result == "router research"
    assert usage["input_tokens"] == 3


def test_research_agent_router_failure_returns_safe_fallback(monkeypatch):
    monkeypatch.setattr(agents, "_find_similar_tickets", lambda *args, **kwargs: [{"ticket_id": 1, "subject": "s", "classification": "bug"}])
    monkeypatch.setattr(agents, "_find_relevant_lessons", lambda *args, **kwargs: [])

    class BoomRouter:
        def complete(self, **kwargs):
            raise RuntimeError("provider error")

    result, usage = agents.research_agent(
        client=object(),
        db=object(),
        ticket_id=1,
        ticket_subject="subject",
        ticket_summary="summary",
        llm_router=BoomRouter(),
    )
    assert result == "Research agent unavailable — proceeding without historical context."
    assert usage == {}
