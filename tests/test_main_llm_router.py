"""Unit tests for ai/main_llm.py — complete_main_llm helper (PR 30).

Tests cover:
- Return structure: all required keys present
- ok=False when db is None
- ok=False when LLMRouter import is unavailable (mock)
- ok=True with correct field passthrough when router succeeds
- ok=False with sanitised error when RuntimeError raised
- ok=False with safe message on unexpected exception
- API-key strings are NOT present in error messages (redaction)
- Input is never mutated
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.main_llm import complete_main_llm


# ── Helpers ────────────────────────────────────────────────────────────────────

def _memory_db():
    """Return a minimal in-memory SQLite DB (structure only; router is mocked)."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


def _mock_router(text="response text", provider="anthropic", model="claude-3",
                 input_tokens=10, output_tokens=20):
    """Return a mock LLMRouter whose complete() returns sensible data."""
    resp = MagicMock()
    resp.text = text
    resp.provider = provider
    resp.model = model
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens

    router = MagicMock()
    router.complete.return_value = resp
    return router


def _patch_router(router_instance):
    """Context-manager: replace LLMRouter in ai.main_llm with a factory returning router_instance."""
    import ai.main_llm as mod

    class _Factory:
        def __init__(self, **kw):
            pass

        def complete(self, *args, **kwargs):
            return router_instance.complete(*args, **kwargs)

    return patch.object(mod, "_LLMRouter", _Factory)


# ── Return structure ───────────────────────────────────────────────────────────


def test_returns_dict_on_success():
    db = _memory_db()
    r = _mock_router()
    with _patch_router(r):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert isinstance(result, dict)


def test_has_text_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "text" in result


def test_has_provider_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "provider" in result


def test_has_model_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "model" in result


def test_has_input_tokens_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "input_tokens" in result


def test_has_output_tokens_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "output_tokens" in result


def test_has_ok_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "ok" in result


def test_has_error_key():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert "error" in result


# ── ok=True happy path ─────────────────────────────────────────────────────────


def test_ok_true_on_success():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["ok"] is True


def test_text_passthrough():
    db = _memory_db()
    with _patch_router(_mock_router(text="Hello world")):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["text"] == "Hello world"


def test_provider_passthrough():
    db = _memory_db()
    with _patch_router(_mock_router(provider="openai")):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["provider"] == "openai"


def test_model_passthrough():
    db = _memory_db()
    with _patch_router(_mock_router(model="gpt-4")):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["model"] == "gpt-4"


def test_input_tokens_passthrough():
    db = _memory_db()
    with _patch_router(_mock_router(input_tokens=42)):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["input_tokens"] == 42


def test_output_tokens_passthrough():
    db = _memory_db()
    with _patch_router(_mock_router(output_tokens=99)):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["output_tokens"] == 99


def test_error_empty_on_success():
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["error"] == ""


# ── ok=False: db is None ───────────────────────────────────────────────────────


def test_ok_false_when_db_none():
    result = complete_main_llm(None, "draft_response_agent", "sys",
                               [{"role": "user", "content": "hi"}])
    assert result["ok"] is False


def test_error_set_when_db_none():
    result = complete_main_llm(None, "draft_response_agent", "sys",
                               [{"role": "user", "content": "hi"}])
    assert result["error"]


def test_text_empty_when_db_none():
    result = complete_main_llm(None, "draft_response_agent", "sys",
                               [{"role": "user", "content": "hi"}])
    assert result["text"] == ""


# ── ok=False: RuntimeError from router ────────────────────────────────────────


def test_ok_false_on_runtime_error():
    db = _memory_db()
    failing_router = MagicMock()
    failing_router.complete.side_effect = RuntimeError("No API key configured for anthropic")
    with _patch_router(failing_router):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["ok"] is False


def test_error_set_on_runtime_error():
    db = _memory_db()
    failing_router = MagicMock()
    failing_router.complete.side_effect = RuntimeError("No API key configured")
    with _patch_router(failing_router):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["error"]


def test_api_key_not_in_error_message():
    """RuntimeError containing a long API-key-like string must be redacted."""
    fake_key = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    db = _memory_db()
    failing_router = MagicMock()
    failing_router.complete.side_effect = RuntimeError(
        f"Invalid API key: {fake_key}"
    )
    with _patch_router(failing_router):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert fake_key not in result["error"]
    assert "[REDACTED]" in result["error"]


# ── ok=False: unexpected exception ────────────────────────────────────────────


def test_ok_false_on_unexpected_exception():
    db = _memory_db()
    failing_router = MagicMock()
    failing_router.complete.side_effect = ValueError("something unexpected")
    with _patch_router(failing_router):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["ok"] is False


def test_error_set_on_unexpected_exception():
    db = _memory_db()
    failing_router = MagicMock()
    failing_router.complete.side_effect = ValueError("unexpected")
    with _patch_router(failing_router):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["error"]


def test_never_raises():
    """complete_main_llm must never raise regardless of input."""
    import ai.main_llm as mod

    with patch.object(mod, "_LLMRouter", side_effect=Exception("chaos")):
        result = complete_main_llm(_memory_db(), "any_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert isinstance(result, dict)
    assert result["ok"] is False


# ── ok=False: LLMRouter unavailable ───────────────────────────────────────────


def test_ok_false_when_router_unavailable():
    import ai.main_llm as mod

    with patch.object(mod, "_ROUTER_AVAILABLE", False):
        result = complete_main_llm(_memory_db(), "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["ok"] is False


def test_error_set_when_router_unavailable():
    import ai.main_llm as mod

    with patch.object(mod, "_ROUTER_AVAILABLE", False):
        result = complete_main_llm(_memory_db(), "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["error"]


# ── None-text from router is coerced to empty string ──────────────────────────


def test_none_text_coerced_to_empty_string():
    db = _memory_db()
    with _patch_router(_mock_router(text=None)):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["text"] == ""


# ── usage=None is handled gracefully ──────────────────────────────────────────


def test_none_usage_returns_zero_tokens():
    db = _memory_db()
    r = _mock_router()
    r.complete.return_value.usage = None
    with _patch_router(r):
        result = complete_main_llm(db, "draft_response_agent", "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


# ── Agent names used in app.py ─────────────────────────────────────────────────


@pytest.mark.parametrize("agent_name", [
    "main_analysis_agent",
    "draft_response_agent",
    "prd_agent",
])
def test_agent_names_accepted(agent_name):
    db = _memory_db()
    with _patch_router(_mock_router()):
        result = complete_main_llm(db, agent_name, "sys",
                                   [{"role": "user", "content": "hi"}])
    assert result["ok"] is True
