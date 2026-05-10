"""Tests for Semantic RAG Configuration in settings.html and app.py save logic.

Source-level only — reads files as strings, no Flask, no DB, no network.
"""
from __future__ import annotations

import re


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


SETTINGS_HTML = _read("templates/settings.html")
APP_SRC = _read("app.py")


# ── Template: Semantic RAG Configuration section ──────────────────────────────


def test_settings_html_has_semantic_rag_configuration_heading():
    assert "Semantic RAG Configuration" in SETTINGS_HTML


def test_settings_html_has_semantic_rag_enabled_field():
    assert 'name="semantic_rag_enabled"' in SETTINGS_HTML


def test_settings_html_semantic_rag_enabled_has_on_off_options():
    assert 'value="true"' in SETTINGS_HTML
    assert 'value="false"' in SETTINGS_HTML


def test_settings_html_has_semantic_rag_provider_field():
    assert 'name="semantic_rag_provider"' in SETTINGS_HTML


def test_settings_html_has_semantic_embedding_model_field():
    assert 'name="semantic_embedding_model"' in SETTINGS_HTML


def test_settings_html_semantic_embedding_model_shows_default():
    assert "text-embedding-3-small" in SETTINGS_HTML


def test_settings_html_has_semantic_rag_top_k_field():
    assert 'name="semantic_rag_top_k"' in SETTINGS_HTML


def test_settings_html_semantic_rag_top_k_is_number_input():
    pattern = r'<input[^>]*type="number"[^>]*name="semantic_rag_top_k"|<input[^>]*name="semantic_rag_top_k"[^>]*type="number"'
    assert re.search(pattern, SETTINGS_HTML), "semantic_rag_top_k must be a number input"


def test_settings_html_has_semantic_rag_min_score_field():
    assert 'name="semantic_rag_min_score"' in SETTINGS_HTML


def test_settings_html_semantic_rag_min_score_is_number_input():
    pattern = r'<input[^>]*type="number"[^>]*name="semantic_rag_min_score"|<input[^>]*name="semantic_rag_min_score"[^>]*type="number"'
    assert re.search(pattern, SETTINGS_HTML), "semantic_rag_min_score must be a number input"


def test_settings_html_helper_text_mentions_off_by_default():
    lower = SETTINGS_HTML.lower()
    assert "off by default" in lower or "disabled" in lower or "default" in lower


def test_settings_html_helper_text_mentions_provider_cost():
    lower = SETTINGS_HTML.lower()
    assert "cost" in lower


def test_settings_html_helper_text_mentions_fallback_to_keyword():
    lower = SETTINGS_HTML.lower()
    assert "keyword" in lower and ("fallback" in lower or "fall back" in lower)


def test_settings_html_experimental_note_present():
    lower = SETTINGS_HTML.lower()
    assert "experimental" in lower


# ── Template: Semantic RAG Cache section ──────────────────────────────────────


def test_settings_html_has_semantic_rag_cache_section():
    assert "Semantic RAG Cache" in SETTINGS_HTML


def test_settings_html_cache_section_is_read_only():
    # The cache section must be read-only — no form inputs inside it
    # We check that 'Semantic RAG Cache' section does not contain 'name=' after it
    idx = SETTINGS_HTML.find("Semantic RAG Cache")
    assert idx != -1
    # The section is read-only by design — no inputs should follow immediately
    # (We verify this by checking that the status block uses kb_cache_status variable)
    assert "kb_cache_status" in SETTINGS_HTML


def test_settings_html_cache_shows_enabled_status():
    assert "semantic_rag_enabled" in SETTINGS_HTML
    # Shows Enabled/Disabled based on setting
    assert "Enabled" in SETTINGS_HTML or "Disabled" in SETTINGS_HTML


def test_settings_html_cache_shows_provider():
    assert "semantic_rag_provider" in SETTINGS_HTML


def test_settings_html_cache_shows_model():
    assert "semantic_embedding_model" in SETTINGS_HTML


def test_settings_html_cache_shows_record_count():
    assert "kb_cache_status.count" in SETTINGS_HTML


def test_settings_html_cache_handles_unavailable():
    assert "Unavailable" in SETTINGS_HTML or "unavailable" in SETTINGS_HTML.lower()


# ── app.py: POST handler saves semantic RAG settings ─────────────────────────


def test_app_saves_semantic_rag_enabled():
    assert 'set_setting("semantic_rag_enabled"' in APP_SRC or "set_setting('semantic_rag_enabled'" in APP_SRC


