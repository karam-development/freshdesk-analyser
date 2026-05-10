"""Behavioural tests for PR 30 (revised) — main generation paths.

Verifies:
1. Router failure with db provided does NOT silently call legacy text path.
2. db=None still uses legacy path (backward compat).
3. Vision/screenshot path always uses legacy path regardless of db.
4. Existing draft is preserved on router failure (analyze_and_draft_ai returns error dict).
5. Missing llm_api_key (router returns ok=False) gives clear error.
6. main_analysis_agent max_tokens is NOT hard-coded to 1500.
7. draft_response_agent uses 4000 for normal drafts (not 2000).
8. prd_agent uses 10000.

All external I/O (LLMRouter, Anthropic client, screenshots) is mocked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module


# ── Shared mock builders ───────────────────────────────────────────────────────


def _ok_router_result(text="router text"):
    return {
        "text": text, "provider": "anthropic", "model": "claude-sonnet-4-5",
        "input_tokens": 10, "output_tokens": 20, "ok": True, "error": "",
    }


def _fail_router_result(error="No API key configured for anthropic"):
    return {
        "text": "", "provider": "", "model": "",
        "input_tokens": 0, "output_tokens": 0, "ok": False, "error": error,
    }


def _mock_legacy_resp(text="legacy text"):
    resp = MagicMock()
    resp.content = [MagicMock()]
    resp.content[0].text = text
    return resp


def _fake_db():
    return MagicMock()


# ── analyze_and_draft_ai ───────────────────────────────────────────────────────

_ANALYSIS_VALID_JSON = '{"classification":"bug","confidence":80,"needs_review":false,"summary":"s","analysis":"a","risk_level":"low","draft_response":"","template_name":"T","workflow_name":"W"}'


def test_analyze_uses_router_when_db_provided(monkeypatch):
    """When db is provided, complete_main_llm is called and legacy is NOT."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp(_ANALYSIS_VALID_JSON)

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm", return_value=_ok_router_result(_ANALYSIS_VALID_JSON)) as mock_router:
        result = app_module.analyze_and_draft_ai("thread", "key", db=db)

    mock_router.assert_called_once()
    assert not legacy_called, "Legacy path must NOT be called when db is provided"


def test_analyze_router_failure_returns_error_dict_not_legacy(monkeypatch):
    """Router failure with db provided → error dict returned, legacy NOT called."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp(_ANALYSIS_VALID_JSON)

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        result = app_module.analyze_and_draft_ai("thread", "key", db=db)

    assert not legacy_called, "Legacy path must NOT be called on router failure when db provided"
    assert result["needs_review"] is True
    assert "ROUTER ERROR" in result["analysis"] or "error" in result["analysis"].lower()


def test_analyze_router_failure_preserves_existing_draft_field(monkeypatch):
    """Error dict must include draft_response='' so caller never receives partial state."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        result = app_module.analyze_and_draft_ai("thread", "key", db=db)

    assert "draft_response" in result
    assert result["draft_response"] == ""  # must not overwrite existing draft with garbage


def test_analyze_db_none_uses_legacy_not_router(monkeypatch):
    """db=None must use legacy call_anthropic_with_retry, not router."""
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp(_ANALYSIS_VALID_JSON)

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.analyze_and_draft_ai("thread", "key", db=None)

    assert legacy_called, "Legacy path must be called when db is None"
    mock_router.assert_not_called()


def test_analyze_main_analysis_agent_max_tokens_not_1500():
    """main_analysis_agent call must not force max_tokens=1500."""
    src = Path("app.py").read_text(encoding="utf-8")
    # Find the complete_main_llm call for main_analysis_agent
    idx = src.find('"main_analysis_agent"')
    assert idx != -1
    # Grab 300 chars around the call
    window = src[max(0, idx - 50):idx + 300]
    assert "max_tokens=1500" not in window, (
        "main_analysis_agent must not be capped at 1500 tokens"
    )


# ── generate_draft_response ────────────────────────────────────────────────────


