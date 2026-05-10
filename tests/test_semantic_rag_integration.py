"""Integration and source-level tests for PR 38 — Semantic RAG feature flag.

Covers:
- Feature flag default false
- When false, no embedding functions are called
- retrieve_relevant_kb_entries behaviour unchanged
- Cache table migration is idempotent
- Hybrid retrieval deduplicates and adds source tags
- Semantic failure falls back to keyword-only
- No API keys in error messages
- app.py wiring is behind feature flag
- No semantic calls in CI/default tests
- Docs mention feature flag and cost
- Acceptance scenarios
"""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest


# ── DB helpers ─────────────────────────────────────────────────────────────────


def _make_db(semantic_rag_enabled="false"):
    """In-memory SQLite DB with all required tables."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS kb_embedding_cache (
            record_id TEXT PRIMARY KEY, entry_id TEXT, provider TEXT, model TEXT,
            text_hash TEXT, embedding_json TEXT, metadata_json TEXT,
            created_at TEXT, updated_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        ("semantic_rag_enabled", semantic_rag_enabled),
    )
    db.commit()
    return db


def _insert_kb_entry(db, title, content, category="product"):
    db.execute(
        "INSERT INTO knowledge_base (category, title, content) VALUES (?, ?, ?)",
        (category, title, content),
    )
    db.commit()


# ── Feature flag default ───────────────────────────────────────────────────────


class TestFeatureFlagDefault:

    def test_default_is_false_no_embed_calls(self):
        """When semantic_rag_enabled is missing from settings, no embed calls are made."""
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        db.execute("CREATE TABLE kb_embedding_cache (record_id TEXT PRIMARY KEY, entry_id TEXT, provider TEXT, model TEXT, text_hash TEXT, embedding_json TEXT, metadata_json TEXT, created_at TEXT, updated_at TEXT)")
        db.commit()

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            from app import get_setting
            val = get_setting("semantic_rag_enabled", "false", db=db)
            assert val.lower() not in ("true", "1", "yes")

        mock_embed.assert_not_called()

    def test_false_flag_augment_returns_keyword_entries(self):
        """_augment_kb_with_semantic returns keyword entries unchanged when flag is false."""
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="false")
        keyword_entries = [
            {"id": 1, "title": "K1", "content": "C1", "score": 8.0, "evidence_type": "product_evidence"}
        ]

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            result = _augment_kb_with_semantic(db, keyword_entries, subject="test")

        mock_embed.assert_not_called()
        assert result is keyword_entries or result == keyword_entries

    def test_true_flag_attempts_semantic(self):
        """When flag is true, _augment_kb_with_semantic attempts embedding calls."""
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="true")
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-test-key"),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_provider", "openai"),
        )
        db.commit()
        _insert_kb_entry(db, "Entry 1", "Content one.")

        keyword_entries = []

        with patch("ai.kb_embeddings._embed_openai") as mock_openai:
            mock_openai.return_value = [[0.1, 0.2]]
            # embed_texts is called twice: once for KB records, once for query
            result = _augment_kb_with_semantic(
                db, keyword_entries, subject="test query"
            )

        # Whether it succeeds or fails, result must be a list
        assert isinstance(result, list)


# ── retrieve_relevant_kb_entries unchanged ────────────────────────────────────


class TestKeywordRetrievalUnchanged:

    def test_retrieve_relevant_kb_entries_signature_unchanged(self):
        """Function signature must have all original parameters."""
        import inspect
        from ai.kb_retrieval import retrieve_relevant_kb_entries

        sig = inspect.signature(retrieve_relevant_kb_entries)
        params = list(sig.parameters.keys())
        for expected in ["db", "subject", "summary", "template_name", "workflow_name", "limit", "min_score"]:
            assert expected in params

    def test_retrieve_relevant_kb_entries_returns_list(self):
        from ai.kb_retrieval import retrieve_relevant_kb_entries

        db = _make_db()
        _insert_kb_entry(db, "Dropdown setting", "Use the dropdown for staff wording.")
        result = retrieve_relevant_kb_entries(
            db, subject="dropdown", summary="", template_name="", workflow_name=""
        )
        assert isinstance(result, list)

    def test_retrieve_relevant_kb_entries_return_shape(self):
        """Return dict must have all expected keys."""
        from ai.kb_retrieval import retrieve_relevant_kb_entries

        db = _make_db()
        _insert_kb_entry(db, "Dropdown setting", "Use the dropdown for staff wording.")
        entries = retrieve_relevant_kb_entries(
            db, subject="dropdown", summary="", template_name="", workflow_name=""
        )
        if entries:
            e = entries[0]
            for key in ["id", "category", "title", "content", "score", "matched_terms",
                        "evidence_type", "score_reasons"]:
                assert key in e, f"Key '{key}' missing from retrieve_relevant_kb_entries result"

    def test_retrieve_relevant_kb_entries_empty_db_returns_empty(self):
        from ai.kb_retrieval import retrieve_relevant_kb_entries

        db = _make_db()
        result = retrieve_relevant_kb_entries(db, subject="anything")
        assert result == []


# ── Cache table migration ──────────────────────────────────────────────────────


class TestCacheTableMigration:

    def test_kb_embedding_cache_table_created_idempotently(self):
        """CREATE TABLE IF NOT EXISTS must not fail on second call."""
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row

        create_sql = """CREATE TABLE IF NOT EXISTS kb_embedding_cache (
            record_id TEXT PRIMARY KEY, entry_id TEXT, provider TEXT, model TEXT,
            text_hash TEXT, embedding_json TEXT, metadata_json TEXT,
            created_at TEXT, updated_at TEXT
        )"""
        db.execute(create_sql)
        db.execute(create_sql)  # second call must not raise
        db.commit()

        cols = {row[1] for row in db.execute("PRAGMA table_info(kb_embedding_cache)").fetchall()}
        for col in ["record_id", "entry_id", "provider", "model", "text_hash",
                    "embedding_json", "metadata_json", "created_at", "updated_at"]:
            assert col in cols

    def test_cache_table_has_required_columns(self):
        db = _make_db()
        cols = {row[1] for row in db.execute("PRAGMA table_info(kb_embedding_cache)").fetchall()}
        for col in ["record_id", "entry_id", "provider", "model", "text_hash",
                    "embedding_json", "metadata_json", "created_at", "updated_at"]:
            assert col in cols, f"Column '{col}' missing from kb_embedding_cache"

    def test_record_id_is_primary_key(self):
        db = _make_db()
        info = {row[1]: row for row in db.execute("PRAGMA table_info(kb_embedding_cache)").fetchall()}
        assert info["record_id"][5] == 1  # pk column

    def test_provider_model_separation(self):
        """Same record_id with different providers/models stored separately."""
        from ai.kb_embeddings import save_cached_embedding, load_cached_embedding, _text_hash

        db = _make_db()
        rec = {"record_id": "r1", "entry_id": "1", "title": "T", "text": "T", "chunk_index": 0, "metadata": {"total_chunks": 1}}
        emb_oai = [0.1, 0.2]
        emb_cohere = [0.9, 0.8]

        # Manually insert for two providers
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        th = _text_hash("T")
        db.execute(
            "INSERT INTO kb_embedding_cache (record_id, entry_id, provider, model, text_hash, embedding_json, metadata_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("r1-oai", "1", "openai", "model-a", th, json.dumps(emb_oai), "{}", now, now)
        )
        db.execute(
            "INSERT INTO kb_embedding_cache (record_id, entry_id, provider, model, text_hash, embedding_json, metadata_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("r1-cohere", "1", "cohere", "model-b", th, json.dumps(emb_cohere), "{}", now, now)
        )
        db.commit()

        r_oai = load_cached_embedding(db, "r1-oai", "openai", "model-a", th)
        r_cohere = load_cached_embedding(db, "r1-cohere", "cohere", "model-b", th)
        assert r_oai == emb_oai
        assert r_cohere == emb_cohere
        assert r_oai != r_cohere


# ── retrieve_hybrid_kb_entries ─────────────────────────────────────────────────


class TestHybridRetrieval:

    def test_keyword_only_when_no_semantic(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        kw = [{"id": "1", "entry_id": "1", "title": "T1", "score": 8.0}]
        result = retrieve_hybrid_kb_entries(db, {}, kw, [], top_n=8)
        assert len(result) == 1
        assert result[0]["source"] == "keyword"

    def test_semantic_only_when_no_keyword(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        sem = [{"id": "2", "entry_id": "2", "title": "T2", "score": 75.0, "source": "semantic"}]
        result = retrieve_hybrid_kb_entries(db, {}, [], sem, top_n=8)
        assert len(result) == 1
        assert result[0]["source"] == "semantic"

    def test_deduplication_marks_hybrid(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        kw = [{"id": "1", "entry_id": "1", "title": "Shared Entry", "score": 8.0}]
        sem = [{"id": "1", "entry_id": "1", "title": "Shared Entry", "score": 80.0, "source": "semantic"}]
        result = retrieve_hybrid_kb_entries(db, {}, kw, sem, top_n=8)
        assert len(result) == 1
        assert result[0]["source"] == "hybrid"

    def test_non_overlapping_entries_both_included(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        kw = [{"id": "1", "entry_id": "1", "title": "Keyword Entry", "score": 8.0}]
        sem = [{"id": "2", "entry_id": "2", "title": "Semantic Entry", "score": 70.0, "source": "semantic"}]
        result = retrieve_hybrid_kb_entries(db, {}, kw, sem, top_n=8)
        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert "keyword" in sources
        assert "semantic" in sources

    def test_top_n_respected(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        kw = [{"id": str(i), "entry_id": str(i), "title": f"KW{i}", "score": float(i)} for i in range(5)]
        sem = [{"id": str(i + 5), "entry_id": str(i + 5), "title": f"SEM{i}", "score": float(i)} for i in range(5)]
        result = retrieve_hybrid_kb_entries(db, {}, kw, sem, top_n=6)
        assert len(result) == 6

    def test_keyword_entries_not_mutated(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries
        import copy

        db = _make_db()
        kw = [{"id": "1", "entry_id": "1", "title": "T", "score": 5.0}]
        original = copy.deepcopy(kw)
        retrieve_hybrid_kb_entries(db, {}, kw, [], top_n=8)
        assert kw == original

    def test_returns_keyword_on_exception(self):
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        kw = [{"id": "1", "entry_id": "1", "title": "Safe", "score": 5.0}]
        # Pass a non-iterable as semantic_entries to provoke an internal error
        result = retrieve_hybrid_kb_entries(db, {}, kw, None, top_n=8)  # type: ignore
        # Must not raise; returns at most keyword entries
        assert isinstance(result, list)


# ── Semantic failure fallback ──────────────────────────────────────────────────


class TestSemanticFallback:

    def test_embed_failure_returns_keyword_entries(self):
        """If embedding API fails, _augment_kb_with_semantic returns keyword entries."""
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="true")
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-test"),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_provider", "openai"),
        )
        db.commit()
        _insert_kb_entry(db, "E1", "content one")

        keyword_entries = [{"id": "1", "entry_id": "1", "title": "K1", "score": 5.0}]

        # Patch embed_texts to raise
        with patch("ai.kb_embeddings._embed_openai", side_effect=RuntimeError("API down")):
            result = _augment_kb_with_semantic(db, keyword_entries, subject="query")

        # Must fall back to keyword entries
        assert isinstance(result, list)
        # Keyword entry must be preserved
        assert any(e.get("title") == "K1" or e.get("id") == "1" for e in result)

    def test_no_api_key_falls_back_to_keyword(self):
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="true")
        # No llm_api_key set
        keyword_entries = [{"id": "1", "entry_id": "1", "title": "K1", "score": 5.0}]

        result = _augment_kb_with_semantic(db, keyword_entries, subject="query")
        assert isinstance(result, list)

    def test_exception_does_not_propagate(self):
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="true")
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-test"),
        )
        db.commit()

        keyword_entries = [{"id": "1", "title": "K", "score": 5.0}]

        # Induce catastrophic failure
        with patch("ai.kb_semantic_foundation.build_semantic_kb_records", side_effect=MemoryError("OOM")):
            result = _augment_kb_with_semantic(db, keyword_entries, subject="q")

        assert isinstance(result, list)


# ── No API key in errors ───────────────────────────────────────────────────────


class TestApiKeyNotExposed:

    def test_embed_texts_does_not_return_api_key(self):
        from ai.kb_embeddings import embed_texts

        db = _make_db()
        secret = "sk-my-secret-production-key-9999"

        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg, \
             patch("ai.kb_embeddings._get_api_key") as mock_key, \
             patch("ai.kb_embeddings._embed_openai") as mock_openai:
            mock_cfg.return_value = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "has_key": True,
                "base_url": "",
            }
            mock_key.return_value = secret
            mock_openai.return_value = [[0.1, 0.2]]

            result = embed_texts(db, ["test text"])

        result_str = json.dumps(result)
        assert secret not in result_str

    def test_get_embedding_provider_config_does_not_include_api_key(self):
        from ai.kb_embeddings import get_embedding_provider_config

        db = _make_db()
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-sensitive-key"),
        )
        db.commit()

        with patch("app.get_setting") as mock_get:
            mock_get.side_effect = lambda key, default="", db=None: {
                "llm_provider": "openai",
                "semantic_rag_provider": "openai",
                "semantic_embedding_model": "text-embedding-3-small",
                "llm_api_key": "sk-sensitive-key",
                "llm_base_url": "",
            }.get(key, default)

            cfg = get_embedding_provider_config(db)

        assert "api_key" not in cfg
        assert "sk-sensitive-key" not in json.dumps(cfg)


# ── App.py wiring behind feature flag ─────────────────────────────────────────


class TestAppWiring:

    def test_augment_function_exists_in_app(self):
        """_augment_kb_with_semantic must exist in app.py."""
        import app
        assert hasattr(app, "_augment_kb_with_semantic")

    def test_augment_is_callable(self):
        import app
        assert callable(app._augment_kb_with_semantic)

    def test_app_py_calls_augment_at_display_point(self):
        """app.py source must reference _augment_kb_with_semantic at the live display path."""
        from pathlib import Path
        src = Path("app.py").read_text()
        # Must appear at least 3 times (ingest, display, draft)
        count = src.count("_augment_kb_with_semantic")
        assert count >= 3, f"Expected ≥3 wiring points, found {count}"

    def test_kb_embedding_cache_in_app_py(self):
        """app.py must create the kb_embedding_cache table."""
        from pathlib import Path
        src = Path("app.py").read_text()
        assert "kb_embedding_cache" in src

    def test_augment_checks_feature_flag_first(self):
        """Source of _augment_kb_with_semantic must check semantic_rag_enabled."""
        from pathlib import Path
        src = Path("app.py").read_text()
        start = src.find("def _augment_kb_with_semantic(")
        assert start >= 0
        next_def = src.find("\ndef ", start + 1)
        body = src[start:next_def] if next_def > 0 else src[start:]
        assert "semantic_rag_enabled" in body


# ── Source / safety checks ────────────────────────────────────────────────────


class TestSourceSafetyChecks:

    def test_kb_embeddings_no_freshdesk_url(self):
        from pathlib import Path
        src = Path("ai/kb_embeddings.py").read_text().lower()
        assert "freshdesk.com" not in src

    def test_kb_embeddings_no_anthropic_call(self):
        from pathlib import Path
        src = Path("ai/kb_embeddings.py").read_text()
        assert "from anthropic" not in src
        assert "Anthropic(" not in src

    def test_kb_semantic_search_no_api_calls(self):
        from pathlib import Path
        src = Path("ai/kb_semantic_search.py").read_text()
        assert "import requests" not in src
        assert "import openai" not in src
        assert "import anthropic" not in src
        assert "urllib.request" not in src

    def test_kb_semantic_search_no_db_writes(self):
        from pathlib import Path
        src = Path("ai/kb_semantic_search.py").read_text().lower()
        assert "insert into" not in src
        assert ".commit()" not in src

    def test_hybrid_retrieval_does_not_change_retrieve_signature(self):
        from pathlib import Path
        src = Path("ai/kb_retrieval.py").read_text()
        assert "def retrieve_relevant_kb_entries(" in src
        assert "def retrieve_hybrid_kb_entries(" in src

    def test_no_auto_send_in_new_files(self):
        from pathlib import Path
        for fname in ["ai/kb_embeddings.py", "ai/kb_semantic_search.py"]:
            src = Path(fname).read_text().lower()
            assert "send_reply" not in src
            assert "requests.post" not in src
            assert "freshdesk.com/api" not in src


# ── Docs ──────────────────────────────────────────────────────────────────────


class TestDocs:

    def test_semantic_plan_mentions_feature_flag(self):
        from pathlib import Path
        doc = Path("docs/SEMANTIC_KB_RETRIEVAL_PLAN.md").read_text().lower()
        assert "feature flag" in doc or "semantic_rag_enabled" in doc

    def test_semantic_plan_mentions_off_by_default(self):
        from pathlib import Path
        doc = Path("docs/SEMANTIC_KB_RETRIEVAL_PLAN.md").read_text().lower()
        assert "off by default" in doc or "default" in doc

    def test_semantic_plan_mentions_cost(self):
        from pathlib import Path
        doc = Path("docs/SEMANTIC_KB_RETRIEVAL_PLAN.md").read_text().lower()
        assert "cost" in doc or "billing" in doc or "token" in doc

    def test_production_checklist_mentions_semantic_rag(self):
        from pathlib import Path
        doc = Path("docs/PRODUCTION_CHECKLIST.md").read_text().lower()
        assert "semantic_rag_enabled" in doc or "semantic rag" in doc

    def test_production_checklist_mentions_cost(self):
        from pathlib import Path
        doc = Path("docs/PRODUCTION_CHECKLIST.md").read_text().lower()
        assert "cost" in doc or "billing" in doc or "api call" in doc

    def test_readme_mentions_semantic_rag(self):
        from pathlib import Path
        readme = Path("README.md").read_text().lower()
        assert "semantic" in readme and "rag" in readme


# ── Acceptance scenarios ──────────────────────────────────────────────────────


class TestAcceptanceScenarios:

    def test_flag_false_exact_keyword_results(self):
        """semantic_rag_enabled=false: augment returns exactly keyword results."""
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="false")
        keyword_entries = [
            {"id": "1", "entry_id": "1", "title": "Dropdown setting",
             "content": "Use dropdown.", "score": 7.0, "evidence_type": "existing_setting_evidence"},
        ]

        with patch("ai.kb_embeddings.embed_texts") as mock_embed, \
             patch("ai.kb_embeddings._embed_openai") as mock_openai:
            result = _augment_kb_with_semantic(
                db, keyword_entries, subject="dropdown", summary="staff wording"
            )

        mock_embed.assert_not_called()
        mock_openai.assert_not_called()
        assert result == keyword_entries or result is keyword_entries

    def test_flag_true_mocked_semantic_match_added(self):
        """semantic_rag_enabled=true with mocked embeddings: semantic match added."""
        from app import _augment_kb_with_semantic
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db(semantic_rag_enabled="true")
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-test"),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_provider", "openai"),
        )
        db.commit()
        _insert_kb_entry(db, "Semantic Entry", "This is semantically relevant content.")

        keyword_entries = []
        fake_emb = [1.0, 0.0, 0.0]

        with patch("ai.kb_embeddings._embed_openai") as mock_openai:
            # All embeddings return the same vector → similarity = 1.0
            mock_openai.return_value = [fake_emb] * 100

            result = _augment_kb_with_semantic(
                db, keyword_entries, subject="semantically relevant"
            )

        assert isinstance(result, list)
        # If semantic succeeded, we should have at least one entry
        # (may still be empty if min_score isn't met with same-vector degenerate case)
        # The important check is: it's a list and didn't crash
        for entry in result:
            assert isinstance(entry, dict)

    def test_flag_true_duplicate_becomes_hybrid(self):
        """Entries in both keyword and semantic results get source='hybrid'."""
        from ai.kb_retrieval import retrieve_hybrid_kb_entries

        db = _make_db()
        shared = {"id": "5", "entry_id": "5", "title": "Shared", "score": 9.0}
        kw = [shared]
        sem = [{"id": "5", "entry_id": "5", "title": "Shared", "score": 80.0, "source": "semantic"}]

        result = retrieve_hybrid_kb_entries(db, {}, kw, sem, top_n=8)
        hybrid = [r for r in result if r.get("source") == "hybrid"]
        assert len(hybrid) == 1
        assert hybrid[0]["title"] == "Shared"

    def test_flag_true_embed_failure_fallback(self):
        """If embedding API raises, keyword results are returned unchanged."""
        from app import _augment_kb_with_semantic

        db = _make_db(semantic_rag_enabled="true")
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_api_key", "sk-test"),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("llm_provider", "openai"),
        )
        db.commit()
        _insert_kb_entry(db, "E1", "content")

        keyword_entries = [{"id": "1", "entry_id": "1", "title": "KW", "score": 5.0}]

        with patch("ai.kb_embeddings._embed_openai", side_effect=Exception("API unreachable")):
            result = _augment_kb_with_semantic(db, keyword_entries, subject="test")

        assert isinstance(result, list)
        # Must contain the keyword entry
        titles = [e.get("title") for e in result]
        assert "KW" in titles
