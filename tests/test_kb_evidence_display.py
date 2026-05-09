"""Tests for ai/kb_evidence_display.py — KB evidence display helper."""
from __future__ import annotations

import pytest

from ai.kb_evidence_display import build_kb_evidence_review


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _entry(
    title="KB Entry",
    category="General",
    content="Some content about the topic.",
    score=5,
    matched_terms=None,
    evidence_type="general_evidence",
):
    return {
        "title": title,
        "category": category,
        "content": content,
        "score": score,
        "matched_terms": matched_terms if matched_terms is not None else ["title:invoice"],
        "evidence_type": evidence_type,
    }


# ── Empty / invalid input ──────────────────────────────────────────────────────


def test_empty_list_has_data_false():
    result = build_kb_evidence_review([])
    assert result["has_data"] is False


def test_none_has_data_false():
    result = build_kb_evidence_review(None)
    assert result["has_data"] is False


def test_non_list_has_data_false():
    result = build_kb_evidence_review("not a list")
    assert result["has_data"] is False


def test_empty_returns_empty_entries():
    result = build_kb_evidence_review([])
    assert result["entries"] == []


def test_empty_returns_zero_count():
    result = build_kb_evidence_review([])
    assert result["summary"]["count"] == 0


def test_list_of_non_dicts_skipped():
    result = build_kb_evidence_review(["string", 42, None])
    assert result["has_data"] is False


# ── Severity mapping ───────────────────────────────────────────────────────────


def test_legal_evidence_maps_to_warning():
    result = build_kb_evidence_review([_entry(evidence_type="legal_evidence")])
    assert result["entries"][0]["severity"] == "warning"


def test_workaround_evidence_maps_to_success():
    result = build_kb_evidence_review([_entry(evidence_type="workaround_evidence")])
    assert result["entries"][0]["severity"] == "success"


def test_existing_setting_evidence_maps_to_success():
    result = build_kb_evidence_review([_entry(evidence_type="existing_setting_evidence")])
    assert result["entries"][0]["severity"] == "success"


def test_product_evidence_maps_to_info():
    result = build_kb_evidence_review([_entry(evidence_type="product_evidence")])
    assert result["entries"][0]["severity"] == "info"


def test_terminology_evidence_maps_to_neutral():
    result = build_kb_evidence_review([_entry(evidence_type="terminology_evidence")])
    assert result["entries"][0]["severity"] == "neutral"


def test_general_evidence_maps_to_neutral():
    result = build_kb_evidence_review([_entry(evidence_type="general_evidence")])
    assert result["entries"][0]["severity"] == "neutral"


def test_unknown_evidence_type_maps_to_neutral():
    result = build_kb_evidence_review([_entry(evidence_type="future_unknown_type")])
    assert result["entries"][0]["severity"] == "neutral"


# ── Badge label mapping ────────────────────────────────────────────────────────


def test_legal_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="legal_evidence")])
    assert result["entries"][0]["badge_label"] == "Legal evidence"


def test_workaround_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="workaround_evidence")])
    assert result["entries"][0]["badge_label"] == "Workaround"


def test_existing_setting_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="existing_setting_evidence")])
    assert result["entries"][0]["badge_label"] == "Existing setting"


def test_product_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="product_evidence")])
    assert result["entries"][0]["badge_label"] == "Product evidence"


def test_terminology_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="terminology_evidence")])
    assert result["entries"][0]["badge_label"] == "Terminology"


def test_general_evidence_badge_label():
    result = build_kb_evidence_review([_entry(evidence_type="general_evidence")])
    assert result["entries"][0]["badge_label"] == "General"


def test_unknown_evidence_type_badge_label_general():
    result = build_kb_evidence_review([_entry(evidence_type="made_up_type")])
    assert result["entries"][0]["badge_label"] == "General"


# ── Snippet truncation ─────────────────────────────────────────────────────────


def test_snippet_truncated_to_220():
    long_content = "a" * 500
    result = build_kb_evidence_review([_entry(content=long_content)])
    snippet = result["entries"][0]["snippet"]
    assert len(snippet) <= 221  # 220 chars + ellipsis char
    assert snippet.endswith("…")


def test_snippet_short_content_not_truncated():
    short_content = "Short content."
    result = build_kb_evidence_review([_entry(content=short_content)])
    assert result["entries"][0]["snippet"] == short_content


def test_snippet_exactly_220_not_truncated():
    content_220 = "b" * 220
    result = build_kb_evidence_review([_entry(content=content_220)])
    assert result["entries"][0]["snippet"] == content_220
    assert "…" not in result["entries"][0]["snippet"]


def test_snippet_newlines_replaced_with_spaces():
    content = "Line one.\nLine two.\nLine three."
    result = build_kb_evidence_review([_entry(content=content)])
    assert "\n" not in result["entries"][0]["snippet"]


def test_snippet_empty_content():
    result = build_kb_evidence_review([_entry(content="")])
    assert result["entries"][0]["snippet"] == ""


# ── Matched terms capping ──────────────────────────────────────────────────────


def test_matched_terms_capped_at_8():
    many_terms = [f"term:{i}" for i in range(20)]
    result = build_kb_evidence_review([_entry(matched_terms=many_terms)])
    assert len(result["entries"][0]["matched_terms"]) == 8


def test_matched_terms_fewer_than_8_preserved():
    terms = ["title:invoice", "title:date", "content:format"]
    result = build_kb_evidence_review([_entry(matched_terms=terms)])
    assert result["entries"][0]["matched_terms"] == terms


def test_matched_terms_none_becomes_empty_list():
    e = _entry()
    e["matched_terms"] = None
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["matched_terms"] == []


def test_matched_terms_non_list_becomes_empty():
    e = _entry()
    e["matched_terms"] = "not-a-list"
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["matched_terms"] == []