def test_draft_uses_router_when_db_provided_no_screenshots(monkeypatch):
    """Text-only + db provided → router called, legacy NOT called."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy draft")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm", return_value=_ok_router_result("router draft")) as mock_router:
        result = app_module.generate_draft_response("thread", "key", db=db, ticket_id=1)

    mock_router.assert_called_once()
    assert not legacy_called
    assert result == "router draft"


def test_draft_router_failure_raises_not_calls_legacy(monkeypatch):
    """Router failure with db provided → RuntimeError raised, legacy NOT called."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy draft")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        with pytest.raises(RuntimeError, match="(?i)draft generation failed|LLM provider"):
            app_module.generate_draft_response("thread", "key", db=db, ticket_id=1)

    assert not legacy_called, "Legacy must NOT be called after router failure"


def test_draft_db_none_uses_legacy(monkeypatch):
    """db=None → legacy path used, router NOT called."""
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy draft")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_draft_response("thread", "key", db=None, ticket_id=1)

    assert legacy_called
    mock_router.assert_not_called()


def test_draft_vision_path_always_uses_legacy(monkeypatch):
    """Screenshot content → legacy always, even when db is provided."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy draft")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    # Return a non-empty screenshot list
    monkeypatch.setattr(
        app_module, "load_screenshots_for_ai",
        lambda tid: [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}],
    )

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_draft_response("thread", "key", db=db, ticket_id=1)

    assert legacy_called, "Legacy must be called for vision/screenshot path"
    mock_router.assert_not_called()


def test_draft_normal_max_tokens_is_4000():
    """Normal draft (not force_simple) must use 4000 tokens, not 2000."""
    src = Path("app.py").read_text(encoding="utf-8")
    func_pos = src.find("def generate_draft_response(")
    next_func = src.find("\ndef ", func_pos + 1)
    body = src[func_pos:next_func]
    # The ternary is: 600 if force_simple else 4000
    # Check that 4000 appears (as the non-simple limit) and 2000 does NOT
    assert "4000" in body, (
        "draft_response_agent must use 4000 tokens for normal drafts"
    )
    assert "else 2000" not in body and "max_tokens=2000" not in body, (
        "Old 2000-token limit must be removed from generate_draft_response"
    )


# ── translate_draft ────────────────────────────────────────────────────────────


def test_translate_uses_router_when_db_provided(monkeypatch):
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("traduit")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm", return_value=_ok_router_result("traduit")) as mock_router:
        result = app_module.translate_draft("hello", "en", "fr", "key", db=db)

    mock_router.assert_called_once()
    assert not legacy_called
    assert result == "traduit"


def test_translate_router_failure_raises_not_calls_legacy(monkeypatch):
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        with pytest.raises(RuntimeError, match="(?i)translation failed|LLM provider"):
            app_module.translate_draft("hello", "en", "fr", "key", db=db)

    assert not legacy_called


def test_translate_db_none_uses_legacy(monkeypatch):
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("traduit")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.translate_draft("hello", "en", "fr", "key", db=None)

    assert legacy_called
    mock_router.assert_not_called()


def test_translate_empty_input_returns_immediately():
    """Empty/whitespace text must return without calling router or legacy."""
    with patch("ai.main_llm.complete_main_llm") as mock_router:
        result = app_module.translate_draft("", "en", "fr", "key", db=_fake_db())
    mock_router.assert_not_called()
    assert result == ""


# ── generate_prd_analysis ──────────────────────────────────────────────────────


def test_prd_uses_router_when_db_provided_no_screenshots(monkeypatch):
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp('{"template_name":"T","workflow":"W"}')

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm",
               return_value=_ok_router_result('{"template_name":"T","workflow":"W"}')) as mock_router:
        app_module.generate_prd_analysis("thread", "key", "fr", db=db, ticket_id=1)

    mock_router.assert_called_once()
    assert not legacy_called


def test_prd_router_failure_raises_not_calls_legacy(monkeypatch):
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp('{"template_name":"T","workflow":"W"}')

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        with pytest.raises(RuntimeError, match="(?i)PRD analysis failed|LLM provider"):
            app_module.generate_prd_analysis("thread", "key", "fr", db=db, ticket_id=1)

    assert not legacy_called


def test_prd_db_none_uses_legacy(monkeypatch):
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp('{"template_name":"T","workflow":"W"}')

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_prd_analysis("thread", "key", "fr", db=None, ticket_id=1)

    assert legacy_called
    mock_router.assert_not_called()


def test_prd_vision_path_always_uses_legacy(monkeypatch):
    """Screenshot content → legacy always, even when db is provided."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp('{"template_name":"T","workflow":"W"}')

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(
        app_module, "load_screenshots_for_ai",
        lambda tid, **kw: [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}],
    )

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_prd_analysis("thread", "key", "fr", db=db, ticket_id=1)

    assert legacy_called, "Legacy must be called for vision/screenshot path"
    mock_router.assert_not_called()


