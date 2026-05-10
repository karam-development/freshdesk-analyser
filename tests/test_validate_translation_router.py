"""Tests for PR 33 — validate_translation routed through LLMRouter.

Patch strategy (matches the pattern used in test_main_generation_behaviour.py):
- complete_main_llm is imported lazily inside validate_translation, so patch the
  source:  patch("ai.main_llm.complete_main_llm", ...)
- call_anthropic_with_retry is defined in app.py, so patch via the module:
  monkeypatch.setattr(app_module, "call_anthropic_with_retry", ...)

Tests cover:
- Function signature includes db=None
- db provided → calls complete_main_llm (router path), not legacy Anthropic
- db provided + router ok → applies router-returned fixes
- db provided + router ok=False → returns corrected text unchanged (non-blocking)
- db provided + router exception → returns corrected text unchanged (non-blocking)
- db provided → never calls call_anthropic_with_retry (no silent fallback)
- db=None → legacy Anthropic path available (backward compatibility)
- Short drafts (<= 500 words) skip API entirely (both paths)
- Term-level fixes always applied regardless of path
- Both call sites in app.py pass db=db
- No "INTENTIONALLY DEFERRED" wording in app.py or production docs
- Prompt content preserved (no prompt changes)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from app import validate_translation


# ── Helpers ────────────────────────────────────────────────────────────────────

APP_SRC = Path("app.py").read_text(encoding="utf-8")

_SHORT_FR = "Bonjour. Ceci est un court message."          # << 500 words — skips API
_LONG_FR = "La société " + ("rapport annuel annuellement " * 200)  # > 500 words (3*200+2=602)

_GOOD_EN = "Hello. This is a short message."
_GOOD_EN_LONG = "The company " + ("annual report annually " * 200)

_ROUTER_OK = {
    "text": '{"issues_found": false, "fixes": []}',
    "provider": "openai", "model": "gpt-4o",
    "input_tokens": 100, "output_tokens": 20,
    "ok": True, "error": "",
}
_ROUTER_FAIL = {
    "text": "", "provider": "", "model": "",
    "input_tokens": 0, "output_tokens": 0,
    "ok": False, "error": "LLMRouter: api_key missing",
}


def _fake_db():
    return MagicMock(name="db")


def _noop_legacy(*args, **kwargs):
    """Stand-in for call_anthropic_with_retry that does nothing."""
    raise AssertionError("Legacy path must not be called when db is provided")


def _ok_legacy_resp():
    resp = MagicMock()
    resp.content = [MagicMock(text='{"issues_found": false, "fixes": []}')]
    return resp


# ── 1. Signature includes db=None ─────────────────────────────────────────────

def test_validate_translation_signature_has_db_param():
    import inspect
    sig = inspect.signature(validate_translation)
    assert "db" in sig.parameters


def test_validate_translation_db_defaults_to_none():
    import inspect
    sig = inspect.signature(validate_translation)
    assert sig.parameters["db"].default is None


def test_validate_translation_source_has_db_param():
    func_pos = APP_SRC.find("def validate_translation(")
    line_end = APP_SRC.find(":", func_pos)
    signature = APP_SRC[func_pos:line_end]
    assert "db" in signature


# ── 2. db provided → calls complete_main_llm ─────────────────────────────────

def test_db_provided_calls_complete_main_llm(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("legacy must not be called")))
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK) as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    mock_router.assert_called_once()


def test_db_provided_calls_complete_main_llm_with_draft_response_agent(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK) as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    args = mock_router.call_args[0]
    # agent_name is the second positional argument
    assert args[1] == "draft_response_agent"


def test_db_provided_calls_complete_main_llm_with_correct_db(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK) as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    args = mock_router.call_args[0]
    assert args[0] is db


def test_db_provided_passes_max_tokens_2500(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK) as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    kwargs = mock_router.call_args[1]
    assert kwargs.get("max_tokens") == 2500


def test_db_provided_does_not_call_legacy(monkeypatch):
    db = _fake_db()
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK):
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert called == [], "call_anthropic_with_retry must not be called when db is provided"


# ── 3. db provided + router ok → applies fixes ───────────────────────────────

def test_db_provided_router_ok_applies_ai_fixes(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    fix_response = {
        **_ROUTER_OK,
        "text": json.dumps({
            "issues_found": True,
            "fixes": [{"original": "Management Board", "corrected": "Board of Managers"}],
        }),
    }
    en_with_wrong_term = _GOOD_EN_LONG + " The Management Board approved the report."
    with patch("ai.main_llm.complete_main_llm", return_value=fix_response):
        result = validate_translation(_LONG_FR, en_with_wrong_term, "key", db=db)
    assert "Board of Managers" in result


def test_db_provided_router_ok_no_issues_returns_input(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_OK):
        result = validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert result == _GOOD_EN_LONG


# ── 4. db provided + router ok=False → non-blocking ──────────────────────────

def test_db_provided_router_fail_does_not_crash(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_FAIL):
        try:
            result = validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
        except Exception as e:
            pytest.fail(f"validate_translation raised on router failure: {e}")


def test_db_provided_router_fail_returns_nonempty_text(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_FAIL):
        result = validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert result  # non-empty — original EN preserved


def test_db_provided_router_fail_no_legacy_fallback(monkeypatch):
    db = _fake_db()
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_FAIL):
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert called == [], "must not fall back to legacy when router fails with db provided"


def test_db_provided_router_fail_returns_original_en(monkeypatch):
    """Router fail → returns corrected (term-fixes applied, no AI fixes)."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    original_en = _GOOD_EN_LONG
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_FAIL):
        result = validate_translation(_LONG_FR, original_en, "key", db=db)
    # Must not be empty and must not be worse than the input
    assert len(result) > 0
    assert result != ""


