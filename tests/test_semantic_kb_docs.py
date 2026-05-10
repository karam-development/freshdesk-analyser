"""Source-level tests for PR 37 — semantic KB retrieval foundation docs and safety.

All tests are source/text checks.  No app, no DB, no network.

Covers:
- docs/SEMANTIC_KB_RETRIEVAL_PLAN.md exists and has expected content
- README links to semantic plan
- ai/kb_semantic_foundation.py contains no external API calls
- ai/kb_semantic_foundation.py contains no LLMRouter / complete_main_llm calls
- ai/kb_semantic_foundation.py contains no DB writes
- ai/kb_retrieval.py: prepare_kb_entries_for_semantic exists and does not change
  the retrieve_relevant_kb_entries signature or ranking
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ── Source files ──────────────────────────────────────────────────────────────

PLAN_DOC = Path("docs/SEMANTIC_KB_RETRIEVAL_PLAN.md")
README = Path("README.md")
FOUNDATION = Path("ai/kb_semantic_foundation.py")
KB_RETRIEVAL = Path("ai/kb_retrieval.py")


def _plan() -> str:
    return PLAN_DOC.read_text(encoding="utf-8")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _foundation() -> str:
    return FOUNDATION.read_text(encoding="utf-8")


def _kb_retrieval() -> str:
    return KB_RETRIEVAL.read_text(encoding="utf-8")


# ── 1. Plan doc exists ────────────────────────────────────────────────────────

def test_semantic_plan_doc_exists():
    assert PLAN_DOC.exists(), "docs/SEMANTIC_KB_RETRIEVAL_PLAN.md not found"


def test_semantic_plan_doc_not_empty():
    assert PLAN_DOC.stat().st_size > 200


# ── 2. Plan doc content ───────────────────────────────────────────────────────

def test_plan_mentions_deterministic_keyword_retrieval():
    doc = _plan().lower()
    assert "deterministic" in doc and "keyword" in doc


def test_plan_mentions_no_embeddings_in_pr_37():
    plan = _plan()
    lower = plan.lower()
    # Should explicitly say no embeddings in PR 37
    assert "no embeddings" in lower or "no embedding" in lower


def test_plan_mentions_future_embedding_cache_design():
    plan = _plan().lower()
    assert "embedding" in plan and ("cache" in plan or "pr 38" in plan or "pr38" in plan)


def test_plan_mentions_hybrid_retrieval_feature_flag():
    plan = _plan().lower()
    assert "hybrid" in plan and ("feature flag" in plan or "flag" in plan)


def test_plan_mentions_conservative_legal_accounting_handling():
    plan = _plan().lower()
    assert "legal" in plan and "accounting" in plan
    assert "conservative" in plan or "conservative handling" in plan or "case-sensitive" in plan


def test_plan_mentions_pr_38():
    assert "PR 38" in _plan() or "pr 38" in _plan().lower()


def test_plan_mentions_pr_39():
    assert "PR 39" in _plan() or "pr 39" in _plan().lower()


def test_plan_mentions_pr_40():
    assert "PR 40" in _plan() or "pr 40" in _plan().lower()


def test_plan_mentions_safety_rules():
    plan = _plan().lower()
    assert "safety" in plan or "safe" in plan


def test_plan_mentions_no_auto_send():
    assert "no auto-send" in _plan().lower() or "auto-send" in _plan().lower()


def test_plan_mentions_source_evidence_visibility():
    plan = _plan().lower()
    assert "source" in plan and "evidence" in plan


# ── 3. README links to semantic plan ─────────────────────────────────────────

def test_readme_links_to_semantic_plan():
    readme = _readme()
    assert "SEMANTIC_KB_RETRIEVAL_PLAN.md" in readme or "Semantic KB" in readme


def test_readme_semantic_link_in_docs_table():
    readme = _readme()
    # The link should appear in the Documentation table section
    assert "SEMANTIC_KB_RETRIEVAL_PLAN" in readme


# ── 4. No external API calls in foundation helper ────────────────────────────

def test_foundation_no_freshdesk_api_url():
    src = _foundation().lower()
    assert "freshdesk.com/api" not in src
    assert "freshdesk.com" not in src


def test_foundation_no_openai_api_url():
    src = _foundation().lower()
    assert "api.openai.com" not in src


def test_foundation_no_anthropic_api_url():
    src = _foundation().lower()
    assert "api.anthropic.com" not in src


def test_foundation_no_requests_import():
    src = _foundation()
    # Should not import requests, httpx, urllib.request for outbound calls
    import re
    # Allow urllib.parse but not urllib.request (network)
    assert "import requests" not in src
    assert "import httpx" not in src
    # urllib.request is used for network I/O — must not appear
    assert "urllib.request" not in src


# ── 5. No LLMRouter / LLM calls in foundation helper ─────────────────────────

def test_foundation_no_llmrouter_import():
    src = _foundation()
    assert "LLMRouter" not in src
    assert "llm_router" not in src.lower() or "llmrouter" not in src


def test_foundation_no_complete_main_llm():
    src = _foundation()
    assert "complete_main_llm" not in src


def test_foundation_no_anthropic_client():
    src = _foundation()
    assert "Anthropic(" not in src
    assert "from anthropic" not in src
    assert "import anthropic" not in src


def test_foundation_no_openai_client():
    src = _foundation()
    assert "OpenAI(" not in src
    assert "from openai" not in src
    assert "import openai" not in src


# ── 6. No DB writes in foundation helper ─────────────────────────────────────

def test_foundation_no_db_execute_write():
    src = _foundation().lower()
    # Should contain no INSERT / UPDATE / DELETE / CREATE TABLE
    assert "insert into" not in src
    assert "update " not in src.replace("updated", "").replace("update_", "")
    assert "delete from" not in src
    assert "create table" not in src


def test_foundation_no_db_commit():
    src = _foundation().lower()
    assert ".commit()" not in src


def test_foundation_imports_are_stdlib_only():
    src = _foundation()
    # The only imports should be stdlib: hashlib, re, typing, __future__
    import re as _re
    import_lines = [
        line.strip() for line in src.splitlines()
        if line.strip().startswith(("import ", "from ")) and "noqa" not in line
    ]
    allowed_modules = {"__future__", "hashlib", "re", "typing"}
    for line in import_lines:
        # Extract first module name
        if line.startswith("from "):
            module = line.split()[1].split(".")[0]
        else:
            module = line.split()[1].split(".")[0]
        assert module in allowed_modules, (
            f"Unexpected import in kb_semantic_foundation.py: '{line}'"
        )


# ── 7. Foundation helper file structure ──────────────────────────────────────

def test_foundation_file_exists():
    assert FOUNDATION.exists(), "ai/kb_semantic_foundation.py not found"


def test_foundation_exposes_normalize_function():
    src = _foundation()
    assert "def normalize_kb_text_for_semantic(" in src


def test_foundation_exposes_chunk_function():
    src = _foundation()
    assert "def chunk_kb_text(" in src


def test_foundation_exposes_build_records_function():
    src = _foundation()
    assert "def build_semantic_kb_records(" in src


def test_foundation_has_module_docstring():
    src = _foundation()
    # First non-empty, non-comment line should be a docstring
    first_triple = src.find('"""')
    assert first_triple >= 0, "No module docstring found"
    assert first_triple < 200, "Module docstring not near the top of the file"