def test_prd_max_tokens_is_10000():
    src = Path("app.py").read_text(encoding="utf-8")
    func_pos = src.find("def generate_prd_analysis(")
    next_func = src.find("\ndef ", func_pos + 1)
    body = src[func_pos:next_func]
    assert "max_tokens=10000" in body


# ── Missing llm_api_key gives clear error via complete_main_llm ───────────────


def test_missing_llm_api_key_analyze_returns_error_dict(monkeypatch):
    """ok=False from complete_main_llm → error dict, no legacy call."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)

    with patch("ai.main_llm.complete_main_llm",
               return_value=_fail_router_result("No API key configured for anthropic")):
        result = app_module.analyze_and_draft_ai("thread", "key", db=db)

    assert result["ok"] is not True if "ok" in result else True  # error dict may not have 'ok'
    assert result["needs_review"] is True
    assert "No API key" in result["analysis"] or "ROUTER ERROR" in result["analysis"]


def test_missing_llm_api_key_draft_raises(monkeypatch):
    """ok=False from complete_main_llm → RuntimeError raised from generate_draft_response."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm",
               return_value=_fail_router_result("No API key configured for anthropic")):
        with pytest.raises(RuntimeError) as exc_info:
            app_module.generate_draft_response("thread", "key", db=db, ticket_id=1)

    assert "No API key" in str(exc_info.value) or "LLM provider" in str(exc_info.value)


def test_missing_llm_api_key_translate_raises(monkeypatch):
    """ok=False → RuntimeError raised from translate_draft."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)

    with patch("ai.main_llm.complete_main_llm",
               return_value=_fail_router_result("No API key configured for anthropic")):
        with pytest.raises(RuntimeError):
            app_module.translate_draft("hello", "en", "fr", "key", db=db)


def test_missing_llm_api_key_prd_raises(monkeypatch):
    """ok=False → RuntimeError raised from generate_prd_analysis."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm",
               return_value=_fail_router_result("No API key configured for anthropic")):
        with pytest.raises(RuntimeError):
            app_module.generate_prd_analysis("thread", "key", "fr", db=db, ticket_id=1)


# ── generate_decline_response ──────────────────────────────────────────────────


def test_decline_uses_router_when_db_provided_no_screenshots(monkeypatch):
    """Text-only + db provided → router called, legacy NOT called."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy decline")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm", return_value=_ok_router_result("router decline")) as mock_router:
        result = app_module.generate_decline_response("thread", "key", db=db, ticket_id=1)

    mock_router.assert_called_once()
    assert not legacy_called
    assert result == "router decline"


def test_decline_router_failure_raises_not_calls_legacy(monkeypatch):
    """Router failure with db provided → RuntimeError, legacy NOT called."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy decline")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm", return_value=_fail_router_result()):
        with pytest.raises(RuntimeError, match="(?i)decline.*failed|LLM provider"):
            app_module.generate_decline_response("thread", "key", db=db, ticket_id=1)

    assert not legacy_called