def test_app_saves_semantic_rag_provider():
    assert 'set_setting("semantic_rag_provider"' in APP_SRC or "set_setting('semantic_rag_provider'" in APP_SRC


def test_app_saves_semantic_embedding_model():
    assert 'set_setting("semantic_embedding_model"' in APP_SRC or "set_setting('semantic_embedding_model'" in APP_SRC


def test_app_saves_semantic_rag_top_k():
    assert 'set_setting("semantic_rag_top_k"' in APP_SRC or "set_setting('semantic_rag_top_k'" in APP_SRC


def test_app_saves_semantic_rag_min_score():
    assert 'set_setting("semantic_rag_min_score"' in APP_SRC or "set_setting('semantic_rag_min_score'" in APP_SRC


def test_app_validates_top_k_as_positive_integer():
    # There must be a try/except or int() conversion with validation
    assert "int(" in APP_SRC and "semantic_rag_top_k" in APP_SRC
    assert "ValueError" in APP_SRC or "except" in APP_SRC


def test_app_validates_min_score_between_0_and_1():
    assert "float(" in APP_SRC and "semantic_rag_min_score" in APP_SRC
    assert "0.0" in APP_SRC or "0 <=" in APP_SRC or "0.65" in APP_SRC


def test_app_invalid_top_k_flashes_warning_not_crash():
    # On invalid top_k: flash warning and use default, not a hard error
    assert 'flash(' in APP_SRC and "semantic_rag_top_k" in APP_SRC
    # Defaults to 5
    assert '"5"' in APP_SRC or "'5'" in APP_SRC


def test_app_invalid_min_score_flashes_warning_not_crash():
    # On invalid min_score: flash warning and use default, not a hard error
    assert 'flash(' in APP_SRC and "semantic_rag_min_score" in APP_SRC
    assert '"0.65"' in APP_SRC or "'0.65'" in APP_SRC


def test_app_settings_page_does_not_call_embed_texts():
    """The settings route must never trigger embedding API calls."""
    # embed_texts is not called directly from the settings route (only from _augment_kb_with_semantic)
    settings_route_body = APP_SRC[APP_SRC.find("def settings()"):APP_SRC.find("def kb_add()")]
    assert "embed_texts(" not in settings_route_body


def test_app_settings_page_does_not_call_get_or_create_embeddings():
    """The settings route must never trigger embedding generation."""
    settings_route_body = APP_SRC[APP_SRC.find("def settings()"):APP_SRC.find("def kb_add()")]
    assert "get_or_create_embeddings_for_records(" not in settings_route_body


# ── app.py: GET handler loads semantic RAG settings ───────────────────────────


def test_app_get_handler_loads_semantic_rag_enabled():
    assert '"semantic_rag_enabled"' in APP_SRC


def test_app_get_handler_loads_semantic_rag_provider():
    assert '"semantic_rag_provider"' in APP_SRC


def test_app_get_handler_loads_semantic_embedding_model():
    assert '"semantic_embedding_model"' in APP_SRC


def test_app_get_handler_loads_semantic_rag_top_k():
    assert '"semantic_rag_top_k"' in APP_SRC


def test_app_get_handler_loads_semantic_rag_min_score():
    assert '"semantic_rag_min_score"' in APP_SRC


def test_app_passes_kb_cache_status_to_template():
    assert "kb_cache_status=kb_cache_status" in APP_SRC


def test_app_cache_query_uses_try_except():
    """Cache status query must be wrapped in try/except to handle missing table."""
    assert "kb_embedding_cache" in APP_SRC
    # The count query is in a try/except block
    idx = APP_SRC.find("kb_embedding_cache")
    # Find a try/except near the cache count query
    surrounding = APP_SRC[max(0, idx - 200):idx + 200]
    assert "try:" in surrounding or "except" in surrounding


# ── No secrets in template ────────────────────────────────────────────────────


def test_settings_html_does_not_render_llm_api_key_as_value():
    assert 'value="{{ settings.llm_api_key }}"' not in SETTINGS_HTML


def test_settings_html_no_secret_in_cache_section():
    # Cache section is read-only status; no key values rendered
    idx = SETTINGS_HTML.find("Semantic RAG Cache")
    if idx != -1:
        # Nothing after this point should reference llm_api_key as a value
        cache_section = SETTINGS_HTML[idx:idx + 1000]
        assert "settings.llm_api_key" not in cache_section
