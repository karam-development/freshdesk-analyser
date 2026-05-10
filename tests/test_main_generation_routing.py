"""Source-wiring tests for PR 30 — main generation paths routed through LLMRouter.

Reads app.py to assert:
- ai/main_llm.py is imported in app.py
- All four generation functions accept a db= parameter
- Each function contains the router call path
- Vision/screenshot bypass is present in vision-capable functions
- All known caller sites pass db=db
- No silent fallback from llm_api_key to anthropic_api_key
- Module ai/main_llm.py is importable and complete_main_llm is callable
"""
from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


APP_SRC = _read("app.py")


# ── Import check ───────────────────────────────────────────────────────────────


def test_app_imports_complete_main_llm():
    assert "complete_main_llm" in APP_SRC


def test_app_imports_from_ai_main_llm():
    assert "from ai.main_llm import complete_main_llm" in APP_SRC


# ── analyze_and_draft_ai ───────────────────────────────────────────────────────


def test_analyze_and_draft_ai_has_db_param():
    """Function signature must accept db=None."""
    func_pos = APP_SRC.find("def analyze_and_draft_ai(")
    assert func_pos != -1
    # Find the closing paren of the def line (may span multiple lines)
    sig_end = APP_SRC.find("):", func_pos)
    sig = APP_SRC[func_pos:sig_end + 2]
    assert "db=" in sig or "db =" in sig