def test_decline_db_none_uses_legacy(monkeypatch):
    """db=None → legacy path, router NOT called."""
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy decline")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_decline_response("thread", "key", db=None, ticket_id=1)

    assert legacy_called
    mock_router.assert_not_called()


def test_decline_vision_path_always_uses_legacy(monkeypatch):
    """Screenshot content → legacy always, even when db is provided."""
    db = _fake_db()
    legacy_called = []

    def fake_legacy(*args, **kwargs):
        legacy_called.append(True)
        return _mock_legacy_resp("legacy decline")

    monkeypatch.setattr(app_module, "call_anthropic_with_retry", fake_legacy)
    monkeypatch.setattr(
        app_module, "load_screenshots_for_ai",
        lambda tid: [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}],
    )

    with patch("ai.main_llm.complete_main_llm") as mock_router:
        app_module.generate_decline_response("thread", "key", db=db, ticket_id=1)

    assert legacy_called
    mock_router.assert_not_called()


def test_decline_missing_llm_api_key_raises(monkeypatch):
    """ok=False (missing llm_api_key) → RuntimeError from generate_decline_response."""
    db = _fake_db()
    monkeypatch.setattr(app_module, "call_anthropic_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "load_screenshots_for_ai", lambda tid: [])

    with patch("ai.main_llm.complete_main_llm",
               return_value=_fail_router_result("No API key configured for anthropic")):
        with pytest.raises(RuntimeError):
            app_module.generate_decline_response("thread", "key", db=db, ticket_id=1)


# ── validate_translation: intentionally deferred ──────────────────────────────


def test_validate_translation_documented_as_deferred():
    """validate_translation docstring must explicitly document LLMRouter deferral."""
    src = Path("app.py").read_text(encoding="utf-8")
    func_pos = src.find("def validate_translation(")
    assert func_pos != -1
    # Read the docstring (next ~600 chars from the def line)
    doc_window = src[func_pos:func_pos + 800]
    assert "INTENTIONALLY DEFERRED" in doc_window or "intentionally deferred" in doc_window.lower()


def test_validate_translation_api_block_in_try_except():
    """The API call inside validate_translation must be wrapped in try/except."""
    src = Path("app.py").read_text(encoding="utf-8")
    func_pos = src.find("def validate_translation(")
    next_func = src.find("\ndef ", func_pos + 1)
    body = src[func_pos:next_func] if next_func != -1 else src[func_pos:]
    # confirm try/except wraps the API call
    assert "try:" in body
    assert "except Exception" in body


def test_validate_translation_only_fires_for_long_drafts():
    """validate_translation must only call the API for drafts longer than a threshold."""
    src = Path("app.py").read_text(encoding="utf-8")
    func_pos = src.find("def validate_translation(")
    next_func = src.find("\ndef ", func_pos + 1)
    body = src[func_pos:next_func] if next_func != -1 else src[func_pos:]
    # The guard condition must be present
    assert "> 500" in body or "> 300" in body


# ── No unexpected text-only silent fallback ───────────────────────────────────


def test_no_text_only_function_silently_falls_back_to_legacy_when_db_provided():
    """Source check: none of the four routed functions should have a bare
    call_anthropic_with_retry that runs when db is not None and screenshot_blocks is empty."""
    src = Path("app.py").read_text(encoding="utf-8")

    def _body(fn_name):
        pos = src.find(f"def {fn_name}(")
        end = src.find("\ndef ", pos + 1)
        return src[pos:end] if end != -1 else src[pos:]

    for fn in ("analyze_and_draft_ai", "generate_draft_response",
               "translate_draft", "generate_prd_analysis", "generate_decline_response"):
        body = _body(fn)
        # Each function must contain the "db is None" or "backward compat" guard
        # comment/check so legacy calls are explicitly gated
        assert (
            "db is None" in body
            or "db=None" in body
            or "backward compat" in body.lower()
            or "backward compatibility" in body.lower()
        ), f"{fn} missing explicit db=None / backward-compat guard"
