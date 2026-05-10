"""Tests for Semantic RAG Cache status block UI and safety guarantees.

Source-level only — no Flask, no DB, no network.
"""
from __future__ import annotations


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


SETTINGS_HTML = _read("templates/settings.html")
APP_SRC = _read("app.py")


# ── Cache status is visible ───────────────────────────────────────────────────


def test_settings_or_agents_has_semantic_rag_cache_section():
    """Settings page must contain 'Semantic RAG Cache' heading."""
    assert "Semantic RAG Cache" in SETTINGS_HTML


def test_cache_status_block_is_read_only():
    """Cache status block must have read-only label or no edit inputs."""
    assert "read-only" in SETTINGS_HTML


def test_cache_shows_enabled_or_disabled_state():
    """Cache block must indicate whether semantic RAG is on or off."""
    assert "Enabled" in SETTINGS_HTML or "Disabled" in SETTINGS_HTML


def test_cache_shows_record_count_from_template_variable():
    """Cache block must use kb_cache_status.count from the context."""
    assert "kb_cache_status.count" in SETTINGS_HTML


def test_cache_shows_provider():
    """Cache block must display the current embedding provider."""
    assert "semantic_rag_provider" in SETTINGS_HTML


def test_cache_shows_model():
    """Cache block must display the current embedding model."""
    assert "semantic_embedding_model" in SETTINGS_HTML


# ── No destructive cache actions ─────────────────────────────────────────────


def test_no_cache_clear_button_in_settings_html():
    """No 'Clear cache' or 'Delete cache' button must exist in this PR."""
    lower = SETTINGS_HTML.lower()
    assert "clear cache" not in lower
    assert "delete cache" not in lower
    assert "flush cache" not in lower


def test_no_cache_clear_button_in_app_route():
    """app.py must not have a cache-clear route for kb_embedding_cache."""
    assert "DELETE FROM kb_embedding_cache" not in APP_SRC or \
        "clear_embedding_cache" not in APP_SRC


def test_no_embedding_generation_button_in_settings():
    """Settings page must not have a button that triggers embedding generation."""
    lower = SETTINGS_HTML.lower()
    assert "generate embedding" not in lower
    assert "embed all" not in lower
    assert "run embeddings" not in lower


# ── app.py: cache query is safe ───────────────────────────────────────────────


def test_app_cache_query_never_calls_embed_texts_on_settings_page():
    """The settings route must never call embed_texts."""
    settings_route_body = APP_SRC[APP_SRC.find("def settings()"):APP_SRC.find("def kb_add()")]
    assert "embed_texts(" not in settings_route_body


def test_app_cache_query_never_calls_get_or_create_embeddings():
    """The settings route must never call get_or_create_embeddings_for_records."""
    settings_route_body = APP_SRC[APP_SRC.find("def settings()"):APP_SRC.find("def kb_add()")]
    assert "get_or_create_embeddings_for_records(" not in settings_route_body


def test_app_cache_status_handles_missing_table():
    """Cache count query must be wrapped in try/except for missing table safety."""
    # Find the kb_cache_status block
    idx = APP_SRC.find("kb_cache_status")
    assert idx != -1
    surrounding = APP_SRC[max(0, idx - 50):idx + 300]
    assert "try:" in surrounding or "except" in surrounding


def test_app_cache_status_returns_zero_on_failure():
    """Cache status must return count=0 if the table is missing or query fails."""
    assert '"count": 0' in APP_SRC or "'count': 0" in APP_SRC


def test_app_cache_status_marks_available_false_on_failure():
    """Cache status must mark available=False if the query fails."""
    assert '"available": False' in APP_SRC or "'available': False" in APP_SRC


# ── No API calls from cache status block ─────────────────────────────────────


def test_no_external_api_call_in_cache_status_block():
    """Cache status computation must only use SQLite — no HTTP, no OpenAI calls."""
    # Extract the kb_cache_status block from the settings route
    idx_start = APP_SRC.find("kb_cache_status = {")
    if idx_start == -1:
        idx_start = APP_SRC.find('kb_cache_status =')
    assert idx_start != -1
    block = APP_SRC[idx_start:idx_start + 300]
    assert "openai" not in block.lower()
    assert "requests.get" not in block
    assert "requests.post" not in block
    assert "embed_texts" not in block
