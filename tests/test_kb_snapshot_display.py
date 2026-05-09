"""Unit tests for ai/kb_snapshot_display.py (PR 25).

Covers:
- Invalid/empty container → has_data=False
- Single flow → has_data=True
- latest_flow preserved
- Canonical flow order: ingest, draft, regeneration, analysis
- Unknown flows go last (alphabetically)
- entry_count, total_entries, flows_present correct
- has_different_flows True when >1 flow
- Max 8 entries per flow
- Max 8 matched_terms per entry
- Max 8 score_reasons per entry
- Snippet max 180 chars
- Invalid entries skipped / defensive
- Acceptance scenario with ingest + draft snapshots
"""
from __future__ import annotations

import pytest

from ai.kb_snapshot_display import build_kb_snapshot_flow_review


# ── Helpers ────────────────────────────────────────────────────────────────────

_MISSING = object()


def _entry(title="T", evidence_type="workaround_evidence", score=10,
           matched_terms=_MISSING, score_reasons=_MISSING, snippet="A snippet."):
    return {
        "title": title,
        "evidence_type": evidence_type,
        "score": score,
        "matched_terms": ["term:x"] if matched_terms is _MISSING else matched_terms,
        "score_reasons": ["title:x +4"] if score_reasons is _MISSING else score_reasons,
        "snippet": snippet,
    }


def _snap(flow, entries=None, created_at="2026-01-01T10:00:00Z"):
    e = entries if entries is not None else [_entry()]
    # Build evidence_types defensively — entries list may contain non-dicts.
    ev_types = list({x["evidence_type"] for x in e if isinstance(x, dict)})
    return {
        "flow": flow,
        "created_at": created_at,
        "entries": e,
        "summary": {
            "count": len(e),
            "evidence_types": ev_types,
        },
    }


def _container(snaps: dict, latest_flow: str = "") -> dict:
    return {
        "snapshots": snaps,
        "latest_flow": latest_flow or (list(snaps)[-1] if snaps else ""),
        "updated_at": "2026-01-01T10:05:00Z",
    }


# ── Invalid / empty input ──────────────────────────────────────────────────────


def test_none_container_returns_has_data_false():
    result = build_kb_snapshot_flow_review(None)
    assert result["has_data"] is False


def test_empty_dict_returns_has_data_false():
    result = build_kb_snapshot_flow_review({})
    assert result["has_data"] is False


def test_no_snapshots_key_returns_has_data_false():
    result = build_kb_snapshot_flow_review({"latest_flow": "draft", "updated_at": ""})
    assert result["has_data"] is False


def test_empty_snapshots_dict_returns_has_data_false():
    result = build_kb_snapshot_flow_review({"snapshots": {}, "latest_flow": "", "updated_at": ""})
    assert result["has_data"] is False


def test_snapshots_not_dict_returns_has_data_false():
    result = build_kb_snapshot_flow_review({"snapshots": "bad", "latest_flow": ""})
    assert result["has_data"] is False


def test_non_dict_container_returns_has_data_false():
    result = build_kb_snapshot_flow_review("not-a-dict")
    assert result["has_data"] is False


# ── Single flow ────────────────────────────────────────────────────────────────


def test_single_flow_returns_has_data_true():
    c = _container({"draft": _snap("draft")})
    result = build_kb_snapshot_flow_review(c)
    assert result["has_data"] is True


def test_single_flow_entry_count_correct():
    c = _container({"draft": _snap("draft", entries=[_entry(), _entry(title="B")])})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entry_count"] == 2


def test_single_flow_total_entries_correct():
    c = _container({"ingest": _snap("ingest", entries=[_entry(), _entry()])})
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["total_entries"] == 2


def test_single_flow_flows_present():
    c = _container({"ingest": _snap("ingest")})
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["flows_present"] == ["ingest"]


def test_single_flow_has_different_flows_false():
    c = _container({"draft": _snap("draft")})
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["has_different_flows"] is False


# ── latest_flow preserved ──────────────────────────────────────────────────────


