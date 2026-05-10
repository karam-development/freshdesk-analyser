"""KB evidence display helper — no LLM calls, no DB writes.

Public function
---------------
build_kb_evidence_review(entries: list[dict]) -> dict

Transforms raw kb_retrieval entries into a stable display dict suitable
for passing to the ticket.html template.

Returned structure::

    {
      "has_data": bool,
      "entries": [
        {
          "title": str,
          "category": str,
          "evidence_type": str,
          "score": float,
          "matched_terms": list[str],   # max 8
          "score_reasons": list[str],   # max 8; [] when absent/invalid
          "snippet": str,               # max 220 chars
          "badge_label": str,
          "severity": str,
        },
        ...
      ],                                # max 8 entries
      "summary": {
        "count": int,
        "has_legal_evidence": bool,
        "has_workaround_evidence": bool,
        "has_existing_setting_evidence": bool,
        "has_product_evidence": bool,
        "has_terminology_evidence": bool,
        "evidence_types": list[str],    # unique, sorted
      },
    }
"""
from __future__ import annotations

from typing import List

# ── Configuration constants ────────────────────────────────────────────────────

_MAX_ENTRIES = 8
_MAX_TERMS = 8
_MAX_REASONS = 8
_SNIPPET_MAX = 220

_SEVERITY_MAP = {
    "legal_evidence": "warning",
    "workaround_evidence": "success",
    "existing_setting_evidence": "success",
    "product_evidence": "info",
    "terminology_evidence": "neutral",
    "general_evidence": "neutral",
}

_BADGE_LABEL_MAP = {
    "legal_evidence": "Legal evidence",
    "workaround_evidence": "Workaround",
    "existing_setting_evidence": "Existing setting",
    "product_evidence": "Product evidence",
    "terminology_evidence": "Terminology",
    "general_evidence": "General",
}

_EMPTY_RESULT: dict = {
    "has_data": False,
    "entries": [],
    "summary": {
        "count": 0,
        "has_legal_evidence": False,
        "has_workaround_evidence": False,
        "has_existing_setting_evidence": False,
        "has_product_evidence": False,
        "has_terminology_evidence": False,
        "evidence_types": [],
    },
}


def build_kb_evidence_review(entries: List[dict]) -> dict:
    """Transform raw KB retrieval entries into a stable display dict.

    Parameters
    ----------
    entries:
        List of dicts as returned by ``retrieve_relevant_kb_entries``.
        Each dict may have: title, category, content, score, matched_terms,
        evidence_type.  Missing/None fields are handled defensively.

    Returns
    -------
    dict
        Stable display dict. ``has_data`` is False when entries is empty or
        all entries are invalid.  Never raises.
    """
    if not entries or not isinstance(entries, list):
        return dict(_EMPTY_RESULT)

    display_entries: list = []
    seen_evidence_types: set = set()

    for raw in entries[:_MAX_ENTRIES]:
        if not isinstance(raw, dict):
            continue

        evidence_type = (raw.get("evidence_type") or "general_evidence").strip()
        title = (raw.get("title") or "").strip()
        category = (raw.get("category") or "").strip()
        score = raw.get("score") or 0
        content = raw.get("content") or ""

        # Build snippet from content
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

        # Preserve score_reasons (defensive: missing/None/non-list → [])
        raw_reasons = raw.get("score_reasons") or []
        if not isinstance(raw_reasons, list):
            raw_reasons = []
        score_reasons = [str(r) for r in raw_reasons[:_MAX_REASONS]]

        severity = _SEVERITY_MAP.get(evidence_type, "neutral")
        badge_label = _BADGE_LABEL_MAP.get(evidence_type, "General")

        seen_evidence_types.add(evidence_type)

        display_entries.append({
            "title": title,
            "category": category,
            "evidence_type": evidence_type,
            "score": score,
            "matched_terms": matched_terms,
            "score_reasons": score_reasons,
            "snippet": snippet,
            "badge_label": badge_label,
            "severity": severity,
            # source tag for semantic/hybrid entries ("keyword" | "semantic" | "hybrid")
            # defaults to "keyword" so existing display is unchanged when absent
            "source": str(raw.get("source") or "keyword"),
        })

    if not display_entries:
        return dict(_EMPTY_RESULT)

    # Build summary
    summary = {
        "count": len(display_entries),
        "has_legal_evidence": "legal_evidence" in seen_evidence_types,
        "has_workaround_evidence": "workaround_evidence" in seen_evidence_types,
        "has_existing_setting_evidence": "existing_setting_evidence" in seen_evidence_types,
        "has_product_evidence": "product_evidence" in seen_evidence_types,
        "has_terminology_evidence": "terminology_evidence" in seen_evidence_types,
        "evidence_types": sorted(seen_evidence_types),
    }

    return {
        "has_data": True,
        "entries": display_entries,
        "summary": summary,
    }
