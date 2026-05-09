"""Unit tests for ai/kb_evidence_snapshot.py (PR 24).

Covers:
- build_kb_evidence_snapshot: empty entries, caps, snippet truncation,
  invalid entries skipped, flow preserved, created_at present.
- merge_kb_evidence_snapshot: invalid existing JSON, preserves flows,
  updates latest_flow.
- load_kb_evidence_snapshot: invalid inputs return stable empty shape.
- Acceptance scenario with a workaround entry.
"""
from __future__ import annotations

import json

import pytest

from ai.kb_evidence_snapshot import (
    build_kb_evidence_snapshot,
    load_kb_evidence_snapshot,
    merge_kb_evidence_snapshot,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _workaround_entry(**overrides):
    base = {
        "id": 12,
        "title": "Existing workaround for staff cost wording",
        "category": "workaround",
        "content": (
            "If the client wants custom wording, use the editable text field "
            "instead of changing the global default."
        ),
        "score": 14,
        "matched_terms": ["title:staff", "title:wording", "content:editable"],
        "score_reasons": ["title:staff +4", "template_phrase:title +5"],
        "evidence_type": "workaround_evidence",
    }
    base.update(overrides)
    return base


# ── build_kb_evidence_snapshot ─────────────────────────────────────────────────


def test_build_snapshot_empty_entries_returns_stable_shape():
    result = build_kb_evidence_snapshot([])
    assert "flow" in result
    assert "created_at" in result
    assert result["entries"] == []
    assert result["summary"]["count"] == 0


def test_build_snapshot_none_entries_returns_stable_shape():
    result = build_kb_evidence_snapshot(None)
    assert result["entries"] == []


def test_build_snapshot_not_list_returns_stable_shape():
    result = build_kb_evidence_snapshot("not-a-list")
    assert result["entries"] == []


def test_build_snapshot_caps_entries_at_8():
    entries = [_workaround_entry(title=f"Entry {i}") for i in range(12)]
    result = build_kb_evidence_snapshot(entries)
    assert len(result["entries"]) == 8


def test_build_snapshot_snippet_max_300():
    long_content = "x" * 400
    entry = _workaround_entry(content=long_content)
    result = build_kb_evidence_snapshot([entry])
    snippet = result["entries"][0]["snippet"]
    assert len(snippet) <= 301  # 300 + ellipsis char
    assert snippet.endswith("…")


def test_build_snapshot_snippet_short_not_truncated():
    short_content = "Short content."
    entry = _workaround_entry(content=short_content)
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["snippet"] == "Short content."


def test_build_snapshot_matched_terms_max_12():
    entry = _workaround_entry(matched_terms=[f"term{i}" for i in range(20)])
    result = build_kb_evidence_snapshot([entry])
    assert len(result["entries"][0]["matched_terms"]) == 12


def test_build_snapshot_score_reasons_max_12():
    entry = _workaround_entry(score_reasons=[f"reason{i}" for i in range(20)])
    result = build_kb_evidence_snapshot([entry])
    assert len(result["entries"][0]["score_reasons"]) == 12


def test_build_snapshot_invalid_entry_skipped():
    entries = ["not-a-dict", None, _workaround_entry()]
    result = build_kb_evidence_snapshot(entries)
    assert len(result["entries"]) == 1


def test_build_snapshot_flow_preserved():
    result = build_kb_evidence_snapshot([_workaround_entry()], flow="draft")
    assert result["flow"] == "draft"


def test_build_snapshot_empty_flow_preserved():
    result = build_kb_evidence_snapshot([_workaround_entry()], flow="")
    assert result["flow"] == ""


def test_build_snapshot_created_at_present():
    result = build_kb_evidence_snapshot([_workaround_entry()])
    assert result["created_at"]
    assert "T" in result["created_at"]  # ISO format


def test_build_snapshot_summary_count():
    entries = [_workaround_entry(title=f"E{i}") for i in range(3)]
    result = build_kb_evidence_snapshot(entries)
    assert result["summary"]["count"] == 3


def test_build_snapshot_summary_evidence_types_sorted():
    entries = [
        _workaround_entry(evidence_type="product_evidence"),
        _workaround_entry(evidence_type="workaround_evidence"),
        _workaround_entry(evidence_type="legal_evidence"),
    ]
    result = build_kb_evidence_snapshot(entries)
    types = result["summary"]["evidence_types"]
    assert types == sorted(types)


def test_build_snapshot_entry_has_id():
    result = build_kb_evidence_snapshot([_workaround_entry()])
    assert "id" in result["entries"][0]
    assert result["entries"][0]["id"] == 12


def test_build_snapshot_entry_id_none_allowed():
    entry = _workaround_entry()
    del entry["id"]
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["id"] is None


def test_build_snapshot_matched_terms_none_becomes_empty():
    entry = _workaround_entry(matched_terms=None)
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["matched_terms"] == []


def test_build_snapshot_score_reasons_none_becomes_empty():
    entry = _workaround_entry(score_reasons=None)
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["score_reasons"] == []


def test_build_snapshot_matched_terms_non_list_becomes_empty():
    entry = _workaround_entry(matched_terms="bad")
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["matched_terms"] == []


def test_build_snapshot_score_reasons_non_list_becomes_empty():
    entry = _workaround_entry(score_reasons=42)
    result = build_kb_evidence_snapshot([entry])
    assert result["entries"][0]["score_reasons"] == []


# ── merge_kb_evidence_snapshot ─────────────────────────────────────────────────


def test_merge_invalid_existing_json_creates_stable_shape():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="draft")
    result = merge_kb_evidence_snapshot("not-valid-json", snap)
    assert "snapshots" in result
    assert "latest_flow" in result
    assert "updated_at" in result


