"""Semantic KB search helpers — cosine similarity, search, evidence formatting.

No API calls.  No DB reads or writes.  Pure Python + math.

Public functions
----------------
cosine_similarity(a, b) -> float
    Cosine similarity between two float vectors.

semantic_search_kb_records(query_embedding, embedded_records, top_k, min_score) -> list[dict]
    Rank embedded records by cosine similarity to a query embedding.

build_semantic_evidence_entries(matches) -> list[dict]
    Convert semantic matches to the KB evidence entry format expected by
    build_kb_evidence_review and retrieve_hybrid_kb_entries.
"""
from __future__ import annotations

import math
from typing import List


# ── Cosine similarity ──────────────────────────────────────────────────────────


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two float vectors.

    Returns 0.0 for zero-length or mismatched vectors.
    Never raises.
    """
    try:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)
    except Exception:
        return 0.0


# ── Semantic search ────────────────────────────────────────────────────────────


def semantic_search_kb_records(
    query_embedding: List[float],
    embedded_records: List[dict],
    top_k: int = 5,
    min_score: float = 0.65,
) -> List[dict]:
    """Rank embedded records by cosine similarity to *query_embedding*.

    Parameters
    ----------
    query_embedding : list[float]
        Embedding for the search query.
    embedded_records : list[dict]
        Records from ``get_or_create_embeddings_for_records``.  Each must
        contain an ``"embedding"`` key with a list[float].
    top_k : int
        Maximum number of results to return (default 5).
    min_score : float
        Minimum cosine similarity threshold [0, 1] (default 0.65).

    Returns
    -------
    list[dict]
        Sorted by similarity descending.  Each element:
        {
          "record": dict,      # original embedded record
          "similarity": float, # cosine similarity [0, 1]
        }
        Empty list when query_embedding is empty or no records qualify.
        Never raises.
    """
    if not query_embedding or not embedded_records:
        return []

    scored: List[dict] = []
    for rec in embedded_records:
        if not isinstance(rec, dict):
            continue
        emb = rec.get("embedding")
        if not emb or not isinstance(emb, list):
            continue
        try:
            sim = cosine_similarity(query_embedding, emb)
            if sim >= min_score:
                scored.append({"record": rec, "similarity": sim})
        except Exception:
            continue

    scored.sort(key=lambda x: -x["similarity"])
    return scored[:top_k]


# ── Evidence entry builder ─────────────────────────────────────────────────────


def build_semantic_evidence_entries(matches: List[dict]) -> List[dict]:
    """Convert semantic search matches to KB evidence entry format.

    The output entries are compatible with ``build_kb_evidence_review`` and
    ``retrieve_hybrid_kb_entries``.  Extra field ``source="semantic"`` is
    preserved through the display pipeline.

    Parameters
    ----------
    matches : list[dict]
        Output of ``semantic_search_kb_records``.

    Returns
    -------
    list[dict]
        Each entry has::

            id           : str   — entry_id from the semantic record
            entry_id     : str   — same as id
            title        : str
            category     : str
            evidence_type: str
            content      : str   — source_text from the chunk
            score        : float — similarity * 100 (0–100 scale)
            matched_terms: []    — empty for semantic results
            score_reasons: list  — ["semantic_similarity:0.XXX"]
            source       : str   — "semantic"
    """
    entries: List[dict] = []
    for match in (matches or []):
        if not isinstance(match, dict):
            continue
        rec = match.get("record") or {}
        if not isinstance(rec, dict):
            continue
        sim = float(match.get("similarity", 0.0))
        score_pct = round(sim * 100, 1)

        entries.append({
            "id": rec.get("entry_id", ""),
            "entry_id": rec.get("entry_id", ""),
            "title": rec.get("title", ""),
            "category": rec.get("category", ""),
            "evidence_type": rec.get("evidence_type") or "general_evidence",
            "content": rec.get("source_text", ""),
            "score": score_pct,
            "matched_terms": [],
            "score_reasons": [f"semantic_similarity:{sim:.3f}"],
            "source": "semantic",
        })
    return entries
