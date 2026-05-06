import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import AgentOrchestrator
import agents


def test_qa_agent_without_router_legacy_path(monkeypatch):
    monkeypatch.setattr(agents, "_call_with_retry", lambda *args, **kwargs: ('{"passed": true, "score": 90}', {"input_tokens": 1, "output_tokens": 1}))
    result = agents.qa_agent(
        client=object(),
        agent_output="draft",
        output_type="draft_response",
        ticket_subject="subject",
        kb_brief="",
    )
    assert result["score"] == 90
    assert result["passed"] is True


def test_qa_agent_uses_router_when_provided():
    class DummyResp:
        text = '{"passed": false, "score": 10, "critical_issues": ["x"]}'
        usage = type("Usage", (), {"input_tokens": 2, "output_tokens": 3})()

    class DummyRouter:
        def complete(self, **kwargs):
            assert kwargs["agent_name"] == "qa_agent"
            return DummyResp()

    result = agents.qa_agent(
        client=object(),
        agent_output="draft",
        output_type="draft_response",
        ticket_subject="subject",
        kb_brief="",
        llm_router=DummyRouter(),
    )
    assert result["passed"] is False
    assert result["_usage"]["input_tokens"] == 2


def test_qa_agent_router_failure_fails_closed():
    class BoomRouter:
        def complete(self, **kwargs):
            raise RuntimeError("router down")

    result = agents.qa_agent(
        client=object(),
        agent_output="draft",
        output_type="draft_response",
        ticket_subject="subject",
        kb_brief="",
        llm_router=BoomRouter(),
    )
    assert result["passed"] is False
    assert "manual review" in result["summary"].lower()


def test_run_qa_fails_closed_on_exception(monkeypatch):
    monkeypatch.setattr(agents, "qa_agent", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    orch = AgentOrchestrator(anthropic_key="test-key", db=None)

    result = orch.run_qa(
        ticket_id=123,
        agent_output="draft",
        output_type="draft_response",
        ticket_subject="subject",
        kb_brief=""
    )

    assert result["passed"] is False
    assert "manual review" in result["summary"].lower()
    assert result["critical_issues"]
