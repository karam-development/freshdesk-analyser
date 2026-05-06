"""Tests that LLMRouter does NOT silently fall back to anthropic_api_key and raises
a clear error when llm_api_key is missing."""
import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.llm.router import LLMRouter


def _db_with_settings(**kwargs):
    """In-memory DB with a settings table and optional key-value pairs."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("""CREATE TABLE agent_model_config (
        agent_name TEXT UNIQUE NOT NULL,
        provider TEXT NOT NULL DEFAULT 'anthropic',
        model TEXT NOT NULL,
        temperature REAL DEFAULT 0.0,
        max_tokens INTEGER DEFAULT 2000,
        fallback_provider TEXT DEFAULT '',
        fallback_model TEXT DEFAULT ''
    )""")
    for k, v in kwargs.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
    db.commit()
    return db


def test_router_raises_when_llm_api_key_missing():
    """complete() must raise a clear error when llm_api_key is not set."""
    db = _db_with_settings(llm_provider="anthropic")  # no llm_api_key
    db.execute(
        "INSERT INTO agent_model_config(agent_name,provider,model) VALUES ('kb_agent','anthropic','claude-haiku-4-5-20251001')"
    )
    db.commit()

    r = LLMRouter(db=db)
    try:
        r.complete("kb_agent", "sys", [{"role": "user", "content": "hi"}])
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "No API key configured" in str(e)
        assert "anthropic" in str(e)


def test_router_does_not_use_anthropic_api_key_as_fallback():
    """Even when anthropic_api_key is set, the router must NOT use it.
    It must only look at llm_api_key."""
    db = _db_with_settings(
        llm_provider="anthropic",
        anthropic_api_key="legacy-key",  # old key present
        # llm_api_key is intentionally absent
    )
    db.execute(
        "INSERT INTO agent_model_config(agent_name,provider,model) VALUES ('kb_agent','anthropic','claude-haiku-4-5-20251001')"
    )
    db.commit()

    r = LLMRouter(db=db)
    settings = r.get_provider_settings("anthropic")
    assert settings["api_key"] == "", (
        "get_provider_settings must return empty api_key when llm_api_key is not set, "
        "even if anthropic_api_key exists"
    )

    try:
        r.complete("kb_agent", "sys", [{"role": "user", "content": "hi"}])
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "No API key configured" in str(e), (
            f"Expected 'No API key configured' error, got: {e}"
        )


def test_router_works_when_llm_api_key_is_set(monkeypatch):
    """When llm_api_key is set, complete() must reach the gateway (not fail on key check)."""
    db = _db_with_settings(llm_provider="anthropic", llm_api_key="test-key")
    db.execute(
        "INSERT INTO agent_model_config(agent_name,provider,model) VALUES ('kb_agent','anthropic','claude-haiku-4-5-20251001')"
    )
    db.commit()

    import ai.llm.router as router_mod

    class _DummyGW:
        def __init__(self, **kw):
            pass

        def complete(self, req):
            class R:
                text = "ok"
                model = "claude-haiku-4-5-20251001"
                provider = "anthropic"
                usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()
            return R()

    monkeypatch.setattr(router_mod, "LLMGateway", _DummyGW)

    r = LLMRouter(db=db)
    resp = r.complete("kb_agent", "sys", [{"role": "user", "content": "hi"}])
    assert resp.text == "ok"


def test_get_provider_settings_returns_llm_api_key_only():
    """get_provider_settings reads llm_api_key and ignores anthropic_api_key."""
    db = _db_with_settings(
        llm_provider="anthropic",
        llm_api_key="new-key",
        anthropic_api_key="old-key",
    )
    r = LLMRouter(db=db)
    s = r.get_provider_settings("anthropic")
    assert s["api_key"] == "new-key"


def test_test_llm_route_returns_error_when_llm_api_key_missing(monkeypatch):
    """app.test_llm returns ok=False with clear message when llm_api_key is empty."""
    import app

    called = {}

    def fake_get_setting(key, default="", db=None):
        return {
            "llm_provider": "anthropic",
            "llm_api_key": "",          # empty — should trigger error
            "llm_base_url": "",
        }.get(key, default)

    monkeypatch.setattr(app, "get_setting", fake_get_setting)

    with app.app.test_request_context(
        "/api/test-llm",
        method="POST",
        json={},
        content_type="application/json",
    ):
        from flask import g
        g._database = None  # prevent real DB lookup
        # Patch get_db to avoid DB connection
        monkeypatch.setattr(app, "get_db", lambda: type("FakeDB", (), {})())
        resp = app.test_llm()
        data = resp.get_json()

    assert data["ok"] is False
    assert "No API key" in data["message"] or "not set" in data["message"].lower()
