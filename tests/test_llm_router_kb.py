import sys
from pathlib import Path
import sqlite3
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.llm.router import LLMRouter
import agents


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('''CREATE TABLE agent_model_config (
      agent_name TEXT UNIQUE NOT NULL, provider TEXT NOT NULL DEFAULT 'anthropic', model TEXT NOT NULL,
      temperature REAL DEFAULT 0.0, max_tokens INTEGER DEFAULT 2000, fallback_provider TEXT DEFAULT '', fallback_model TEXT DEFAULT ''
    )''')
    return db


def test_router_config_default_when_missing():
    r = LLMRouter(db=_db())
    cfg = r.get_agent_config('kb_agent')
    assert cfg['provider']
    assert cfg['model']


def test_router_invalid_provider_fails_clearly():
    db = _db()
    db.execute("INSERT INTO agent_model_config(agent_name,provider,model) VALUES ('kb_agent','bad','x')")
    db.commit()
    r = LLMRouter(db=db)
    try:
        r.complete('kb_agent', 'sys', [{'role':'user','content':'hi'}])
        assert False
    except Exception as e:
        assert (
            'Unsupported LLM provider' in str(e)
            or 'LLMRouter failure' in str(e)
            or 'No API key configured' in str(e)
        )


def test_kb_agent_without_router_still_works(monkeypatch):
    monkeypatch.setattr(agents, '_call_with_retry', lambda *a, **k: ('ok', {'input_tokens':1,'output_tokens':1}))
    out, usage = agents.kb_agent(client=object(), ticket_subject='s', ticket_summary='t', full_kb_context='kb')
    assert out == 'ok'
    assert usage['input_tokens'] == 1