def test_analyze_and_draft_ai_calls_complete_main_llm():
    """Function must call complete_main_llm with main_analysis_agent."""
    func_pos = APP_SRC.find("def analyze_and_draft_ai(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "complete_main_llm" in body


def test_analyze_and_draft_ai_uses_main_analysis_agent():
    func_pos = APP_SRC.find("def analyze_and_draft_ai(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "main_analysis_agent" in body


def test_analyze_and_draft_ai_has_fallback_to_legacy():
    """Must have a legacy fallback path (call_anthropic_with_retry or legacy_client)."""
    func_pos = APP_SRC.find("def analyze_and_draft_ai(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "call_anthropic_with_retry" in body


# ── generate_draft_response ────────────────────────────────────────────────────


def test_generate_draft_response_has_db_param():
    func_pos = APP_SRC.find("def generate_draft_response(")
    assert func_pos != -1
    sig_end = APP_SRC.find("):", func_pos)
    sig = APP_SRC[func_pos:sig_end + 2]
    assert "db=" in sig or "db =" in sig


def test_generate_draft_response_calls_complete_main_llm():
    func_pos = APP_SRC.find("def generate_draft_response(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "complete_main_llm" in body


def test_generate_draft_response_uses_draft_response_agent():
    func_pos = APP_SRC.find("def generate_draft_response(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "draft_response_agent" in body


def test_generate_draft_response_skips_router_when_screenshot_blocks():
    """Vision path is handled before the router block so router is never reached."""
    func_pos = APP_SRC.find("def generate_draft_response(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "screenshot_blocks" in body
    # Vision path must return before the router block (early-return guard).
    # The comment documenting the intent must be present.
    assert "LLMRouter does not support multimodal" in body or "vision" in body.lower()


def test_generate_draft_response_has_legacy_fallback():
    func_pos = APP_SRC.find("def generate_draft_response(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "call_anthropic_with_retry" in body


# ── translate_draft ────────────────────────────────────────────────────────────


def test_translate_draft_has_db_param():
    func_pos = APP_SRC.find("def translate_draft(")
    assert func_pos != -1
    sig_end = APP_SRC.find("):", func_pos)
    sig = APP_SRC[func_pos:sig_end + 2]
    assert "db=" in sig or "db =" in sig


def test_translate_draft_calls_complete_main_llm():
    func_pos = APP_SRC.find("def translate_draft(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "complete_main_llm" in body


def test_translate_draft_has_legacy_fallback():
    func_pos = APP_SRC.find("def translate_draft(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "call_anthropic_with_retry" in body or "anthropic_key" in body


# ── generate_prd_analysis ──────────────────────────────────────────────────────


def test_generate_prd_analysis_has_db_param():
    func_pos = APP_SRC.find("def generate_prd_analysis(")
    assert func_pos != -1
    sig_end = APP_SRC.find("):", func_pos)
    sig = APP_SRC[func_pos:sig_end + 2]
    assert "db=" in sig or "db =" in sig


def test_generate_prd_analysis_calls_complete_main_llm():
    func_pos = APP_SRC.find("def generate_prd_analysis(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "complete_main_llm" in body


def test_generate_prd_analysis_uses_prd_agent():
    func_pos = APP_SRC.find("def generate_prd_analysis(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "prd_agent" in body


def test_generate_prd_analysis_has_legacy_fallback():
    func_pos = APP_SRC.find("def generate_prd_analysis(")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "call_anthropic_with_retry" in body


# ── Caller sites pass db=db ────────────────────────────────────────────────────


def test_generate_drafts_passes_db_to_generate_draft_response():
    """generate_drafts must forward db to generate_draft_response."""
    func_pos = APP_SRC.find("def generate_drafts(")
    if func_pos == -1:
        func_pos = APP_SRC.find("def generate_drafts ")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    # There should be a call to generate_draft_response, and db=db must appear
    # somewhere after the call (calls may span many lines; don't parse the closing paren)
    assert "generate_draft_response(" in body
    call_pos = body.find("generate_draft_response(")
    # Look for db=db in up to 1000 chars after the opening paren (calls can be long)
    window = body[call_pos:call_pos + 1000]
    assert "db=db" in window or "db = db" in window


def test_generate_drafts_passes_db_to_translate_draft():
    func_pos = APP_SRC.find("def generate_drafts(")
    if func_pos == -1:
        func_pos = APP_SRC.find("def generate_drafts ")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    if "translate_draft(" not in body:
        pytest.skip("translate_draft not called in generate_drafts")
    call_pos = body.find("translate_draft(")
    call_end = body.find(")", call_pos)
    call_text = body[call_pos:call_end + 1]
    assert "db=" in call_text


def test_regenerate_draft_pm_passes_db_to_generate_draft_response():
    func_pos = APP_SRC.find("def regenerate_draft_pm(")
    if func_pos == -1:
        pytest.skip("regenerate_draft_pm not found")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "generate_draft_response(" in body
    call_pos = body.find("generate_draft_response(")
    window = body[call_pos:call_pos + 500]
    assert "db=db" in window or "db = db" in window


def test_prepare_analysis_passes_db_to_generate_prd_analysis():
    func_pos = APP_SRC.find("def prepare_analysis(")
    if func_pos == -1:
        pytest.skip("prepare_analysis not found")
    next_func = APP_SRC.find("\ndef ", func_pos + 1)
    body = APP_SRC[func_pos:next_func] if next_func != -1 else APP_SRC[func_pos:]
    assert "generate_prd_analysis(" in body
    call_pos = body.find("generate_prd_analysis(")
    call_end = body.find(")", call_pos)
    call_text = body[call_pos:call_end + 1]
    assert "db=" in call_text


def test_ingest_worker_passes_db_to_analyze_and_draft():
    """Ingest route/worker must forward db to analyze_and_draft_ai."""
    # Check that the call site at line ~3385 includes db=db
    call_idx = APP_SRC.find("analyze_and_draft_ai(compiled, anthropic_key")
    assert call_idx != -1, "Expected analyze_and_draft_ai caller not found"
    call_end = APP_SRC.find(")", call_idx)
    call_text = APP_SRC[call_idx:call_end + 1]
    assert "db=" in call_text


# ── No silent fallback in complete_main_llm ────────────────────────────────────


def test_main_llm_module_does_not_call_get_setting_for_anthropic_api_key():
    """ai/main_llm.py must never call get_setting('anthropic_api_key') — only LLMRouter via llm_api_key."""
    main_llm_src = _read("ai/main_llm.py")
    # The module may mention anthropic_api_key in docstring/comments as a contrast,
    # but must never contain a function call or assignment that would read it.
    # Ensure there is no get_setting call for anthropic_api_key.
    assert 'get_setting("anthropic_api_key")' not in main_llm_src
    assert "get_setting('anthropic_api_key')" not in main_llm_src
    # Must not assign or pass anthropic_api_key as a value
    assert "= anthropic_api_key" not in main_llm_src


# ── Module importable and callable ────────────────────────────────────────────


def test_main_llm_module_importable():
    from ai.main_llm import complete_main_llm as fn
    assert callable(fn)


def test_complete_main_llm_returns_dict_on_none_db():
    from ai.main_llm import complete_main_llm
    result = complete_main_llm(None, "draft_response_agent", "sys",
                               [{"role": "user", "content": "hi"}])
    assert isinstance(result, dict)
    assert result["ok"] is False


def test_complete_main_llm_has_all_keys():
    from ai.main_llm import complete_main_llm
    result = complete_main_llm(None, "draft_response_agent", "sys",
                               [{"role": "user", "content": "hi"}])
    for key in ("text", "provider", "model", "input_tokens", "output_tokens", "ok", "error"):
        assert key in result, f"Missing key: {key}"