def test_merge_none_existing_creates_container():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    result = merge_kb_evidence_snapshot(None, snap)
    assert "ingest" in result["snapshots"]
    assert result["latest_flow"] == "ingest"


def test_merge_empty_string_existing_creates_container():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="draft")
    result = merge_kb_evidence_snapshot("", snap)
    assert "draft" in result["snapshots"]


def test_merge_empty_braces_existing_creates_container():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="analysis")
    result = merge_kb_evidence_snapshot("{}", snap)
    assert "analysis" in result["snapshots"]


def test_merge_preserves_previous_flow_snapshots():
    snap_ingest = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    container1 = merge_kb_evidence_snapshot(None, snap_ingest)

    snap_draft = build_kb_evidence_snapshot([_workaround_entry(title="Draft entry")], flow="draft")
    container2 = merge_kb_evidence_snapshot(json.dumps(container1), snap_draft)

    assert "ingest" in container2["snapshots"]
    assert "draft" in container2["snapshots"]


def test_merge_updates_latest_flow():
    snap1 = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    c1 = merge_kb_evidence_snapshot(None, snap1)

    snap2 = build_kb_evidence_snapshot([_workaround_entry()], flow="analysis")
    c2 = merge_kb_evidence_snapshot(json.dumps(c1), snap2)

    assert c2["latest_flow"] == "analysis"


def test_merge_empty_flow_uses_unknown_key():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="")
    result = merge_kb_evidence_snapshot(None, snap)
    assert "unknown" in result["snapshots"]
    assert result["latest_flow"] == "unknown"


def test_merge_overwrites_same_flow():
    snap1 = build_kb_evidence_snapshot([_workaround_entry(title="Old")], flow="draft")
    c1 = merge_kb_evidence_snapshot(None, snap1)

    snap2 = build_kb_evidence_snapshot([_workaround_entry(title="New")], flow="draft")
    c2 = merge_kb_evidence_snapshot(json.dumps(c1), snap2)

    assert c2["snapshots"]["draft"]["entries"][0]["title"] == "New"


def test_merge_updated_at_present():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    result = merge_kb_evidence_snapshot(None, snap)
    assert result["updated_at"]


def test_merge_accepts_dict_existing():
    snap1 = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    c1 = merge_kb_evidence_snapshot(None, snap1)

    snap2 = build_kb_evidence_snapshot([_workaround_entry()], flow="draft")
    c2 = merge_kb_evidence_snapshot(c1, snap2)  # pass dict directly

    assert "ingest" in c2["snapshots"]
    assert "draft" in c2["snapshots"]


def test_merge_non_dict_new_snapshot_returns_container():
    result = merge_kb_evidence_snapshot(None, "bad-snapshot")
    assert "snapshots" in result


# ── load_kb_evidence_snapshot ──────────────────────────────────────────────────


def test_load_none_returns_stable_empty_shape():
    result = load_kb_evidence_snapshot(None)
    assert result == {"snapshots": {}, "latest_flow": "", "updated_at": ""}


def test_load_empty_string_returns_stable_shape():
    result = load_kb_evidence_snapshot("")
    assert result["snapshots"] == {}


def test_load_empty_braces_returns_stable_shape():
    result = load_kb_evidence_snapshot("{}")
    assert result["snapshots"] == {}


def test_load_invalid_json_returns_stable_shape():
    result = load_kb_evidence_snapshot("not-json{{{{")
    assert result["snapshots"] == {}
    assert result["latest_flow"] == ""


def test_load_valid_json_roundtrip():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="draft")
    container = merge_kb_evidence_snapshot(None, snap)
    raw = json.dumps(container)

    loaded = load_kb_evidence_snapshot(raw)
    assert loaded["latest_flow"] == "draft"
    assert "draft" in loaded["snapshots"]


def test_load_dict_input_works():
    snap = build_kb_evidence_snapshot([_workaround_entry()], flow="ingest")
    container = merge_kb_evidence_snapshot(None, snap)

    loaded = load_kb_evidence_snapshot(container)
    assert loaded["latest_flow"] == "ingest"


def test_load_snapshots_key_missing_returns_empty_dict():
    raw = json.dumps({"latest_flow": "draft", "updated_at": "2024-01-01T00:00:00+00:00"})
    loaded = load_kb_evidence_snapshot(raw)
    assert loaded["snapshots"] == {}


# ── Acceptance scenario ────────────────────────────────────────────────────────


def test_acceptance_workaround_entry_full_round_trip():
    """Simulate draft flow building and persisting a snapshot."""
    entry = _workaround_entry()
    snap = build_kb_evidence_snapshot([entry], flow="draft")

    # snapshot has correct structure
    assert snap["flow"] == "draft"
    assert snap["summary"]["count"] == 1
    assert snap["entries"][0]["title"] == "Existing workaround for staff cost wording"
    assert snap["entries"][0]["evidence_type"] == "workaround_evidence"
    assert snap["entries"][0]["score"] == 14
    assert len(snap["entries"][0]["snippet"]) <= 301
    # content is stored as snippet (not full content)
    assert "editable text field" in snap["entries"][0]["snippet"]

    # merge into fresh container
    container = merge_kb_evidence_snapshot(None, snap)
    assert container["latest_flow"] == "draft"
    assert "draft" in container["snapshots"]

    # serialise → deserialise (simulates DB round trip)
    raw_json = json.dumps(container, ensure_ascii=False)
    loaded = load_kb_evidence_snapshot(raw_json)
    assert loaded["snapshots"]["draft"]["entries"][0]["score"] == 14
    assert loaded["snapshots"]["draft"]["entries"][0]["score_reasons"] == [
        "title:staff +4",
        "template_phrase:title +5",
    ]
