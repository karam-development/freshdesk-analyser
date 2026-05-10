"""Tests for ai/kb_semantic_search.py — PR 38.

Pure Python, no network, no DB.
"""
from __future__ import annotations

import math

import pytest

from ai.kb_semantic_search import (
    build_semantic_evidence_entries,
    cosine_similarity,
    semantic_search_kb_records,
)


# ── cosine_similarity ──────────────────────────────────────────────────────────


class TestCosineSimilarity:

    def test_identical_vectors_return_one(self):
        v = [1.0, 0.5, 0.3]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_opposite_vectors_return_minus_one(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-9

    def test_known_values(self):
        a = [1.0, 1.0]
        b = [1.0, 0.0]
        # cos(45°) = 1/sqrt(2) ≈ 0.7071
        expected = 1.0 / math.sqrt(2)
        assert abs(cosine_similarity(a, b) - expected) < 1e-6

    def test_empty_a_returns_zero(self):
        assert cosine_similarity([], [1.0]) == 0.0

    def test_empty_b_returns_zero(self):
        assert cosine_similarity([1.0], []) == 0.0

    def test_both_empty_returns_zero(self):
        assert cosine_similarity([], []) == 0.0

    def test_mismatched_dimensions_returns_zero(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_both_zero_vectors_return_zero(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_result_in_minus_one_to_one_range(self):
        import random
        random.seed(42)
        for _ in range(20):
            a = [random.uniform(-1, 1) for _ in range(8)]
            b = [random.uniform(-1, 1) for _ in range(8)]
            r = cosine_similarity(a, b)
            assert -1.0 - 1e-9 <= r <= 1.0 + 1e-9

    def test_never_raises_on_bad_input(self):
        assert cosine_similarity(None, [1.0]) == 0.0  # type: ignore
        assert cosine_similarity([1.0], None) == 0.0  # type: ignore


# ── semantic_search_kb_records ─────────────────────────────────────────────────


def _make_record(record_id, title, embedding):
    return {
        "record_id": record_id,
        "entry_id": record_id,
        "title": title,
        "category": "product",
        "evidence_type": "general_evidence",
        "text": title,
        "source_text": title,
        "embedding": embedding,
    }


class TestSemanticSearchKbRecords:

    def test_empty_query_returns_empty(self):
        records = [_make_record("r1", "T1", [1.0, 0.0])]
        assert semantic_search_kb_records([], records) == []

    def test_empty_records_returns_empty(self):
        assert semantic_search_kb_records([1.0, 0.0], []) == []

    def test_top_k_limits_results(self):
        records = [_make_record(f"r{i}", f"T{i}", [1.0, float(i) * 0.01]) for i in range(10)]
        query = [1.0, 0.0]
        results = semantic_search_kb_records(query, records, top_k=3, min_score=0.0)
        assert len(results) <= 3

    def test_min_score_filters_low_similarity(self):
        # Orthogonal vector — similarity = 0.0
        records = [_make_record("r1", "T1", [0.0, 1.0])]
        query = [1.0, 0.0]
        results = semantic_search_kb_records(query, records, top_k=5, min_score=0.5)
        assert results == []

    def test_results_sorted_by_similarity_descending(self):
        # r1: sim ≈ 1.0 (identical), r2: sim = cos(45°) ≈ 0.71
        q = [1.0, 0.0]
        records = [
            _make_record("r1", "T1", [1.0, 0.0]),
            _make_record("r2", "T2", [1.0, 1.0]),
        ]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.0)
        assert results[0]["record"]["record_id"] == "r1"
        assert results[1]["record"]["record_id"] == "r2"
        assert results[0]["similarity"] >= results[1]["similarity"]

    def test_result_contains_record_and_similarity(self):
        q = [1.0, 0.0]
        records = [_make_record("r1", "T1", [1.0, 0.0])]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.0)
        assert len(results) == 1
        r = results[0]
        assert "record" in r
        assert "similarity" in r
        assert r["record"]["record_id"] == "r1"
        assert abs(r["similarity"] - 1.0) < 1e-9

    def test_records_without_embedding_key_are_skipped(self):
        records = [
            {"record_id": "r1", "title": "T1"},  # no embedding key
            _make_record("r2", "T2", [1.0, 0.0]),
        ]
        q = [1.0, 0.0]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.0)
        assert all(r["record"]["record_id"] == "r2" for r in results)

    def test_records_with_empty_embedding_are_skipped(self):
        records = [
            _make_record("r1", "T1", []),
            _make_record("r2", "T2", [1.0, 0.0]),
        ]
        q = [1.0, 0.0]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.0)
        assert len(results) == 1
        assert results[0]["record"]["record_id"] == "r2"

    def test_non_dict_records_are_skipped(self):
        records = [
            "not a dict",
            _make_record("r1", "T1", [1.0, 0.0]),
        ]
        q = [1.0, 0.0]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.0)  # type: ignore
        assert len(results) == 1

    def test_min_score_boundary_exact_match(self):
        # similarity = 1.0, min_score = 1.0 → should include
        q = [1.0, 0.0]
        records = [_make_record("r1", "T1", [1.0, 0.0])]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=1.0)
        assert len(results) == 1

    def test_min_score_just_above_similarity_excludes(self):
        q = [1.0, 0.0]
        # sim ≈ 0.707
        records = [_make_record("r1", "T1", [1.0, 1.0])]
        results = semantic_search_kb_records(q, records, top_k=5, min_score=0.999)
        assert results == []


