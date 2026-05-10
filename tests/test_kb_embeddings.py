"""Tests for ai/kb_embeddings.py — PR 38.

All external API calls are mocked.  No network I/O, no real OpenAI calls.
"""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from ai.kb_embeddings import (
    _text_hash,
    embed_texts,
    get_embedding_provider_config,
    get_or_create_embeddings_for_records,
    load_cached_embedding,
    save_cached_embedding,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_db():
    """Return an in-memory SQLite DB with kb_embedding_cache table."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS kb_embedding_cache (
            record_id      TEXT PRIMARY KEY,
            entry_id       TEXT,
            provider       TEXT,
            model          TEXT,
            text_hash      TEXT,
            embedding_json TEXT,
            metadata_json  TEXT,
            created_at     TEXT,
            updated_at     TEXT
        )
    """)
    db.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    db.commit()
    return db


def _make_record(record_id="rec1", title="Title", text="Title. Content."):
    return {
        "record_id": record_id,
        "entry_id": "1",
        "chunk_index": 0,
        "title": title,
        "category": "product",
        "evidence_type": "general_evidence",
        "text": text,
        "source_text": "Content.",
        "metadata": {"title": title, "chunk_index": 0, "total_chunks": 1},
    }


# ── _text_hash ─────────────────────────────────────────────────────────────────


class TestTextHash:

    def test_deterministic(self):
        assert _text_hash("hello") == _text_hash("hello")

    def test_different_text_different_hash(self):
        assert _text_hash("hello") != _text_hash("world")

    def test_empty_string(self):
        assert len(_text_hash("")) == 32

    def test_returns_32_hex_chars(self):
        h = _text_hash("test")
        assert len(h) == 32
        int(h, 16)  # valid hex


# ── Cache load/save ────────────────────────────────────────────────────────────


class TestCacheLoadSave:

    def test_save_and_load_round_trip(self):
        db = _make_db()
        rec = _make_record()
        emb = [0.1, 0.2, 0.3]
        save_cached_embedding(db, rec, emb, "openai", "text-embedding-3-small")

        th = _text_hash(rec["text"])
        result = load_cached_embedding(db, "rec1", "openai", "text-embedding-3-small", th)
        assert result == emb

    def test_load_returns_none_for_missing_record(self):
        db = _make_db()
        th = _text_hash("some text")
        result = load_cached_embedding(db, "nonexistent", "openai", "model", th)
        assert result is None

    def test_load_returns_none_for_stale_text_hash(self):
        db = _make_db()
        rec = _make_record(text="original text")
        emb = [0.5, 0.5]
        save_cached_embedding(db, rec, emb, "openai", "text-embedding-3-small")

        stale_hash = _text_hash("changed text")
        result = load_cached_embedding(db, "rec1", "openai", "text-embedding-3-small", stale_hash)
        assert result is None

    def test_load_returns_none_for_different_provider(self):
        db = _make_db()
        rec = _make_record()
        emb = [0.1]
        save_cached_embedding(db, rec, emb, "openai", "model-a")

        th = _text_hash(rec["text"])
        result = load_cached_embedding(db, "rec1", "cohere", "model-a", th)
        assert result is None

    def test_load_returns_none_for_different_model(self):
        db = _make_db()
        rec = _make_record()
        emb = [0.1]
        save_cached_embedding(db, rec, emb, "openai", "text-embedding-3-small")

        th = _text_hash(rec["text"])
        result = load_cached_embedding(db, "rec1", "openai", "text-embedding-ada-002", th)
        assert result is None

    def test_save_is_idempotent(self):
        db = _make_db()
        rec = _make_record()
        emb = [0.1, 0.2]
        save_cached_embedding(db, rec, emb, "openai", "model")
        save_cached_embedding(db, rec, emb, "openai", "model")  # second call: no error
        count = db.execute("SELECT COUNT(*) FROM kb_embedding_cache").fetchone()[0]
        assert count == 1

    def test_save_preserves_created_at_on_update(self):
        db = _make_db()
        rec = _make_record()
        emb1 = [0.1]
        emb2 = [0.9]
        save_cached_embedding(db, rec, emb1, "openai", "model")
        created1 = db.execute(
            "SELECT created_at FROM kb_embedding_cache WHERE record_id = 'rec1'"
        ).fetchone()["created_at"]
        save_cached_embedding(db, rec, emb2, "openai", "model")
        created2 = db.execute(
            "SELECT created_at FROM kb_embedding_cache WHERE record_id = 'rec1'"
        ).fetchone()["created_at"]
        assert created1 == created2  # created_at preserved

    def test_save_never_raises_on_db_error(self):
        # Deliberately broken DB (missing table)
        bad_db = sqlite3.connect(":memory:")
        rec = _make_record()
        save_cached_embedding(bad_db, rec, [0.1], "openai", "model")  # must not raise


# ── embed_texts ────────────────────────────────────────────────────────────────


