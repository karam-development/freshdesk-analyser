"""KB evidence snapshot helper — no LLM calls, no DB writes.

Public functions
----------------
build_kb_evidence_snapshot(entries, flow="") -> dict
    Build a stable snapshot dict from raw kb_retrieval entries.

merge_kb_evidence_snapshot(existing_json, new_snapshot) -> dict
    Merge a new snapshot into an existing multi-flow container.

load_kb_evidence_snapshot(raw_json) -> dict
    Safely load a snapshot container from a raw JSON string or dict.

Returned structure for build_kb_evidence_snapshot::

    {
      "flow": str,
      "created_at": str (ISO 8601),
      "entries": [
        {
          "id": int or None,
          "title": str,
          "category": str,
          "evidence_type": str,
          "score": float,
          "matched_terms": list[str],   # max 12
          "score_reasons": list[str],   # max 12
          "snippet": str,               # max 300 chars
        },
        ...
      ],                                # max 8 entries
      "summary": {
        "count": int,
        "evidence_types": list[str],    # unique, sorted
      },
    }

Returned structure for merge_kb_evidence_snapshot / load_kb_evidence_snapshot::

    {
      "snapshots": {
        "<flow>": { ...snapshot... },
        ...
      },
      "latest_flow": str,
      "updated_at": str (ISO 8601),
    }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Union

# ── Configuration constants ────────────────────────────────────────────────────

_MAX_ENTRIES = 8
_MAX_TERMS = 12
_MAX_REASONS = 12
_SNIPPET_MAX = 300

# ── Empty stable shapes ────────────────────────────────────────────────────────

_EMPTY_SNAPSHOT: dict = {
    "flow": "",
    "created_at": "",
    "entries": [],
    "summary": {"count": 0, "evidence_types": []},
}

_EMPTY_CONTAINER: dict = {
    "snapshots": {},
    "latest_flow": "",
    "updated_at": "",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ─────────────────────────────────────────────────────────────────


def build_kb_evidence_snapshot(
    entries: List[dict],
    flow: str = "",
) -> dict:
    """Transform raw KB retrieval entries into a stable snapshot dict.

    Parameters
    ----------
    entries:
        List of dicts as returned by ``retrieve_relevant_kb_entries``.
    flow:
        Identifier for which pipeline stage built this snapshot
        (e.g. ``"ingest"``, ``"draft"``, ``"regeneration"``, ``"analysis"``).

    Returns
    -------
    dict
        Stable snapshot dict. Never raises.
    """
    if not entries or not isinstance(entries, list):
        return {
            "flow": str(flow or ""),
            "created_at": _now_iso(),
            "entries": [],
            "summary": {"count": 0, "evidence_types": []},
        }

    snapshot_entries: list = []
    seen_types: set = set()

    for raw in entries[:_MAX_ENTRIES]:
        if not isinstance(raw, dict):
            continue

        evidence_type = (raw.get("evidence_type") or "general_evidence").strip()
        title = (raw.get("title") or "").strip()
        category = (raw.get("category") or "").strip()
        score = raw.get("score") or 0
        entry_id = raw.get("id")  # may be None

        # Build snippet from content
        content = raw.get("content") or ""
        snippet_raw = content.replace("\n", " ").strip()
        if len(snippet_raw) > _SNIPPET_MAX:
            snippet = snippet_raw[:_SNIPPET_MAX] + "…"
        else:
            snippet = snippet_raw

        # Cap matched_terms
        raw_terms = raw.get("matched_terms") or []
        if not isinstance(raw_terms, list):
            raw_terms = []
        matched_terms = [str(t) for t in raw_terms[:_MAX_TERMS]]

        # Cap score_reasons
        raw_reasons = raw.get("score_reasons") or []
        if not isinstance(raw_reasons, list):
            raw_reasons = []
        score_reasons = [str(r) for r in raw_reasons[:_MAX_REASONS]]

        seen_types.add(evidence_type)

        snapshot_entries.append({
            "id": entry_id,
            "title": title,
            "category": category,
            "evidence_type": evidence_type,
            "score": score,
            "matched_terms": matched_terms,
            "score_reasons": score_reasons,
            "snippet": snippet,
        })

    return {
        "flow": str(flow or ""),
        "created_at": _now_iso(),
        "entries": snapshot_entries,
        "summary": {
            "count": len(snapshot_entries),
            "evidence_types": sorted(seen_types),
        },
    }


def merge_kb_evidence_snapshot(
    existing_json: Union[str, dict, None],
    new_snapshot: dict,
) -> dict:
    """Merge a new snapshot into an existing multi-flow container.

    Parameters
    ----------
    existing_json:
        The current value of ``tickets.kb_evidence_json`` — may be a JSON
        string, already-parsed dict, ``None``, or an empty/invalid value.
    new_snapshot:
        A dict built by ``build_kb_evidence_snapshot``.

    Returns
    -------
    dict
        Updated container with all flow snapshots preserved.  Never raises.
    """
    try:
        container = _parse_container(existing_json)
    except Exception:
        container = {
            "snapshots": {},
            "latest_flow": "",
            "updated_at": "",
        }

    if not isinstance(new_snapshot, dict):
        return container

    flow = str(new_snapshot.get("flow") or "unknown")
    if not flow:
        flow = "unknown"

    snapshots = container.get("snapshots")
    if not isinstance(snapshots, dict):
        snapshots = {}

    snapshots[flow] = new_snapshot
    container["snapshots"] = snapshots
    container["latest_flow"] = flow
    container["updated_at"] = _now_iso()
    return container


def load_kb_evidence_snapshot(
    raw_json: Union[str, dict, None],
) -> dict:
    """Safely load a snapshot container.

    Parameters
    ----------
    raw_json:
        The raw value of ``tickets.kb_evidence_json``.

    Returns
    -------
    dict
        A container dict with ``snapshots``, ``latest_flow``, ``updated_at``.
        Returns the empty stable shape if input is invalid.  Never raises.
    """
    try:
        return _parse_container(raw_json)
    except Exception:
        return {
            "snapshots": {},
            "latest_flow": "",
            "updated_at": "",
        }


# ── Internal helpers ───────────────────────────────────────────────────────────


def _parse_container(raw: Union[str, dict, None]) -> dict:
    """Parse raw JSON string or dict into a container dict.

    Raises ``ValueError`` on completely invalid input so callers can catch it.
    """
    if raw is None or raw == "" or raw == "{}":
        return {"snapshots": {}, "latest_flow": "", "updated_at": ""}

    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        parsed = json.loads(raw)  # raises on bad JSON
    else:
        raise ValueError(f"Unsupported type: {type(raw)}")

    # Validate minimal shape — snapshots key must be a dict (or absent)
    snapshots = parsed.get("snapshots", {})
    if not isinstance(snapshots, dict):
        snapshots = {}

    return {
        "snapshots": snapshots,
        "latest_flow": str(parsed.get("latest_flow") or ""),
        "updated_at": str(parsed.get("updated_at") or ""),
    }