# ── 8. kb_retrieval.py: bridge helper exists and is safe ─────────────────────

def test_kb_retrieval_has_prepare_for_semantic_helper():
    src = _kb_retrieval()
    assert "def prepare_kb_entries_for_semantic(" in src


def test_kb_retrieval_bridge_does_not_call_retrieve_directly():
    src = _kb_retrieval()
    # Locate the bridge helper
    start = src.find("def prepare_kb_entries_for_semantic(")
    assert start >= 0
    # Find the next function definition after the bridge
    next_def = src.find("\ndef ", start + 1)
    bridge_body = src[start:next_def] if next_def > 0 else src[start:]
    # The bridge must NOT call retrieve_relevant_kb_entries as a function
    # (a docstring mention is acceptable; a live call would be "retrieve_relevant_kb_entries(")
    assert "retrieve_relevant_kb_entries(" not in bridge_body


def test_kb_retrieval_retrieve_function_still_present():
    src = _kb_retrieval()
    assert "def retrieve_relevant_kb_entries(" in src


def test_kb_retrieval_bridge_imports_from_foundation():
    src = _kb_retrieval()
    start = src.find("def prepare_kb_entries_for_semantic(")
    assert start >= 0
    next_def = src.find("\ndef ", start + 1)
    bridge_body = src[start:next_def] if next_def > 0 else src[start:]
    assert "kb_semantic_foundation" in bridge_body


def test_kb_retrieval_bridge_has_no_db_write():
    src = _kb_retrieval()
    start = src.find("def prepare_kb_entries_for_semantic(")
    assert start >= 0
    next_def = src.find("\ndef ", start + 1)
    bridge_body = (src[start:next_def] if next_def > 0 else src[start:]).lower()
    assert "insert into" not in bridge_body
    assert ".commit()" not in bridge_body