# ── Max entries limit ──────────────────────────────────────────────────────────


def test_max_8_entries():
    entries = [_entry(title=f"Entry {i}") for i in range(15)]
    result = build_kb_evidence_review(entries)
    assert len(result["entries"]) == 8


def test_exactly_8_entries_all_included():
    entries = [_entry(title=f"Entry {i}") for i in range(8)]
    result = build_kb_evidence_review(entries)
    assert len(result["entries"]) == 8


def test_fewer_than_8_entries_all_included():
    entries = [_entry(title=f"Entry {i}") for i in range(3)]
    result = build_kb_evidence_review(entries)
    assert len(result["entries"]) == 3


# ── Summary flags ──────────────────────────────────────────────────────────────


def test_summary_count_correct():
    entries = [_entry(evidence_type="legal_evidence"), _entry(evidence_type="general_evidence")]
    result = build_kb_evidence_review(entries)
    assert result["summary"]["count"] == 2


def test_summary_has_legal_evidence_true():
    result = build_kb_evidence_review([_entry(evidence_type="legal_evidence")])
    assert result["summary"]["has_legal_evidence"] is True


def test_summary_has_legal_evidence_false():
    result = build_kb_evidence_review([_entry(evidence_type="workaround_evidence")])
    assert result["summary"]["has_legal_evidence"] is False


def test_summary_has_workaround_evidence():
    result = build_kb_evidence_review([_entry(evidence_type="workaround_evidence")])
    assert result["summary"]["has_workaround_evidence"] is True


def test_summary_has_existing_setting():
    result = build_kb_evidence_review([_entry(evidence_type="existing_setting_evidence")])
    assert result["summary"]["has_existing_setting_evidence"] is True


def test_summary_has_product_evidence():
    result = build_kb_evidence_review([_entry(evidence_type="product_evidence")])
    assert result["summary"]["has_product_evidence"] is True


def test_summary_has_terminology_evidence():
    result = build_kb_evidence_review([_entry(evidence_type="terminology_evidence")])
    assert result["summary"]["has_terminology_evidence"] is True


def test_summary_evidence_types_sorted():
    entries = [
        _entry(evidence_type="workaround_evidence"),
        _entry(evidence_type="legal_evidence"),
    ]
    result = build_kb_evidence_review(entries)
    types = result["summary"]["evidence_types"]
    assert types == sorted(types)


def test_summary_evidence_types_unique():
    entries = [
        _entry(evidence_type="legal_evidence"),
        _entry(evidence_type="legal_evidence"),
        _entry(evidence_type="workaround_evidence"),
    ]
    result = build_kb_evidence_review(entries)
    types = result["summary"]["evidence_types"]
    assert len(types) == len(set(types))


# ── Display entry fields ───────────────────────────────────────────────────────


def test_entry_title_preserved():
    result = build_kb_evidence_review([_entry(title="My KB Title")])
    assert result["entries"][0]["title"] == "My KB Title"


def test_entry_category_preserved():
    result = build_kb_evidence_review([_entry(category="Legal requirements")])
    assert result["entries"][0]["category"] == "Legal requirements"


def test_entry_score_preserved():
    result = build_kb_evidence_review([_entry(score=14)])
    assert result["entries"][0]["score"] == 14


def test_entry_evidence_type_preserved():
    result = build_kb_evidence_review([_entry(evidence_type="workaround_evidence")])
    assert result["entries"][0]["evidence_type"] == "workaround_evidence"


def test_entry_has_data_true_with_valid_entry():
    result = build_kb_evidence_review([_entry()])
    assert result["has_data"] is True


# ── Defensive: missing / None fields ──────────────────────────────────────────


def test_missing_title_defaults_empty_string():
    e = {"evidence_type": "general_evidence", "content": "hello", "score": 1}
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["title"] == ""


def test_missing_category_defaults_empty_string():
    e = {"evidence_type": "general_evidence", "title": "T", "content": "c", "score": 2}
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["category"] == ""


def test_none_content_produces_empty_snippet():
    e = {"evidence_type": "general_evidence", "title": "T", "content": None, "score": 1}
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["snippet"] == ""


def test_none_score_defaults_to_zero():
    e = {"evidence_type": "general_evidence", "title": "T", "content": "c", "score": None}
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["score"] == 0


def test_none_evidence_type_defaults_to_general():
    e = {"title": "T", "content": "c", "score": 3, "evidence_type": None}
    result = build_kb_evidence_review([e])
    assert result["entries"][0]["evidence_type"] == "general_evidence"
    assert result["entries"][0]["badge_label"] == "General"


# ── Acceptance scenario ────────────────────────────────────────────────────────


def test_acceptance_scenario():
    """Full acceptance scenario from PR 21 spec."""
    entries = [
        {
            "title": "Existing workaround for staff cost wording",
            "category": "workaround",
            "content": (
                "If the client wants custom wording, use the editable text field "
                "instead of changing the global default."
            ),
            "score": 14,
            "matched_terms": ["title:staff", "title:wording", "content:editable"],
            "evidence_type": "workaround_evidence",
        }
    ]

    result = build_kb_evidence_review(entries)

    assert result["has_data"] is True
    assert result["summary"]["count"] == 1
    assert result["summary"]["has_workaround_evidence"] is True
    assert result["summary"]["has_legal_evidence"] is False

    entry = result["entries"][0]
    assert entry["badge_label"] == "Workaround"
    assert entry["severity"] == "success"
    assert "editable text field" in entry["snippet"]
    assert entry["matched_terms"] == ["title:staff", "title:wording", "content:editable"]
    assert entry["title"] == "Existing workaround for staff cost wording"
    assert entry["score"] == 14
