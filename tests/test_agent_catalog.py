"""Tests for ai/agent_catalog.py.

Source-level unit tests — no Flask, no DB, no network.
"""
from __future__ import annotations

from ai.agent_catalog import get_agent_purpose_catalog, build_agent_catalog_rows


# ── Catalog content tests ─────────────────────────────────────────────────────


def test_catalog_contains_kb_agent():
    catalog = get_agent_purpose_catalog()
    assert "kb_agent" in catalog


def test_catalog_contains_code_agent():
    assert "code_agent" in get_agent_purpose_catalog()


def test_catalog_contains_research_agent():
    assert "research_agent" in get_agent_purpose_catalog()


def test_catalog_contains_qa_agent():
    assert "qa_agent" in get_agent_purpose_catalog()


def test_catalog_contains_learning_agent():
    assert "learning_agent" in get_agent_purpose_catalog()


def test_each_catalog_entry_has_purpose():
    catalog = get_agent_purpose_catalog()
    for name, entry in catalog.items():
        assert "purpose" in entry, f"{name} missing purpose"
        assert entry["purpose"], f"{name} purpose is empty"


def test_each_catalog_entry_has_used_in():
    catalog = get_agent_purpose_catalog()
    for name, entry in catalog.items():
        assert "used_in" in entry, f"{name} missing used_in"
        assert entry["used_in"], f"{name} used_in is empty"


# ── build_agent_catalog_rows tests ───────────────────────────────────────────


def _make_row(agent_name, provider="anthropic", model="claude-haiku", max_tokens=2000, enabled=True):
    """Return a plain dict mimicking a sqlite3.Row."""
    return {
        "agent_name": agent_name,
        "provider": provider,
        "model": model,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "enabled": enabled,
    }


def test_build_rows_returns_list():
    rows = build_agent_catalog_rows([_make_row("kb_agent")])
    assert isinstance(rows, list)


def test_build_rows_known_agent_has_purpose():
    rows = build_agent_catalog_rows([_make_row("kb_agent")])
    assert rows
    assert rows[0]["purpose"] != "Purpose not documented yet"


def test_build_rows_unknown_agent_shows_fallback():
    rows = build_agent_catalog_rows([_make_row("mystery_agent")])
    assert rows
    assert rows[0]["purpose"] == "Purpose not documented yet"


def test_build_rows_merges_provider_and_model():
    rows = build_agent_catalog_rows([_make_row("qa_agent", provider="openai", model="gpt-4o")])
    assert rows[0]["provider"] == "openai"
    assert rows[0]["model"] == "gpt-4o"


def test_build_rows_empty_input_returns_empty():
    assert build_agent_catalog_rows([]) == []


def test_build_rows_none_input_returns_empty():
    assert build_agent_catalog_rows(None) == []  # type: ignore[arg-type]


def test_build_rows_never_raises():
    # Garbage input must not raise
    result = build_agent_catalog_rows([{"bad": "data"}, None, 42])  # type: ignore[list-item]
    assert isinstance(result, list)
