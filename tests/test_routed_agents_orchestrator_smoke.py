import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents
from agents import AgentOrchestrator


class _FailRouter:
    def complete(self, **kwargs):
        raise RuntimeError("router unavailable")


def test_orchestrator_routed_agent_failures_are_safe(monkeypatch):
    monkeypatch.setattr(agents, "_find_similar_tickets", lambda *a, **k: [{"ticket_id": 2, "subject": "s", "classification": "bug"}])
    monkeypatch.setattr(agents, "_find_relevant_lessons", lambda *a, **k: [])
    monkeypatch.setattr(agents, "_upsert_lesson", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not save")))

    class _DB:
        def execute(self, *args, **kwargs):
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def commit(self):
            return None

    orch = AgentOrchestrator(anthropic_key="test-key", db=_DB())
    orch.llm_router = _FailRouter()

    kb = orch.get_kb_brief(1, "subj", "sum", "KB context")
    assert "KB Agent failed" in kb

    code = orch.get_code_brief(1, "subj", "sum", "some_code = 1")
    assert "Code Agent unavailable" in code
    assert "some_code" not in code

    research = orch.get_research_brief(1, "subj", "sum")
    assert research == "Research agent unavailable — proceeding without historical context."

    qa = orch.run_qa(1, "output", "draft_response", "subj", "kb")
    assert qa["passed"] is False

    learn = orch.run_learning(1, "subj", "tpl", "wf", "old output", "new output", "draft_response")
    assert learn == []