class TestEmbedTexts:

    def test_empty_list_returns_empty(self):
        db = _make_db()
        result = embed_texts(db, [])
        assert result == []

    def test_unsupported_provider_returns_empty(self):
        db = _make_db()
        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg:
            mock_cfg.return_value = {
                "provider": "cohere",
                "model": "embed-v3",
                "has_key": True,
                "base_url": "",
            }
            result = embed_texts(db, ["hello"], provider="cohere")
        assert result == []

    def test_missing_api_key_returns_empty(self):
        db = _make_db()
        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg, \
             patch("ai.kb_embeddings._get_api_key") as mock_key:
            mock_cfg.return_value = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "has_key": False,
                "base_url": "",
            }
            mock_key.return_value = ""
            result = embed_texts(db, ["hello"])
        assert result == []

    def test_successful_openai_call_returns_embeddings(self):
        db = _make_db()
        fake_emb = [0.1, 0.2, 0.3]

        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg, \
             patch("ai.kb_embeddings._get_api_key") as mock_key, \
             patch("ai.kb_embeddings._embed_openai") as mock_openai:
            mock_cfg.return_value = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "has_key": True,
                "base_url": "",
            }
            mock_key.return_value = "sk-test"
            mock_openai.return_value = [fake_emb]

            result = embed_texts(db, ["hello world"])

        assert result == [fake_emb]
        mock_openai.assert_called_once()
        # API key must NOT appear in any of the call args as a plain string for logging
        # (we just verify it was called)

    def test_openai_failure_returns_empty_vectors(self):
        db = _make_db()
        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg, \
             patch("ai.kb_embeddings._get_api_key") as mock_key, \
             patch("ai.kb_embeddings._embed_openai") as mock_openai:
            mock_cfg.return_value = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "has_key": True,
                "base_url": "",
            }
            mock_key.return_value = "sk-test"
            mock_openai.return_value = []  # API failure

            result = embed_texts(db, ["hello"])

        assert result == [[]]

    def test_whitespace_only_texts_get_empty_vector(self):
        db = _make_db()
        with patch("ai.kb_embeddings.get_embedding_provider_config") as mock_cfg, \
             patch("ai.kb_embeddings._get_api_key") as mock_key, \
             patch("ai.kb_embeddings._embed_openai") as mock_openai:
            mock_cfg.return_value = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "has_key": True,
                "base_url": "",
            }
            mock_key.return_value = "sk-test"
            mock_openai.return_value = [[0.1, 0.2]]

            result = embed_texts(db, ["   ", "real text"])

        # First text is whitespace → empty vector; second gets embedding
        assert result[0] == []
        assert result[1] == [0.1, 0.2]

    def test_api_key_not_in_returned_result(self):
        """Embedding result must never contain the API key string."""
        db = _make_db()
        secret = "sk-super-secret-key-12345"
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
            mock_openai.return_value = [[0.5, 0.5]]

            result = embed_texts(db, ["hello"])

        result_str = json.dumps(result)
        assert secret not in result_str


# ── get_or_create_embeddings_for_records ──────────────────────────────────────


class TestGetOrCreateEmbeddingsForRecords:

    def test_empty_records_returns_empty(self):
        db = _make_db()
        assert get_or_create_embeddings_for_records(db, [], "openai", "model") == []

    def test_loads_from_cache_without_api_call(self):
        db = _make_db()
        rec = _make_record()
        emb = [0.4, 0.5, 0.6]
        save_cached_embedding(db, rec, emb, "openai", "text-embedding-3-small")

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            result = get_or_create_embeddings_for_records(
                db, [rec], "openai", "text-embedding-3-small"
            )

        mock_embed.assert_not_called()
        assert result[0]["embedding"] == emb

    def test_generates_missing_embeddings(self):
        db = _make_db()
        rec = _make_record()
        fake_emb = [0.1, 0.2]

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            mock_embed.return_value = [fake_emb]
            result = get_or_create_embeddings_for_records(
                db, [rec], "openai", "text-embedding-3-small"
            )

        assert result[0]["embedding"] == fake_emb

    def test_generated_embeddings_are_saved_to_cache(self):
        db = _make_db()
        rec = _make_record()
        fake_emb = [0.7, 0.8]

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            mock_embed.return_value = [fake_emb]
            get_or_create_embeddings_for_records(
                db, [rec], "openai", "text-embedding-3-small"
            )

        th = _text_hash(rec["text"])
        cached = load_cached_embedding(db, "rec1", "openai", "text-embedding-3-small", th)
        assert cached == fake_emb

    def test_stale_text_hash_triggers_regeneration(self):
        db = _make_db()
        rec = _make_record(text="original text")
        old_emb = [0.1, 0.2]
        save_cached_embedding(db, rec, old_emb, "openai", "model")

        # Now the record has different text
        rec_updated = dict(rec)
        rec_updated["text"] = "updated text"

        new_emb = [0.9, 0.8]
        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            mock_embed.return_value = [new_emb]
            result = get_or_create_embeddings_for_records(db, [rec_updated], "openai", "model")

        mock_embed.assert_called_once()
        assert result[0]["embedding"] == new_emb

    def test_does_not_mutate_input_records(self):
        db = _make_db()
        rec = _make_record()
        original = dict(rec)

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            mock_embed.return_value = [[0.1]]
            get_or_create_embeddings_for_records(db, [rec], "openai", "model")

        # Original record must not have "embedding" added
        assert "embedding" not in rec
        assert rec == original

    def test_failed_embedding_gets_empty_vector(self):
        db = _make_db()
        rec = _make_record()

        with patch("ai.kb_embeddings.embed_texts") as mock_embed:
            mock_embed.return_value = [[]]  # empty vector = failure
            result = get_or_create_embeddings_for_records(db, [rec], "openai", "model")

        assert result[0]["embedding"] == []
