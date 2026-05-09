"""KB snapshot diff helper — no LLM calls, no DB writes.

Public function
---------------
build_kb_snapshot_diff_review(snapshot_container: dict) -> dict

Produces a deterministic diff summary comparing KB evidence entries across
flow pairs (ingest→draft, draft→regeneration, draft→analysis,
ingest→latest) so the PO can see at a glance what changed between stages.

Returned structure::

    {
      "has_data": bool,
      "comparisons": [
        {
          "from_flow": str,
          "to_flow": str,
          "has_changes": bool,
          "added_titles": list[str],         # max 8
          "removed_titles": list[str],        # max 8
          "shared_titles": list[str],         # max 8
          "added_evidence_types": list[str],
          "removed_evidence_types": list[str],
          "score_changes": [                  # max 8
            {
              "title": str,
              "from_score": float,
              "to_score": float,
              "delta": float,
            },
            ...
          ],
          "summary_text": str,
        },
        ...
      ],
      "summary": {
        "comparison_count": int,
        "changed_count": int,
        "unchanged_count": int,
        "flows_compared": list[str],
      },
    }
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ── Configuration constants ────────────────────────────────────────────────────

_MAX_TITLES = 8
_MAX_SCORE_CHANGES = 8

# Pairs to attempt in order (from_flow, to_flow).
# Duplicate pairs (after resolving latest_flow) are skipped.
_CANDIDATE_PAIRS: List[Tuple[str, str]] = [
    ("ingest", "draft"),
    ("draft", "regeneration"),
    ("draft", "analysis"),
]

_EMPTY_RESULT: dict = {
    "has_data": False,
    "comparisons": [],
    "summary": {
        "comparison_count": 0,
        "changed_count": 0,
        "unchanged_count": 0,
        "flows_compared": [],
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────


def build_kb_snapshot_diff_review(snapshot_container: dict) -> dict:
    """Build a deterministic diff summary from a KB snapshot container.

    Parameters
    ----------
    snapshot_container:
        A dict as returned by ``load_kb_evidence_snapshot``.

    Returns
    -------
    dict
        Stable diff review dict. ``has_data`` is False when the container
        has fewer than two flow snapshots.  Never raises.
    """
    if not snapshot_container or not isinstance(snapshot_container, dict):
        return dict(_EMPTY_RESULT)

    raw_snapshots = snapshot_container.get("snapshots")
    if not isinstance(raw_snapshots, dict) or len(raw_snapshots) < 2:
        return dict(_EMPTY_RESULT)

    latest_flow = str(snapshot_container.get("latest_flow") or "")

    # Build candidate pairs: fixed pairs + optional ingest→latest pair.
    candidate_pairs: List[Tuple[str, str]] = list(_CANDIDATE_PAIRS)
    if (
        latest_flow
        and latest_flow != "ingest"
        and "ingest" in raw_snapshots
        and latest_flow in raw_snapshots
    ):
        ingest_latest = ("ingest", latest_flow)
        if ingest_latest not in candidate_pairs:
            candidate_pairs.append(ingest_latest)

    # Build comparisons for pairs where both flows are present.
    seen_pairs: set = set()
    comparisons: list = []
    flows_compared_set: set = set()

    for from_flow, to_flow in candidate_pairs:
        pair = (from_flow, to_flow)
        if pair in seen_pairs:
            continue
        if from_flow not in raw_snapshots or to_flow not in raw_snapshots:
            continue
        seen_pairs.add(pair)

        from_snap = raw_snapshots[from_flow]
        to_snap = raw_snapshots[to_flow]
        if not isinstance(from_snap, dict) or not isinstance(to_snap, dict):
            continue

        comparison = _compare_snapshots(from_flow, to_flow, from_snap, to_snap)
        comparisons.append(comparison)
        flows_compared_set.add(from_flow)
        flows_compared_set.add(to_flow)

    if not comparisons:
        return dict(_EMPTY_RESULT)

    changed_count = sum(1 for c in comparisons if c["has_changes"])
    unchanged_count = len(comparisons) - changed_count

    return {
        "has_data": True,
        "comparisons": comparisons,
        "summary": {
            "comparison_count": len(comparisons),
            "changed_count": changed_count,
            "unchanged_count": unchanged_count,
            "flows_compared": sorted(flows_compared_set),
        },
    }


# ── Internal helpers ───────────────────────────────────────────────────────────


def _entry_key(entry: dict) -> str:
    """Return a stable identity key for an entry (title → id → type+snippet)."""
    title = (entry.get("title") or "").strip()
    if title:
        return title
    entry_id = entry.get("id")
    if entry_id is not None:
        return f"__id__{entry_id}"
    ev_type = (entry.get("evidence_type") or "").strip()
    snippet = (entry.get("snippet") or "")[:40].strip()
    return f"__typed__{ev_type}__{snippet}"


def _entries_from_snap(snap: dict) -> List[dict]:
    raw = snap.get("entries") or []
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict)]


def _compare_snapshots(
    from_flow: str,
    to_flow: str,
    from_snap: dict,
    to_snap: dict,
) -> dict:
    """Produce a diff comparison dict for a single from→to flow pair."""
    from_entries = _entries_from_snap(from_snap)
    to_entries = _entries_from_snap(to_snap)

    from_by_key: Dict[str, dict] = {_entry_key(e): e for e in from_entries}
    to_by_key: Dict[str, dict] = {_entry_key(e): e for e in to_entries}

    from_keys = set(from_by_key)
    to_keys = set(to_by_key)

    added_keys = sorted(to_keys - from_keys)
    removed_keys = sorted(from_keys - to_keys)
    shared_keys = sorted(from_keys & to_keys)

    added_titles = [k for k in added_keys if not k.startswith("__")][:_MAX_TITLES]
    # For fallback keys keep them readable
    added_titles += [k for k in added_keys if k.startswith("__")][:max(0, _MAX_TITLES - len(added_titles))]
    added_titles = added_titles[:_MAX_TITLES]

    removed_titles = [k for k in removed_keys if not k.startswith("__")][:_MAX_TITLES]
    removed_titles += [k for k in removed_keys if k.startswith("__")][:max(0, _MAX_TITLES - len(removed_titles))]
    removed_titles = removed_titles[:_MAX_TITLES]

    shared_titles = [k for k in shared_keys if not k.startswith("__")][:_MAX_TITLES]
    shared_titles += [k for k in shared_keys if k.startswith("__")][:max(0, _MAX_TITLES - len(shared_titles))]
    shared_titles = shared_titles[:_MAX_TITLES]

    # Evidence type changes
    from_types = {(e.get("evidence_type") or "").strip() for e in from_entries}
    to_types = {(e.get("evidence_type") or "").strip() for e in to_entries}
    from_types.discard("")
    to_types.discard("")
    added_evidence_types = sorted(to_types - from_types)
    removed_evidence_types = sorted(from_types - to_types)

    # Score changes for shared entries
    score_changes: list = []
    for key in shared_keys:
        from_score = from_by_key[key].get("score") or 0
        to_score = to_by_key[key].get("score") or 0
        try:
            from_score = float(from_score)
            to_score = float(to_score)
        except (TypeError, ValueError):
            continue
        if from_score != to_score:
            score_changes.append({
                "title": key if not key.startswith("__") else "",
                "from_score": from_score,
                "to_score": to_score,
                "delta": round(to_score - from_score, 4),
            })
    score_changes = score_changes[:_MAX_SCORE_CHANGES]

    has_changes = bool(added_keys or removed_keys or score_changes or
                       added_evidence_types or removed_evidence_types)

    summary_text = _make_summary_text(
        from_flow, to_flow,
        added_titles, removed_titles,
        added_evidence_types, removed_evidence_types,
        score_changes, has_changes,
    )

    return {
        "from_flow": from_flow,
        "to_flow": to_flow,
        "has_changes": has_changes,
        "added_titles": added_titles,
        "removed_titles": removed_titles,
        "shared_titles": shared_titles,
        "added_evidence_types": added_evidence_types,
        "removed_evidence_types": removed_evidence_types,
        "score_changes": score_changes,
        "summary_text": summary_text,
    }


def _make_summary_text(
    from_flow: str,
    to_flow: str,
    added_titles: list,
    removed_titles: list,
    added_evidence_types: list,
    removed_evidence_types: list,
    score_changes: list,
    has_changes: bool,
) -> str:
    """Build a human-readable one-line summary for a comparison."""
    if not has_changes:
        return f"No KB evidence changes between {from_flow} and {to_flow}."

    parts: list = []
    n_added = len(added_titles)
    n_removed = len(removed_titles)

    if n_added and n_removed:
        parts.append(
            f"{n_added} entr{'ies' if n_added != 1 else 'y'} added, "
            f"{n_removed} removed between {from_flow} and {to_flow}."
        )
    elif n_added:
        parts.append(
            f"{n_added} entr{'ies' if n_added != 1 else 'y'} added between {from_flow} and {to_flow}."
        )
    elif n_removed:
        parts.append(
            f"{n_removed} entr{'ies' if n_removed != 1 else 'y'} removed between {from_flow} and {to_flow}."
        )

    if added_evidence_types or removed_evidence_types:
        type_parts: list = []
        if removed_evidence_types:
            type_parts.append(f"removed: {', '.join(removed_evidence_types)}")
        if added_evidence_types:
            type_parts.append(f"added: {', '.join(added_evidence_types)}")
        parts.append(f"Evidence types changed ({'; '.join(type_parts)}).")

    if score_changes:
        n = len(score_changes)
        parts.append(
            f"Scores changed for {n} shared entr{'ies' if n != 1 else 'y'}."
        )

    return " ".join(parts) if parts else f"KB evidence differs between {from_flow} and {to_flow}."