# ── build_semantic_evidence_entries ───────────────────────────────────────────


class TestBuildSemanticEvidenceEntries:

    def test_empty_matches_returns_empty(self):
        assert build_semantic_evidence_entries([]) == []

    def test_none_matches_returns_empty(self):
        assert build_semantic_evidence_entries(None) == []  # type: ignore

    def test_basic_entry_has_required_fields(self):
        matches = [
            {
                "record": _make_record("123", "My Title", [1.0, 0.0]),
                "similarity": 0.87,
            }
        ]
        entries = build_semantic_evidence_entries(matches)
        assert len(entries) == 1
        e = entries[0]
        assert e["title"] == "My Title"
        assert e["source"] == "semantic"
        assert e["entry_id"] == "123"
        assert e["score"] == round(0.87 * 100, 1)
        assert "semantic_similarity:0.870" in e["score_reasons"][0]

    def test_matched_terms_is_empty_list(self):
        matches = [{"record": _make_record("1", "T", [1.0, 0.0]), "similarity": 0.8}]
        entries = build_semantic_evidence_entries(matches)
        assert entries[0]["matched_terms"] == []

    def test_score_reasons_contains_similarity(self):
        matches = [{"record": _make_record("1", "T", [1.0, 0.0]), "similarity": 0.75}]
        entries = build_semantic_evidence_entries(matches)
        assert any("0.750" in r for r in entries[0]["score_reasons"])

    def test_evidence_type_preserved(self):
        rec = _make_record("1", "T", [1.0, 0.0])
        rec["evidence_type"] = "legal_evidence"
        matches = [{"record": rec, "similarity": 0.9}]
        entries = build_semantic_evidence_entries(matches)
        assert entries[0]["evidence_type"] == "legal_evidence"

    def test_evidence_type_defaults_to_general(self):
        rec = _make_record("1", "T", [1.0, 0.0])
        del rec["evidence_type"]
        matches = [{"record": rec, "similarity": 0.9}]
        entries = build_semantic_evidence_entries(matches)
        assert entries[0]["evidence_type"] == "general_evidence"

    def test_non_dict_match_skipped(self):
        matches = ["not a dict", {"record": _make_record("1", "T", [1.0]), "similarity": 0.8}]
        entries = build_semantic_evidence_entries(matches)  # type: ignore
        assert len(entries) == 1

    def test_score_is_0_to_100_scale(self):
        matches = [{"record": _make_record("1", "T", [1.0, 0.0]), "similarity": 0.75}]
        entries = build_semantic_evidence_entries(matches)
        assert 0 <= entries[0]["score"] <= 100
