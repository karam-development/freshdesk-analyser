"""KB snapshot flow display helper — no LLM calls, no DB writes.

Public function
---------------
build_kb_snapshot_flow_review(snapshot_container: dict) -> dict

Transforms a loaded KB evidence snapshot container (from
``load_kb_evidence_snapshot``) into a stable display dict suitable for
rendering a per-flow audit view on the ticket detail page.

Returned structure::

    {
      "has_data": bool,
      "latest_flow": str,
      "flows": [
        {
          "flow": str,
          "created_at": str,
          "entry_count": int,
          "evidence_types": list[str],   # unique, sorted
          "entries": [
            {
              "title": str,
              "evidence_type": str,
              "score": float,
              "matched_terms": list[str],  # max 8
              "score_reasons": list[str],  # max 8
              "snippet": str,              # max 180 chars
            },
            ...
          ],                               # max 8 entries per flow
        },
        ...
      ],
      "summary": {
        "flow_count": int,
        "total_entries": int,
        "flows_present": list[str],
        "has_different_flows": bool,
      },
    }
"""
from __future__ import annotations

from typing import Dict, List

# ── Configuration constants ────────────────────────────────────────────────────

_MAX_ENTRIES = 8
_MAX_TERMS = 8
_MAX_REASONS = 8
_SNIPPET_MAX = 180

# Canonical flow order; unknown flows are appended after these.
_FLOW_ORDER = ["ingest", "draft", "regeneration", "analysis"]

_EMPTY_RESULT: dict = {
    "has_data": False,
    "latest_flow": "",
    "flows": [],
    "summary": {
        "flow_count": 0,
        "total_entries": 0,
        "flows_present": [],
        "has_different_flows": False,
    },
}


def build_kb_snapshot_flow_review(snapshot_container: dict) -> dict:
    """Transform a loaded KB snapshot container into a stable per-flow display dict.

    Parameters
    ----------
    snapshot_container:
        A dict as returned by ``load_kb_evidence_snapshot``.  Expected shape::

            {
              "snapshots": { "<flow>": { ... }, ... },
              "latest_flow": str,
              "updated_at": str,
            }

    Returns
    -------
    dict
        Stable display dict. ``has_data`` is False when the container is
        empty or entirely invalid.  Never raises.
    """
    if not snapshot_container or not isinstance(snapshot_container, dict):
        return dict(_EMPTY_RESULT)

    raw_snapshots = snapshot_container.get("snapshots")
    if not isinstance(raw_snapshots, dict) or not raw_snapshots:
        return dict(_EMPTY_RESULT)

    latest_flow = str(snapshot_container.get("latest_flow") or "")

    # Sort flows: canonical order first, then unknown flows alphabetically.
    known = [f for f in _FLOW_ORDER if f in raw_snapshots]
    unknown = sorted(f for f in raw_snapshots if f not in _FLOW_ORDER)
    ordered_flows = known + unknown

    flows: List[dict] = []
    total_entries = 0

    for flow_name in ordered_flows:
        raw_snap = raw_snapshots[flow_name]
        if not isinstance(raw_snap, dict):
            continue

        created_at = str(raw_snap.get("created_at") or "")
        raw_entries = raw_snap.get("entries") or []
        if not isinstance(raw_entries, list):
            raw_entries = []

        display_entries: list = []
        seen_types: set = set()

        for raw_entry in raw_entries[:_MAX_ENTRIES]:
            if not isinstance(raw_entry, dict):
                continue

            evidence_type = (raw_entry.get("evidence_type") or "general_evidence").strip()
            title = (raw_entry.get("title") or "").strip()
            score = raw_entry.get("score") or 0

            # Snippet from entry snippet field (already truncated by snapshot helper)
            # or from content if present; re-apply cap at _SNIPPET_MAX.
            snippet_src = (raw_entry.get("snippet") or raw_entry.get("content") or "")
            snippet_raw = snippet_src.replace("\n", " ").strip()
            if len(snippet_raw) > _SNIPPET_MAX:
                snippet = snippet_raw[:_SNIPPET_MAX] + "…"
            else:
                snippet = snippet_raw

            # Cap matched_terms
            raw_terms = raw_entry.get("matched_terms") or []
            if not isinstance(raw_terms, list):
                raw_terms = []
            matched_terms = [str(t) for t in raw_terms[:_MAX_TERMS]]

            # Cap score_reasons
            raw_reasons = raw_entry.get("score_reasons") or []
            if not isinstance(raw_reasons, list):
                raw_reasons = []
            score_reasons = [str(r) for r in raw_reasons[:_MAX_REASONS]]

            seen_types.add(evidence_type)
            display_entries.append({
                "title": title,
                "evidence_type": evidence_type,
                "score": score,
                "matched_terms": matched_terms,
                "score_reasons": score_reasons,
                "snippet": snippet,
            })

        total_entries += len(display_entries)

        flows.append({
            "flow": flow_name,
            "created_at": created_at,
            "entry_count": len(display_entries),
            "evidence_types": sorted(seen_types),
            "entries": display_entries,
        })

    if not flows:
        return dict(_EMPTY_RESULT)

    flows_present = [f["flow"] for f in flows]

    summary = {
        "flow_count": len(flows),
        "total_entries": total_entries,
        "flows_present": flows_present,
        "has_different_flows": len(flows) > 1,
    }

    return {
        "has_data": True,
        "latest_flow": latest_flow,
        "flows": flows,
        "summary": summary,
    }