# ── 5. db provided + router exception → non-blocking ─────────────────────────

def test_db_provided_router_exception_does_not_crash(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", side_effect=RuntimeError("network error")):
        try:
            result = validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
        except Exception as e:
            pytest.fail(f"validate_translation raised on router exception: {e}")


def test_db_provided_router_exception_returns_nonempty(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", _noop_legacy)
    with patch("ai.main_llm.complete_main_llm", side_effect=RuntimeError("network error")):
        result = validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert result


def test_db_provided_router_exception_no_legacy_fallback(monkeypatch):
    db = _fake_db()
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    with patch("ai.main_llm.complete_main_llm", side_effect=RuntimeError("network error")):
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "key", db=db)
    assert called == [], "must not fall back to legacy on router exception"


# ── 6. db=None → legacy path available ───────────────────────────────────────

def test_db_none_long_draft_calls_legacy(monkeypatch):
    called = []

    def fake_legacy(client, *args, **kwargs):
        called.append(1)
        return _ok_legacy_resp()

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, "sk-test-key", db=None)
    assert called, "legacy call_anthropic_with_retry must be called when db=None"
    mock_router.assert_not_called()


def test_db_none_short_draft_no_api_call(monkeypatch):
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        validate_translation(_SHORT_FR, _GOOD_EN, "sk-test-key", db=None)
    assert called == [], "short draft must not call legacy"
    mock_router.assert_not_called()


def test_db_none_no_key_no_api_call(monkeypatch):
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        validate_translation(_LONG_FR, _GOOD_EN_LONG, anthropic_key="", db=None)
    assert called == [], "no key → no legacy call"
    mock_router.assert_not_called()


# ── 7. Short drafts skip API entirely ────────────────────────────────────────

def test_short_draft_skips_router():
    db = _fake_db()
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        validate_translation(_SHORT_FR, _GOOD_EN, "key", db=db)
    mock_router.assert_not_called()


def test_short_draft_returns_input_unchanged():
    result = validate_translation(_SHORT_FR, _GOOD_EN, "key", db=_fake_db())
    assert result == _GOOD_EN


# ── 8. Term fixes always applied (Step 1, no API needed) ──────────────────────

def test_term_fix_applied_without_any_api_call():
    """Step 1 term fixes run even for short drafts — no API needed."""
    fr = "La société utilise un Gérant Unique pour la gouvernance."
    en = "The company uses a Solo Manager for governance."
    result = validate_translation(fr, en, "", db=None)
    assert "Sole Manager" in result
    assert "Solo Manager" not in result


def test_term_fix_applied_with_db_short_draft():
    """Step 1 term fixes run even when db is provided but draft is short."""
    fr = "La société utilise un Conseil de Gérance."
    en = "The company uses a Management Board."
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        result = validate_translation(fr, en, "", db=_fake_db())
    mock_router.assert_not_called()  # short draft — no router call
    assert "Board of Managers" in result


# ── 9. No legacy fallback when db provided (source check) ─────────────────────