def test_latest_flow_preserved():
    c = _container({"ingest": _snap("ingest"), "draft": _snap("draft")}, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    assert result["latest_flow"] == "draft"


def test_latest_flow_empty_string_allowed():
    c = _container({"ingest": _snap("ingest")}, latest_flow="")
    # latest_flow from container is empty but snapshots has ingest
    result = build_kb_snapshot_flow_review(c)
    assert result["has_data"] is True


# ── Canonical flow order ───────────────────────────────────────────────────────


def test_canonical_flow_order_ingest_before_draft():
    c = _container({"draft": _snap("draft"), "ingest": _snap("ingest")}, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    flow_names = [f["flow"] for f in result["flows"]]
    assert flow_names.index("ingest") < flow_names.index("draft")


def test_canonical_flow_order_all_four():
    c = _container({
        "analysis": _snap("analysis"),
        "regeneration": _snap("regeneration"),
        "draft": _snap("draft"),
        "ingest": _snap("ingest"),
    }, latest_flow="analysis")
    result = build_kb_snapshot_flow_review(c)
    flow_names = [f["flow"] for f in result["flows"]]
    assert flow_names == ["ingest", "draft", "regeneration", "analysis"]


def test_unknown_flows_go_last():
    c = _container({
        "custom_flow": _snap("custom_flow"),
        "ingest": _snap("ingest"),
        "draft": _snap("draft"),
    }, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    flow_names = [f["flow"] for f in result["flows"]]
    assert flow_names == ["ingest", "draft", "custom_flow"]


def test_multiple_unknown_flows_sorted_alphabetically():
    c = _container({
        "zebra": _snap("zebra"),
        "alpha": _snap("alpha"),
        "ingest": _snap("ingest"),
    }, latest_flow="ingest")
    result = build_kb_snapshot_flow_review(c)
    flow_names = [f["flow"] for f in result["flows"]]
    assert flow_names == ["ingest", "alpha", "zebra"]


# ── Summary correctness ────────────────────────────────────────────────────────


def test_flow_count_correct():
    c = _container({
        "ingest": _snap("ingest"),
        "draft": _snap("draft"),
        "analysis": _snap("analysis"),
    }, latest_flow="analysis")
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["flow_count"] == 3


def test_total_entries_summed_across_flows():
    c = _container({
        "ingest": _snap("ingest", entries=[_entry(), _entry()]),
        "draft": _snap("draft", entries=[_entry(), _entry(), _entry()]),
    }, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["total_entries"] == 5


def test_flows_present_matches_ordered_flows():
    c = _container({
        "draft": _snap("draft"),
        "ingest": _snap("ingest"),
    }, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["flows_present"] == ["ingest", "draft"]


def test_has_different_flows_true_with_two_flows():
    c = _container({
        "ingest": _snap("ingest"),
        "draft": _snap("draft"),
    }, latest_flow="draft")
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["has_different_flows"] is True


def test_has_different_flows_false_with_one_flow():
    c = _container({"ingest": _snap("ingest")})
    result = build_kb_snapshot_flow_review(c)
    assert result["summary"]["has_different_flows"] is False


# ── Per-entry caps ─────────────────────────────────────────────────────────────


def test_max_entries_per_flow_is_8():
    entries = [_entry(title=f"E{i}") for i in range(12)]
    c = _container({"draft": _snap("draft", entries=entries)})
    result = build_kb_snapshot_flow_review(c)
    assert len(result["flows"][0]["entries"]) == 8


def test_entry_count_reflects_capped_entries():
    entries = [_entry(title=f"E{i}") for i in range(12)]
    c = _container({"draft": _snap("draft", entries=entries)})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entry_count"] == 8


def test_max_matched_terms_is_8():
    entry = _entry(matched_terms=[f"t{i}" for i in range(15)])
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert len(result["flows"][0]["entries"][0]["matched_terms"]) == 8


def test_max_score_reasons_is_8():
    entry = _entry(score_reasons=[f"r{i} +1" for i in range(15)])
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert len(result["flows"][0]["entries"][0]["score_reasons"]) == 8


def test_snippet_max_180():
    entry = _entry(snippet="x" * 250)
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    snippet = result["flows"][0]["entries"][0]["snippet"]
    assert len(snippet) <= 181  # 180 + ellipsis
    assert snippet.endswith("…")


def test_snippet_short_not_truncated():
    entry = _entry(snippet="Short.")
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entries"][0]["snippet"] == "Short."


def test_snippet_from_content_field_when_no_snippet():
    entry = _entry(snippet="")
    entry["content"] = "Fallback content text."
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entries"][0]["snippet"] == "Fallback content text."


# ── Defensive handling ─────────────────────────────────────────────────────────


def test_non_dict_entry_skipped():
    entries = ["bad", None, _entry()]
    c = _container({"draft": _snap("draft", entries=entries)})
    result = build_kb_snapshot_flow_review(c)
    assert len(result["flows"][0]["entries"]) == 1


def test_non_dict_snapshot_skipped():
    c = {
        "snapshots": {"ingest": "not-a-dict", "draft": _snap("draft")},
        "latest_flow": "draft",
        "updated_at": "",
    }
    result = build_kb_snapshot_flow_review(c)
    flow_names = [f["flow"] for f in result["flows"]]
    assert "ingest" not in flow_names
    assert "draft" in flow_names


def test_matched_terms_none_becomes_empty():
    entry = _entry(matched_terms=None)
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entries"][0]["matched_terms"] == []


def test_score_reasons_non_list_becomes_empty():
    entry = _entry(score_reasons=42)
    c = _container({"draft": _snap("draft", entries=[entry])})
    result = build_kb_snapshot_flow_review(c)
    assert result["flows"][0]["entries"][0]["score_reasons"] == []


def test_empty_entries_list_in_flow_still_included():
    c = _container({"ingest": _snap("ingest", entries=[])})
    result = build_kb_snapshot_flow_review(c)
    # The flow itself is still present with 0 entries
    assert result["flows"][0]["flow"] == "ingest"
    assert result["flows"][0]["entry_count"] == 0


def test_evidence_types_in_flow_sorted():
    entries = [
        _entry(evidence_type="workaround_evidence"),
        _entry(evidence_type="legal_evidence"),
        _entry(evidence_type="product_evidence"),
    ]
    c = _container({"draft": _snap("draft", entries=entries)})
    result = build_kb_snapshot_flow_review(c)
    types = result["flows"][0]["evidence_types"]
    assert types == sorted(types)


# ── Acceptance scenario ────────────────────────────────────────────────────────


def test_acceptance_ingest_plus_draft():
    """Full acceptance scenario with ingest + draft snapshots."""
    container = {
        "snapshots": {
            "ingest": {
                "flow": "ingest",
                "created_at": "2026-01-01T10:00:00Z",
                "entries": [
                    {
                        "title": "Existing setting for staff note",
                        "evidence_type": "existing_setting_evidence",
                        "score": 12,
                        "matched_terms": ["title:staff"],
                        "score_reasons": ["template_phrase:title +5"],
                        "snippet": "Use the existing dropdown setting.",
                    }
                ],
                "summary": {"count": 1, "evidence_types": ["existing_setting_evidence"]},
            },
            "draft": {
                "flow": "draft",
                "created_at": "2026-01-01T10:05:00Z",
                "entries": [
                    {
                        "title": "Existing workaround for staff wording",
                        "evidence_type": "workaround_evidence",
                        "score": 14,
                        "matched_terms": ["title:staff", "content:editable"],
                        "score_reasons": ["title:staff +4", "evidence_type:workaround +3"],
                        "snippet": "Use the editable text field.",
                    }
                ],
                "summary": {"count": 1, "evidence_types": ["workaround_evidence"]},
            },
        },
        "latest_flow": "draft",
        "updated_at": "2026-01-01T10:05:00Z",
    }

    result = build_kb_snapshot_flow_review(container)

    assert result["has_data"] is True
    assert result["latest_flow"] == "draft"
    assert result["summary"]["flow_count"] == 2
    assert result["summary"]["total_entries"] == 2
    assert result["summary"]["has_different_flows"] is True
    assert result["summary"]["flows_present"] == ["ingest", "draft"]

    # ingest flow comes first
    assert result["flows"][0]["flow"] == "ingest"
    assert result["flows"][0]["entry_count"] == 1
    assert result["flows"][0]["entries"][0]["title"] == "Existing setting for staff note"
    assert result["flows"][0]["entries"][0]["score"] == 12
    assert result["flows"][0]["entries"][0]["evidence_type"] == "existing_setting_evidence"

    # draft flow comes second
    assert result["flows"][1]["flow"] == "draft"
    assert result["flows"][1]["entry_count"] == 1
    assert result["flows"][1]["entries"][0]["title"] == "Existing workaround for staff wording"
    assert result["flows"][1]["entries"][0]["score"] == 14
    assert result["flows"][1]["entries"][0]["score_reasons"] == [
        "title:staff +4", "evidence_type:workaround +3"
    ]
