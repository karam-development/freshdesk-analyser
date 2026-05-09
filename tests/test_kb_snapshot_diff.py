"""Unit tests for ai/kb_snapshot_diff.py (PR 26).

Covers:
- Invalid/empty container → has_data=False
- Fewer than 2 flows → has_data=False
- ingest+draft unchanged → has_changes=False
- ingest+draft with added title → has_changes=True
- ingest+draft with removed title → has_changes=True
- evidence type added/removed detected
- shared title score change detected
- score_changes capped at 8
- added/removed/shared titles capped at 8
- ingest→latest comparison added when latest_flow != ingest
- duplicate pairs avoided
- comparison order deterministic
- empty title fallback key
- summary changed/unchanged counts correct
- acceptance scenario
"""
from __future__ import annotations

import pytest

from ai.kb_snapshot_diff import build_kb_snapshot_diff_review


# ── Helpers ────────────────────────────────────────────────────────────────────

def _entry(title="Entry A", evidence_type="workaround_evidence",
           score=10.0, snippet="Some text.", entry_id=None):
    e = {
        "title": title,
        "evidence_type": evidence_type,
        "score": score,
        "snippet": snippet,
    }
    if entry_id is not None:
        e["id"] = entry_id
    return e


def _snap(flow, entries=None):
    return {
        "flow": flow,
        "created_at": "2026-01-01T10:00:00Z",
        "entries": entries if entries is not None else [],
    }


def _container(snaps: dict, latest_flow: str = "") -> dict:
    lf = latest_flow or (list(snaps)[-1] if snaps else "")
    return {"snapshots": snaps, "latest_flow": lf, "updated_at": "2026-01-01T10:05:00Z"}


# ── Invalid / empty input ──────────────────────────────────────────────────────


def test_none_container_returns_has_data_false():
    assert build_kb_snapshot_diff_review(None)["has_data"] is False


def test_empty_dict_returns_has_data_false():
    assert build_kb_snapshot_diff_review({})["has_data"] is False


def test_no_snapshots_key_returns_has_data_false():
    assert build_kb_snapshot_diff_review({"latest_flow": "draft"})["has_data"] is False


def test_single_flow_returns_has_data_false():
    c = _container({"ingest": _snap("ingest", [_entry()])})
    assert build_kb_snapshot_diff_review(c)["has_data"] is False


def test_two_flows_no_comparable_pair_returns_has_data_false():
    # alpha and beta are not a known pair and latest is alpha, so no ingest→latest either
    c = _container({"alpha": _snap("alpha", [_entry()]), "beta": _snap("beta", [_entry()])},
                   latest_flow="beta")
    assert build_kb_snapshot_diff_review(c)["has_data"] is False


# ── Ingest + draft comparisons ─────────────────────────────────────────────────


