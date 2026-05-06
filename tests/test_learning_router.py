import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agents


def test_learning_agent_without_router_legacy_path(monkeypatch):
    monkeypatch.setattr(
        agents,
        "_call_with_retry",
        lambda *args, **kwargs: ('[{"category":"pattern","lesson":"Always validate.","importance":"high","applies_to":"all"}]', {"input_tokens": 1, "output_tokens": 1}),
    )
    monkeypatch.setattr(agents, "_upsert_lesson", lambda *args, **kwargs: (1, False))

    class DummyDB:
        def commit(self):
            return None

    lessons = agents.learning_agent(
        client=object(),
        db=DummyDB(),
        ticket_id=1,
        ticket_subject="subject",
        template_name="tpl",
        workflow_name="wf",
        original_ai_output="old",
        final_po_output="new",
    )
    assert isinstance(lessons, list)
    assert lessons


def test_learning_agent_uses_router_when_provided(monkeypatch):
    monkeypatch.setattr(agents, "_upsert_lesson", lambda *args, **kwargs: (1, False))

    class DummyResp:
        text = '[{"category":"pattern","lesson":"Always validate.","importance":"high","applies_to":"all"}]'
        usage = type("Usage", (), {"input_tokens": 2, "output_tokens": 3})()

    class DummyRouter:
        def complete(self, **kwargs):
            assert kwargs["agent_name"] == "learning_agent"
            return DummyResp()

    class DummyDB:
        def commit(self):
            return None

    lessons, usage = agents.learning_agent(
        client=object(),
        db=DummyDB(),
        ticket_id=1,
        ticket_subject="subject",
        template_name="tpl",
        workflow_name="wf",
        original_ai_output="old",
        final_po_output="new",
        llm_router=DummyRouter(),
        include_usage=True,
    )
    assert lessons
    assert usage["input_tokens"] == 2


def test_learning_agent_router_failure_safe_and_no_save(monkeypatch):
    saved = {"count": 0}
    monkeypatch.setattr(agents, "_upsert_lesson", lambda *args, **kwargs: saved.__setitem__("count", saved["count"] + 1))

    class BoomRouter:
        def complete(self, **kwargs):
            raise RuntimeError("router down")

    class DummyDB:
        def commit(self):
            return None

    lessons, usage = agents.learning_agent(
        client=object(),
        db=DummyDB(),
        ticket_id=1,
        ticket_subject="subject",
        template_name="tpl",
        workflow_name="wf",
        original_ai_output="old",
        final_po_output="new",
        llm_router=BoomRouter(),
        include_usage=True,
    )
    assert lessons == []
    assert usage == {}
    assert saved["count"] == 0