def test_source_router_block_guards_legacy_path():
    """Source check: legacy call_anthropic_with_retry must be inside elif, not if."""
    func_pos = APP_SRC.find("def validate_translation(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]

    router_pos = body.find("db is not None")
    legacy_pos = body.find("call_anthropic_with_retry")
    assert router_pos != -1, "Router path (db is not None) not found"
    assert legacy_pos != -1, "Legacy path (call_anthropic_with_retry) not found"
    # Legacy must appear AFTER the router block
    assert legacy_pos > router_pos
    # The path to legacy must be guarded by elif (not reachable when db is provided)
    between = body[router_pos:legacy_pos]
    assert "elif" in between, "Legacy path must be in an 'elif' branch"


# ── 10. Call sites pass db=db ─────────────────────────────────────────────────

def test_generate_drafts_validate_translation_passes_db():
    pos_route = APP_SRC.find('@app.route("/ticket/<int:ticket_id>/generate-drafts"')
    assert pos_route != -1
    pos_call = APP_SRC.find("validate_translation(", pos_route)
    assert pos_call > pos_route
    window = APP_SRC[pos_call:pos_call + 200]
    assert "db=db" in window, f"Missing db=db in generate_drafts call: {window!r}"


def test_regenerate_draft_pm_validate_translation_passes_db():
    pos_route = APP_SRC.find('@app.route("/ticket/<int:ticket_id>/regenerate-draft-pm"')
    assert pos_route != -1
    pos_call = APP_SRC.find("validate_translation(", pos_route)
    assert pos_call > pos_route
    window = APP_SRC[pos_call:pos_call + 200]
    assert "db=db" in window, f"Missing db=db in regenerate_draft_pm call: {window!r}"


# ── 11. No stale "INTENTIONALLY DEFERRED" wording ────────────────────────────

def test_no_intentionally_deferred_in_validate_translation_docstring():
    func_pos = APP_SRC.find("def validate_translation(")
    doc_window = APP_SRC[func_pos:func_pos + 1200]
    assert "INTENTIONALLY DEFERRED" not in doc_window


def test_team_demo_guide_no_longer_says_validate_translation_deferred():
    guide = Path("docs/TEAM_DEMO_GUIDE.md").read_text(encoding="utf-8")
    assert "validate_translation is not routed" not in guide


def test_production_checklist_no_validate_translation_deferred_entry():
    checklist = Path("docs/PRODUCTION_CHECKLIST.md").read_text(encoding="utf-8")
    assert "validate_translation" not in checklist or \
        "deferred to a future PR" not in checklist


# ── 12. Router path documented in docstring ───────────────────────────────────

def test_docstring_documents_llmrouter_when_db_provided():
    func_pos = APP_SRC.find("def validate_translation(")
    doc_window = APP_SRC[func_pos:func_pos + 1200]
    assert "LLMRouter" in doc_window or "complete_main_llm" in doc_window


def test_docstring_documents_db_none_legacy_compat():
    func_pos = APP_SRC.find("def validate_translation(")
    doc_window = APP_SRC[func_pos:func_pos + 1200]
    assert "db=None" in doc_window or "db is None" in doc_window or "backward compat" in doc_window.lower()


def test_docstring_documents_non_blocking_failure():
    func_pos = APP_SRC.find("def validate_translation(")
    doc_window = APP_SRC[func_pos:func_pos + 1200]
    lower = doc_window.lower()
    assert "non-blocking" in lower or ("failure" in lower and "blocking" not in lower.replace("non-blocking", ""))


# ── 13. Prompt content preserved (no prompt changes) ─────────────────────────

def test_system_prompt_key_legal_terms_preserved():
    func_pos = APP_SRC.find("def validate_translation(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "Conseil de Gérance" in body
    assert "Board of Managers" in body
    assert "issues_found" in body
    assert "fixes" in body


def test_length_threshold_preserved():
    func_pos = APP_SRC.find("def validate_translation(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "> 500" in body


def test_json_parse_logic_preserved():
    """JSON parsing block must still handle markdown code fences."""
    func_pos = APP_SRC.find("def validate_translation(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "startswith" in body and '```' in body


# ── 14. Acceptance scenario ───────────────────────────────────────────────────

def test_acceptance_router_validates_and_applies_fix(monkeypatch):
    """Full acceptance: long draft + db → router called, AI fix applied."""
    db = _fake_db()
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    fix_resp = {
        **_ROUTER_OK,
        "text": json.dumps({
            "issues_found": True,
            "fixes": [{"original": "Solo Manager", "corrected": "Sole Manager"}],
        }),
    }
    en_input = _GOOD_EN_LONG + " The Solo Manager approved it."
    with patch("ai.main_llm.complete_main_llm", return_value=fix_resp) as mock_router:
        result = validate_translation(_LONG_FR, en_input, "key", db=db)
    mock_router.assert_called_once()
    assert called == [], "legacy must not be called"
    assert "Sole Manager" in result
    assert "Solo Manager" not in result


def test_acceptance_router_failure_preserves_en_draft(monkeypatch):
    """Full acceptance: router fails → original EN draft returned, no crash."""
    db = _fake_db()
    called = []
    monkeypatch.setattr(app_module, "call_anthropic_with_retry",
                        lambda *a, **k: called.append(1))
    original_en = _GOOD_EN_LONG
    with patch("ai.main_llm.complete_main_llm", return_value=_ROUTER_FAIL):
        result = validate_translation(_LONG_FR, original_en, "key", db=db)
    assert result == original_en
    assert called == [], "legacy must not be called"
