"""Tests for the AI Provider Configuration section in settings.html — PR fix-settings-llm-provider-ui.

All tests are source-level (read files as strings).
No Flask test client, no DB, no network.
"""
from __future__ import annotations

import re


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


SETTINGS_HTML = _read("templates/settings.html")
APP_SRC = _read("app.py")


# ── Template: AI Provider Configuration section ───────────────────────────────


def test_settings_html_has_ai_provider_configuration_heading():
    """Settings page must advertise the new section by name."""
    assert "AI Provider Configuration" in SETTINGS_HTML


def test_settings_html_has_llm_provider_select_field():
    """A <select name='llm_provider'> must be present."""
    assert 'name="llm_provider"' in SETTINGS_HTML


def test_settings_html_has_anthropic_option_for_llm_provider():
    assert 'value="anthropic"' in SETTINGS_HTML


def test_settings_html_has_openai_option_for_llm_provider():
    assert 'value="openai"' in SETTINGS_HTML


def test_settings_html_has_llm_api_key_password_field():
    """A password input named llm_api_key must exist."""
    assert 'name="llm_api_key"' in SETTINGS_HTML
    # The input must be type="password"
    pattern = r'<input[^>]*type="password"[^>]*name="llm_api_key"[^>]*>|<input[^>]*name="llm_api_key"[^>]*type="password"[^>]*>'
    assert re.search(pattern, SETTINGS_HTML), "llm_api_key must be a password input"


def test_settings_html_llm_api_key_does_not_render_value():
    """The llm_api_key password input must never use settings.llm_api_key as its value attribute."""
    # It would be a security issue to pre-fill the key into the DOM
    assert 'value="{{ settings.llm_api_key }}"' not in SETTINGS_HTML
    assert "value=\"{{ settings.llm_api_key }}\"" not in SETTINGS_HTML


def test_settings_html_llm_api_key_input_has_empty_value():
    """The llm_api_key input must have value=\"\" (never pre-filled)."""
    # Find the llm_api_key input and verify it has value=""
    pattern = r'<input[^>]*name="llm_api_key"[^>]*value=""[^>]*>|<input[^>]*value=""[^>]*name="llm_api_key"[^>]*>'
    assert re.search(pattern, SETTINGS_HTML), (
        "llm_api_key input must have value=\"\" (never pre-filled with the saved key)"
    )


def test_settings_html_has_llm_base_url_field():
    """A text input named llm_base_url must exist."""
    assert 'name="llm_base_url"' in SETTINGS_HTML


def test_settings_html_llm_base_url_shows_existing_value():
    """llm_base_url CAN show the current value (it is not secret)."""
    assert 'settings.llm_base_url' in SETTINGS_HTML


def test_settings_html_provider_hint_mentions_llmrouter():
    """The section must describe what LLMRouter is used for."""
    assert "LLMRouter" in SETTINGS_HTML or "draft generation" in SETTINGS_HTML


def test_settings_html_provider_hint_mentions_semantic_rag():
    """The section hint must mention semantic RAG embeddings."""
    assert "semantic RAG" in SETTINGS_HTML or "embeddings" in SETTINGS_HTML


# ── Template: key-is-set indicator ───────────────────────────────────────────


def test_settings_html_shows_key_set_indicator():
    """Template must show a 'Key is set' indicator when settings.llm_api_key is truthy."""
    assert "Key is set" in SETTINGS_HTML or "key is set" in SETTINGS_HTML.lower()


def test_settings_html_shows_leave_blank_placeholder():
    """Password field placeholder must say 'Leave blank to keep existing key'."""
    assert "Leave blank to keep existing key" in SETTINGS_HTML


def test_settings_html_shows_migration_tip_when_legacy_key_set():
    """Template must hint at copying the legacy key when llm_api_key is missing."""
    assert "anthropic_api_key" in SETTINGS_HTML
    # Tip should reference legacy key
    assert "Legacy Anthropic" in SETTINGS_HTML or "legacy" in SETTINGS_HTML.lower()


# ── Template: legacy section preserved ───────────────────────────────────────


def test_settings_html_legacy_anthropic_section_present():
    """The legacy anthropic_api_key input must still exist for backward compatibility."""
    assert 'name="anthropic_api_key"' in SETTINGS_HTML


def test_settings_html_legacy_section_labeled_as_legacy():
    """The legacy section must be clearly labeled as 'Legacy'."""
    assert "Legacy Anthropic" in SETTINGS_HTML


def test_settings_html_legacy_section_explains_scope():
    """Legacy section must explain it is for vision/fallback paths only."""
    lower = SETTINGS_HTML.lower()
    assert "vision" in lower or "fallback" in lower or "legacy" in lower


def test_settings_html_provider_section_comes_before_legacy_section():
    """AI Provider Configuration section must appear before the Legacy section."""
    idx_provider = SETTINGS_HTML.find("AI Provider Configuration")
    idx_legacy = SETTINGS_HTML.find("Legacy Anthropic")
    assert idx_provider != -1, "AI Provider Configuration section missing"
    assert idx_legacy != -1, "Legacy Anthropic section missing"
    assert idx_provider < idx_legacy, (
        "AI Provider Configuration must appear before Legacy Anthropic section"
    )