def test_ingest_draft_same_entries_has_changes_false():
    entry = _entry("Common entry")
    c = _container({
        "ingest": _snap("ingest", [entry]),
        "draft": _snap("draft", [entry]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    assert result["has_data"] is True
    comp = result["comparisons"][0]
    assert comp["from_flow"] == "ingest"
    assert comp["to_flow"] == "draft"
    assert comp["has_changes"] is False


def test_ingest_draft_unchanged_summary_text():
    entry = _entry("Shared")
    c = _container({
        "ingest": _snap("ingest", [entry]),
        "draft": _snap("draft", [entry]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert "No KB evidence changes" in comp["summary_text"]
    assert "ingest" in comp["summary_text"]
    assert "draft" in comp["summary_text"]


def test_ingest_draft_added_title_has_changes_true():
    c = _container({
        "ingest": _snap("ingest", [_entry("Old entry")]),
        "draft": _snap("draft", [_entry("Old entry"), _entry("New entry")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert comp["has_changes"] is True
    assert "New entry" in comp["added_titles"]
    assert "Old entry" not in comp["added_titles"]


def test_ingest_draft_removed_title_has_changes_true():
    c = _container({
        "ingest": _snap("ingest", [_entry("Old entry"), _entry("Gone entry")]),
        "draft": _snap("draft", [_entry("Old entry")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert comp["has_changes"] is True
    assert "Gone entry" in comp["removed_titles"]


def test_shared_titles_correct():
    c = _container({
        "ingest": _snap("ingest", [_entry("Shared"), _entry("Only ingest")]),
        "draft": _snap("draft", [_entry("Shared"), _entry("Only draft")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert "Shared" in comp["shared_titles"]
    assert "Only ingest" not in comp["shared_titles"]
    assert "Only draft" not in comp["shared_titles"]


# ── Evidence type changes ──────────────────────────────────────────────────────


def test_added_evidence_type_detected():
    c = _container({
        "ingest": _snap("ingest", [_entry("E", evidence_type="legal_evidence")]),
        "draft": _snap("draft", [_entry("E2", evidence_type="workaround_evidence")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert "workaround_evidence" in comp["added_evidence_types"]


def test_removed_evidence_type_detected():
    c = _container({
        "ingest": _snap("ingest", [_entry("E", evidence_type="legal_evidence")]),
        "draft": _snap("draft", [_entry("E2", evidence_type="workaround_evidence")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert "legal_evidence" in comp["removed_evidence_types"]


def test_same_evidence_type_not_flagged():
    c = _container({
        "ingest": _snap("ingest", [_entry("E1", evidence_type="workaround_evidence")]),
        "draft": _snap("draft", [_entry("E2", evidence_type="workaround_evidence")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert comp["added_evidence_types"] == []
    assert comp["removed_evidence_types"] == []


# ── Score changes ──────────────────────────────────────────────────────────────


def test_score_change_detected_for_shared_entry():
    c = _container({
        "ingest": _snap("ingest", [_entry("Shared", score=8.0)]),
        "draft": _snap("draft", [_entry("Shared", score=14.0)]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["score_changes"]) == 1
    sc = comp["score_changes"][0]
    assert sc["title"] == "Shared"
    assert sc["from_score"] == 8.0
    assert sc["to_score"] == 14.0
    assert sc["delta"] == 6.0


def test_no_score_change_not_reported():
    c = _container({
        "ingest": _snap("ingest", [_entry("Shared", score=10.0)]),
        "draft": _snap("draft", [_entry("Shared", score=10.0)]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert comp["score_changes"] == []


def test_score_changes_capped_at_8():
    entries_ingest = [_entry(f"Entry {i}", score=float(i)) for i in range(12)]
    entries_draft = [_entry(f"Entry {i}", score=float(i) + 5) for i in range(12)]
    c = _container({
        "ingest": _snap("ingest", entries_ingest),
        "draft": _snap("draft", entries_draft),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["score_changes"]) <= 8


# ── Title caps ─────────────────────────────────────────────────────────────────


def test_added_titles_capped_at_8():
    entries_draft = [_entry(f"New {i}") for i in range(12)]
    c = _container({
        "ingest": _snap("ingest", []),
        "draft": _snap("draft", entries_draft),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["added_titles"]) <= 8


def test_removed_titles_capped_at_8():
    entries_ingest = [_entry(f"Old {i}") for i in range(12)]
    c = _container({
        "ingest": _snap("ingest", entries_ingest),
        "draft": _snap("draft", []),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["removed_titles"]) <= 8


def test_shared_titles_capped_at_8():
    entries = [_entry(f"Shared {i}") for i in range(12)]
    c = _container({
        "ingest": _snap("ingest", entries),
        "draft": _snap("draft", entries),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["shared_titles"]) <= 8


# ── Ingest → latest pair ───────────────────────────────────────────────────────


def test_ingest_to_latest_comparison_added_when_latest_is_analysis():
    c = _container({
        "ingest": _snap("ingest", [_entry("I")]),
        "analysis": _snap("analysis", [_entry("A")]),
    }, latest_flow="analysis")
    result = build_kb_snapshot_diff_review(c)
    pairs = [(comp["from_flow"], comp["to_flow"]) for comp in result["comparisons"]]
    assert ("ingest", "analysis") in pairs


def test_ingest_to_latest_not_added_when_latest_is_ingest():
    c = _container({
        "ingest": _snap("ingest", [_entry("I")]),
        "draft": _snap("draft", [_entry("D")]),
    }, latest_flow="ingest")
    result = build_kb_snapshot_diff_review(c)
    pairs = [(comp["from_flow"], comp["to_flow"]) for comp in result["comparisons"]]
    # Only ingest→draft should be present
    assert ("ingest", "ingest") not in pairs


def test_duplicate_pair_not_added_twice():
    # latest_flow = draft means ingest→draft is candidate AND it's already a fixed pair
    c = _container({
        "ingest": _snap("ingest", [_entry("I")]),
        "draft": _snap("draft", [_entry("D")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    pairs = [(comp["from_flow"], comp["to_flow"]) for comp in result["comparisons"]]
    assert pairs.count(("ingest", "draft")) == 1


# ── Comparison ordering ────────────────────────────────────────────────────────


def test_comparison_order_ingest_draft_before_draft_analysis():
    c = _container({
        "ingest": _snap("ingest", [_entry("I")]),
        "draft": _snap("draft", [_entry("D")]),
        "analysis": _snap("analysis", [_entry("A")]),
    }, latest_flow="analysis")
    result = build_kb_snapshot_diff_review(c)
    pairs = [(comp["from_flow"], comp["to_flow"]) for comp in result["comparisons"]]
    id_idx = pairs.index(("ingest", "draft"))
    da_idx = pairs.index(("draft", "analysis"))
    assert id_idx < da_idx


# ── Empty title fallback ───────────────────────────────────────────────────────


def test_empty_title_uses_fallback_key():
    entry_with_id = {"title": "", "id": 99, "evidence_type": "product_evidence",
                     "score": 5.0, "snippet": "text"}
    c = _container({
        "ingest": _snap("ingest", [entry_with_id]),
        "draft": _snap("draft", []),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    # Removed entry has a fallback key, not empty
    assert any(comp["removed_titles"])


def test_empty_title_and_no_id_uses_type_snippet_key():
    entry = {"title": "", "evidence_type": "legal_evidence", "score": 5.0,
             "snippet": "A legal text"}
    c = _container({
        "ingest": _snap("ingest", [entry]),
        "draft": _snap("draft", []),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    comp = result["comparisons"][0]
    assert len(comp["removed_titles"]) == 1


# ── Summary counts ─────────────────────────────────────────────────────────────


def test_summary_changed_count():
    same = _entry("Same")
    diff_ingest = _entry("Diff ingest")
    diff_draft = _entry("Diff draft")
    c = _container({
        "ingest": _snap("ingest", [same, diff_ingest]),
        "draft": _snap("draft", [same, diff_draft]),
        "analysis": _snap("analysis", [same]),
    }, latest_flow="analysis")
    result = build_kb_snapshot_diff_review(c)
    assert result["summary"]["changed_count"] >= 1


def test_summary_unchanged_count():
    same = _entry("Same")
    c = _container({
        "ingest": _snap("ingest", [same]),
        "draft": _snap("draft", [same]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    assert result["summary"]["unchanged_count"] == 1
    assert result["summary"]["changed_count"] == 0


def test_summary_comparison_count():
    c = _container({
        "ingest": _snap("ingest", [_entry("I")]),
        "draft": _snap("draft", [_entry("D")]),
        "analysis": _snap("analysis", [_entry("A")]),
    }, latest_flow="analysis")
    result = build_kb_snapshot_diff_review(c)
    # At minimum: ingest→draft, draft→analysis, ingest→analysis
    assert result["summary"]["comparison_count"] >= 2


# ── Summary text ───────────────────────────────────────────────────────────────


def test_summary_text_added_and_removed():
    c = _container({
        "ingest": _snap("ingest", [_entry("Removed entry")]),
        "draft": _snap("draft", [_entry("Added entry")]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    text = result["comparisons"][0]["summary_text"]
    assert "added" in text.lower()
    assert "removed" in text.lower()


def test_summary_text_score_change():
    c = _container({
        "ingest": _snap("ingest", [_entry("Shared", score=5.0)]),
        "draft": _snap("draft", [_entry("Shared", score=12.0)]),
    }, latest_flow="draft")
    result = build_kb_snapshot_diff_review(c)
    text = result["comparisons"][0]["summary_text"]
    assert "score" in text.lower()


# ── Acceptance scenario ────────────────────────────────────────────────────────


def test_acceptance_scenario():
    """Full acceptance: ingest has legal entry; draft has workaround entry."""
    container = {
        "snapshots": {
            "ingest": {
                "flow": "ingest",
                "entries": [
                    {
                        "title": "Invoice VAT legal disclosure",
                        "evidence_type": "legal_evidence",
                        "score": 8.0,
                        "snippet": "Required by law to display VAT number.",
                    }
                ],
            },
            "draft": {
                "flow": "draft",
                "entries": [
                    {
                        "title": "Existing workaround for staff wording",
                        "evidence_type": "workaround_evidence",
                        "score": 14.0,
                        "snippet": "Use the editable text field.",
                    }
                ],
            },
        },
        "latest_flow": "draft",
        "updated_at": "2026-01-01T10:05:00Z",
    }

    result = build_kb_snapshot_diff_review(container)

    assert result["has_data"] is True
    assert result["summary"]["comparison_count"] >= 1

    comp = next(c for c in result["comparisons"]
                if c["from_flow"] == "ingest" and c["to_flow"] == "draft")
    assert comp["has_changes"] is True
    assert "Invoice VAT legal disclosure" in comp["removed_titles"]
    assert "Existing workaround for staff wording" in comp["added_titles"]
    assert "workaround_evidence" in comp["added_evidence_types"]
    assert "legal_evidence" in comp["removed_evidence_types"]
    assert comp["score_changes"] == []   # no shared entries → no score changes
    assert comp["summary_text"]          # non-empty
    assert "added" in comp["summary_text"].lower() or "removed" in comp["summary_text"].lower()
