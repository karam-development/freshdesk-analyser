"""KB embedding cache helpers.

Manages embedding generation and caching for semantic KB retrieval.
Embeddings are generated via an external provider API (OpenAI or compatible).
All generated embeddings are stored in the ``kb_embedding_cache`` DB table to
avoid redundant API calls.

Embedding API calls are only made when ``semantic_rag_enabled`` is explicitly
set to ``true`` in settings.  Tests must mock provider calls.

Public functions
----------------
get_embedding_provider_config(db) -> dict
    Read provider/model config from settings.  Never returns the API key.

embed_texts(db, texts, provider=None, model=None) -> list[list[float]]
    Generate embeddings for a list of texts.  Returns [] on unrecoverable failure.

load_cached_embedding(db, record_id, provider, model, text_hash) -> list[float] | None
    Load a cached embedding.  Returns None if not found or text_hash is stale.

save_cached_embedding(db, record, embedding, provider, model) -> None
    Upsert an embedding into the cache (best-effort; never raises).

get_or_create_embeddings_for_records(db, records, provider, model) -> list[dict]
    For each record, load from cache or generate and cache.  Returns records with
    an ``"embedding"`` key added.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Provider constants ─────────────────────────────────────────────────────────

_SUPPORTED_EMBEDDING_PROVIDERS = frozenset({"openai"})

_DEFAULT_EMBEDDING_MODEL: dict = {
    "openai": "text-embedding-3-small",
}

_BATCH_SIZE = 64  # max texts per single API call


# ── Provider config ────────────────────────────────────────────────────────────


def get_embedding_provider_config(db) -> dict:
    """Read embedding provider config from settings.

    Returns
    -------
    dict with keys:
        provider : str  — embedding provider ("openai", …)
        model    : str  — embedding model name
        has_key  : bool — True if an API key is configured
        base_url : str  — optional OpenAI-compatible base URL

    The API key itself is deliberately NOT included in the returned dict.
    Never raises; returns safe defaults on error.
    """
    try:
        from app import get_setting  # noqa: PLC0415

        llm_provider = get_setting("llm_provider", "openai", db=db) or "openai"
        provider = (
            get_setting("semantic_rag_provider", llm_provider, db=db) or llm_provider
        ).strip().lower()

        default_model = _DEFAULT_EMBEDDING_MODEL.get(provider, "text-embedding-3-small")
        model = (
            get_setting("semantic_embedding_model", default_model, db=db) or default_model
        ).strip()

        api_key = get_setting("llm_api_key", "", db=db) or ""
        base_url = get_setting("llm_base_url", "", db=db) or ""

        return {
            "provider": provider,
            "model": model,
            "has_key": bool(api_key),
            "base_url": base_url,
            # api_key deliberately excluded
        }
    except Exception as exc:
        logger.warning("get_embedding_provider_config failed: %s", exc)
        return {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "has_key": False,
            "base_url": "",
        }


def _get_api_key(db) -> str:
    """Return the LLM API key from settings.  Never logged or exposed."""
    try:
        from app import get_setting  # noqa: PLC0415
        return get_setting("llm_api_key", "", db=db) or ""
    except Exception:
        return ""


# ── Text hashing (change detection) ───────────────────────────────────────────


def _text_hash(text: str) -> str:
    """Return first 32 hex chars of SHA-256(text) for cache invalidation."""
    return hashlib.sha256(
        (text or "").encode("utf-8", errors="replace")
    ).hexdigest()[:32]


# ── Provider-specific API calls ────────────────────────────────────────────────


def _embed_openai(
    texts: List[str],
    api_key: str,
    model: str,
    base_url: str = "",
) -> List[List[float]]:
    """Call the OpenAI embeddings endpoint.

    Returns list of embeddings in the same order as *texts*.
    Returns [] on any failure (key never exposed in logs).
    """
    try:
        import openai  # noqa: PLC0415

        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)

        response = client.embeddings.create(input=texts, model=model)
        # Sort by index to guarantee input order
        items = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in items]
    except Exception as exc:
        # Log type only — never log the api_key or response body
        logger.warning("OpenAI embedding API call failed: %s", type(exc).__name__)
        return []


# ── Cache load/save ────────────────────────────────────────────────────────────


def load_cached_embedding(
    db,
    record_id: str,
    provider: str,
    model: str,
    text_hash: str,
) -> Optional[List[float]]:
    """Load a cached embedding from ``kb_embedding_cache``.

    Returns
    -------
    list[float]   — the stored embedding vector, or
    None          — if no entry exists, or if ``text_hash`` has changed
                    (stale cache: source text was modified).
    """
    try:
        row = db.execute(
            "SELECT embedding_json, text_hash FROM kb_embedding_cache "
            "WHERE record_id = ? AND provider = ? AND model = ?",
            (record_id, provider, model),
        ).fetchone()
        if not row:
            return None
        if row["text_hash"] != text_hash:
            return None  # stale: source text changed
        return json.loads(row["embedding_json"])
    except Exception as exc:
        logger.debug("load_cached_embedding failed for %s: %s", record_id, exc)
        return None


def save_cached_embedding(
    db,
    record: dict,
    embedding: List[float],
    provider: str,
    model: str,
) -> None:
    """Upsert an embedding into ``kb_embedding_cache``.

    Uses INSERT OR REPLACE so repeated calls are idempotent.
    Preserves the original ``created_at`` on updates.
    Fails silently — caching is best-effort.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        record_id = record.get("record_id", "")
        entry_id = record.get("entry_id", "")
        text = record.get("text", "")
        th = _text_hash(text)
        metadata = {
            "title": record.get("title", ""),
            "chunk_index": record.get("chunk_index", 0),
            "total_chunks": record.get("metadata", {}).get("total_chunks", 1),
        }
        db.execute(
            """INSERT OR REPLACE INTO kb_embedding_cache
               (record_id, entry_id, provider, model, text_hash,
                embedding_json, metadata_json, created_at, updated_at)
               VALUES (
                   ?, ?, ?, ?, ?,
                   ?, ?,
                   COALESCE(
                       (SELECT created_at FROM kb_embedding_cache WHERE record_id = ?),
                       ?
                   ),
                   ?
               )""",
            (
                record_id, entry_id, provider, model, th,
                json.dumps(embedding, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                record_id, now, now,
            ),
        )
        db.commit()
    except Exception as exc:
        logger.debug(
            "save_cached_embedding failed for %s: %s",
            record.get("record_id", "?"),
            exc,
        )


# ── Embedding generation ───────────────────────────────────────────────────────


def embed_texts(
    db,
    texts: List[str],
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> List[List[float]]:
    """Generate embeddings for *texts* using the configured provider.

    Parameters
    ----------
    db : SQLite connection
        Used to read config if *provider* / *model* are not supplied.
    texts : list[str]
        Texts to embed.  Empty/whitespace strings produce an empty vector.
    provider : str | None
        Override provider.  Falls back to settings if None.
    model : str | None
        Override model.  Falls back to settings if None.

    Returns
    -------
    list[list[float]]
        One embedding per input text, in the same order.
        On unrecoverable failure returns ``[]``.
        Never exposes the API key in return values or logs.

    Notes
    -----
    - Returns ``[]`` immediately if provider is not in the supported set.
    - Returns ``[]`` immediately if no API key is configured.
    """
    if not texts:
        return []

    try:
        cfg = get_embedding_provider_config(db)
        _provider = (provider or cfg["provider"]).strip().lower()
        _model = (model or cfg["model"]).strip()
        _base_url = cfg.get("base_url", "")

        if _provider not in _SUPPORTED_EMBEDDING_PROVIDERS:
            logger.warning(
                "Embedding provider '%s' is not supported. Supported: %s",
                _provider,
                sorted(_SUPPORTED_EMBEDDING_PROVIDERS),
            )
            return []

        api_key = _get_api_key(db)
        if not api_key:
            logger.warning(
                "No API key configured for embedding provider '%s'", _provider
            )
            return []

        # Build list of (original_index, text) for non-empty texts only
        non_empty: List[tuple] = [
            (i, t) for i, t in enumerate(texts) if t and t.strip()
        ]
        if not non_empty:
            return [[] for _ in texts]

        # Batch the non-empty texts to respect _BATCH_SIZE
        flat_texts = [t for _, t in non_empty]
        all_embeddings: List[List[float]] = []

        for start in range(0, len(flat_texts), _BATCH_SIZE):
            batch = flat_texts[start : start + _BATCH_SIZE]
            if _provider == "openai":
                batch_embs = _embed_openai(batch, api_key, _model, _base_url)
            else:
                batch_embs = []

            if not batch_embs:
                all_embeddings.extend([[] for _ in batch])
            else:
                all_embeddings.extend(batch_embs)

        # Map back to original positions
        result: List[List[float]] = [[] for _ in texts]
        for out_idx, (orig_idx, _) in enumerate(non_empty):
            if out_idx < len(all_embeddings):
                result[orig_idx] = all_embeddings[out_idx]

        return result

    except Exception as exc:
        logger.warning("embed_texts failed: %s", type(exc).__name__)
        return []


# ── Orchestrator ───────────────────────────────────────────────────────────────


def get_or_create_embeddings_for_records(
    db,
    records: List[dict],
    provider: str,
    model: str,
) -> List[dict]:
    """Return records with an ``"embedding"`` field populated.

    For each record:
    1. Look up ``kb_embedding_cache`` by (record_id, provider, model, text_hash).
    2. If found and text_hash matches → use cached value.
    3. Otherwise → call ``embed_texts`` in batch, save results to cache.

    Parameters
    ----------
    records : list[dict]
        Semantic KB records from ``build_semantic_kb_records``.
    provider : str
        Embedding provider (e.g. "openai").
    model : str
        Embedding model name.

    Returns
    -------
    list[dict]
        Shallow copies of input records, each with ``"embedding": list[float]``
        added.  Records that fail get ``"embedding": []``.
    """
    if not records:
        return []

    result = [dict(r) for r in records]  # shallow copy — do not mutate originals

    # Phase 1: cache lookup
    missing_indices: List[int] = []
    for i, rec in enumerate(result):
        text = rec.get("text", "")
        th = _text_hash(text)
        cached = load_cached_embedding(db, rec["record_id"], provider, model, th)
        if cached is not None:
            result[i]["embedding"] = cached
        else:
            result[i]["embedding"] = []
            missing_indices.append(i)

    if not missing_indices:
        return result

    # Phase 2: generate missing in one batch
    texts_to_embed = [result[i]["text"] for i in missing_indices]
    embeddings = embed_texts(db, texts_to_embed, provider=provider, model=model)

    for batch_idx, orig_idx in enumerate(missing_indices):
        emb = embeddings[batch_idx] if batch_idx < len(embeddings) else []
        result[orig_idx]["embedding"] = emb
        if emb:
            try:
                save_cached_embedding(db, result[orig_idx], emb, provider, model)
            except Exception as exc:
                logger.debug(
                    "Failed to cache embedding for record %s: %s",
                    result[orig_idx].get("record_id", "?"),
                    exc,
                )

    return result
