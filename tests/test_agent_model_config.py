import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import seed_agent_model_configs, list_agent_model_configs, get_agent_model_config, update_agent_model_config


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE agent_model_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name TEXT UNIQUE NOT NULL,
        provider TEXT NOT NULL DEFAULT 'anthropic',
        model TEXT NOT NULL,
        temperature REAL DEFAULT 0.0,
        max_tokens INTEGER DEFAULT 2000,
        enabled INTEGER DEFAULT 1,
        fallback_provider TEXT DEFAULT '',
        fallback_model TEXT DEFAULT '',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    return db


def test_seed_defaults():
    db = _db()
    seed_agent_model_configs(db)
    rows = list_agent_model_configs(db)
    assert len(rows) >= 16


def test_update_and_get_config():
    db = _db()
    seed_agent_model_configs(db)
    update_agent_model_config(db, 'qa_agent', {'provider':'openai','model':'gpt-4.1-mini','temperature':0.2,'max_tokens':800,'enabled':1})
    cfg = get_agent_model_config(db, 'qa_agent')
    assert cfg['provider'] == 'openai'
    assert cfg['model'] == 'gpt-4.1-mini'


def test_invalid_payload_errors():
    db = _db()
    seed_agent_model_configs(db)
    try:
        update_agent_model_config(db, 'qa_agent', {'provider':'bad', 'model':'x'})
        assert False
    except ValueError:
        assert True