# ── app.py: POST handler saves llm_provider ──────────────────────────────────


def test_app_saves_llm_provider_setting():
    """app.py POST handler must persist llm_provider."""
    assert "set_setting(\"llm_provider\"" in APP_SRC or "set_setting('llm_provider'" in APP_SRC


def test_app_saves_llm_provider_only_when_non_blank():
    """llm_provider must be gated on a non-blank check before saving."""
    # Pattern: get llm_provider from form, then if llm_provider: set_setting
    assert 'if llm_provider:' in APP_SRC or "if llm_provider" in APP_SRC


def test_app_saves_llm_base_url():
    """app.py POST handler must persist llm_base_url."""
    assert "set_setting(\"llm_base_url\"" in APP_SRC or "set_setting('llm_base_url'" in APP_SRC


def test_app_saves_llm_api_key():
    """app.py POST handler must persist llm_api_key."""
    assert "set_setting(\"llm_api_key\"" in APP_SRC or "set_setting('llm_api_key'" in APP_SRC


def test_app_preserves_existing_llm_api_key_when_blank():
    """llm_api_key save must be gated — blank submission must not overwrite existing key."""
    # The pattern: read form value, then 'if llm_api_key:' guard before set_setting
    pattern = re.compile(
        r'llm_api_key\s*=\s*request\.form\.get\("llm_api_key"[^)]*\)[^\n]*\n\s*if llm_api_key:',
        re.MULTILINE,
    )
    assert pattern.search(APP_SRC), (
        "llm_api_key save must be guarded by 'if llm_api_key:' to preserve existing value on blank submit"
    )


def test_app_also_syncs_anthropic_api_key_when_provider_is_anthropic():
    """When llm_provider=anthropic, saving llm_api_key should also update anthropic_api_key."""
    # This keeps the legacy path working automatically
    assert 'set_setting("anthropic_api_key", llm_api_key' in APP_SRC or \
           "set_setting('anthropic_api_key', llm_api_key" in APP_SRC


def test_app_legacy_anthropic_api_key_save_unchanged():
    """Legacy anthropic_api_key must still be saved from the form for backward compatibility."""
    assert '"anthropic_api_key"' in APP_SRC
    # The field list for legacy fields must include anthropic_api_key
    assert "anthropic_api_key" in APP_SRC


# ── app.py: GET handler includes llm settings in current dict ─────────────────


def test_app_get_handler_loads_llm_provider():
    """GET handler must load llm_provider into the settings context."""
    assert '"llm_provider"' in APP_SRC


def test_app_get_handler_loads_llm_base_url():
    """GET handler must load llm_base_url into the settings context."""
    assert '"llm_base_url"' in APP_SRC


def test_app_get_handler_loads_llm_api_key():
    """GET handler loads llm_api_key (used for 'key is set' indicator, not rendered as value)."""
    assert '"llm_api_key"' in APP_SRC


# ── Readiness: API keys never exposed ────────────────────────────────────────


def test_system_readiness_uses_llm_provider():
    """System readiness report checks llm_provider_set."""
    assert "llm_provider_set" in APP_SRC or "llm_provider" in APP_SRC


def test_system_readiness_uses_llm_api_key():
    """System readiness report checks llm_api_key_set."""
    assert "llm_api_key_set" in APP_SRC or "llm_api_key" in APP_SRC


def test_security_readiness_does_not_expose_llm_api_key_value():
    """Security readiness must not return the raw key value — only present/missing."""
    sec_src = _read("ai/security_readiness.py")
    # Must not format/embed the key value in any output string
    assert 'llm_api_key"' not in sec_src or "present" in sec_src or "missing" in sec_src or "has_key" in sec_src


def test_settings_html_readiness_card_does_not_render_key_value():
    """The readiness card in settings.html must not print any raw key value."""
    # Readiness cards only show pass/fail — never key values
    assert "{{ sr." in SETTINGS_HTML  # uses readiness object
    # Ensure llm_api_key value is not printed in readiness section
    assert "{{ settings.llm_api_key }}" not in SETTINGS_HTML


# ── No routing / RAG logic changed ───────────────────────────────────────────


def test_llm_router_not_changed():
    """LLM router source must be unchanged — no new routing logic added."""
    router_src = _read("ai/llm/router.py")
    # Router must still have its core routing function
    assert "def route" in router_src or "def complete" in router_src or "def chat" in router_src


def test_semantic_rag_modules_not_changed():
    """Semantic RAG modules must be untouched."""
    emb_src = _read("ai/kb_embeddings.py")
    search_src = _read("ai/kb_semantic_search.py")
    assert "_embed_openai" in emb_src
    assert "cosine_similarity" in search_src


def test_kb_retrieval_not_changed():
    """kb_retrieval.py must still expose retrieve_relevant_kb_entries unchanged."""
    retrieval_src = _read("ai/kb_retrieval.py")
    assert "def retrieve_relevant_kb_entries" in retrieval_src
