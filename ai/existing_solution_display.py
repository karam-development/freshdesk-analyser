"""Existing solution display helper.

Single public function:

    extract_existing_solution_from_pm_decision(pm_decision: dict) -> dict

Reads the existing_solution result from:
  1. pm_decision["_gate_results"]["existing_solution"]  (preferred — full detail)
  2. Top-level pm_decision fields as a fallback if step 1 is missing.

Returns a stable display dict with all keys always present:
    has_data              : bool
    has_existing_solution : bool
    solution_type         : str
    recommended_action    : str
    confidence            : float
    reason                : str
    sources               : list[str]
    signals               : list[str]
    badge_label           : str
    severity              : str

severity mapping:
    existing_setting          → success
    existing_workaround       → success
    existing_template_pattern → info
    make_editable             → warning
    no_existing_solution      → neutral
    unclear                   → neutral

badge_label mapping:
    existing_setting          → Existing setting
    existing_workaround       → Existing workaround
    existing_template_pattern → Existing template pattern
    make_editable             → Make editable
    no_existing_solution      → No existing solution
    unclear                   → Unclear
"""
from __future__ import annotations

from typing import Optional

# ── Mappings ──────────────────────────────────────────────────────────────────

_SEVERITY_MAP: dict = {
    "existing_setting": "success",
    "existing_workaround": "success",
    "existing_template_pattern": "info",
    "make_editable": "warning",
    "no_existing_solution": "neutral",
    "unclear": "neutral",
}

_BADGE_LABEL_MAP: dict = {
    "existing_setting": "Existing setting",
    "existing_workaround": "Existing workaround",
    "existing_template_pattern": "Existing template pattern",
    "make_editable": "Make editable",
    "no_existing_solution": "No existing solution",
    "unclear": "Unclear",
}

_EMPTY: dict = {
    "has_data": False,
    "has_existing_solution": False,
    "solution_type": "",
    "recommended_action": "",
    "confidence": 0.0,
    "reason": "",
    "sources": [],
    "signals": [],
    "badge_label": "",
    "severity": "neutral",
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _safe_list(value: object) -> list:
    """Return a list from a value, handling None / non-list types gracefully."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, (str, int, float)):
        return [str(value)]
    return []


def _safe_float(value: object) -> float:
    """Convert to float safely; return 0.0 on failure."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# ── Public API ────────────────────────────────────────────────────────────────

def extract_existing_solution_from_pm_decision(
    pm_decision: Optional[dict],
) -> dict:
    """Extract the existing solution display dict from a PMDecision dict.

    Reads from ``pm_decision["_gate_results"]["existing_solution"]`` first;
    falls back to top-level keys if that path is absent.

    Returns the ``_EMPTY`` sentinel (has_data=False) for any invalid/missing
    input rather than raising.
    """
    if not pm_decision or not isinstance(pm_decision, dict):
        return dict(_EMPTY)

    # ── Try _gate_results.existing_solution first ─────────────────────────────
    gate_results = pm_decision.get("_gate_results")
    es: Optional[dict] = None

    if isinstance(gate_results, dict):
        candidate = gate_results.get("existing_solution")
        if isinstance(candidate, dict) and candidate:
            es = candidate

    # ── Fallback: top-level existing_solution key ─────────────────────────────
    if es is None:
        candidate = pm_decision.get("existing_solution")
        if isinstance(candidate, dict) and candidate:
            es = candidate

    # ── No data found ─────────────────────────────────────────────────────────
    if not es:
        return dict(_EMPTY)

    # ── Extract fields defensively ────────────────────────────────────────────
    has_existing_solution = bool(es.get("has_existing_solution", False))
    solution_type = str(es.get("solution_type") or "unclear")
    recommended_action = str(es.get("recommended_action") or "")
    confidence = _safe_float(es.get("confidence", 0.0))
    reason = str(es.get("reason") or "")

    # signals in the raw dict is a list[str] already; convert defensively
    signals_raw = es.get("signals")
    if isinstance(signals_raw, dict):
        # The detector stores signals as a dict {name: bool}; extract truthy keys
        signals = [k for k, v in signals_raw.items() if v]
    else:
        signals = _safe_list(signals_raw)

    sources = _safe_list(es.get("sources"))

    # ── Derive display fields ─────────────────────────────────────────────────
    severity = _SEVERITY_MAP.get(solution_type, "neutral")
    badge_label = _BADGE_LABEL_MAP.get(solution_type, solution_type.replace("_", " ").title())

    return {
        "has_data": True,
        "has_existing_solution": has_existing_solution,
        "solution_type": solution_type,
        "recommended_action": recommended_action,
        "confidence": confidence,
        "reason": reason,
        "sources": sources,
        "signals": signals,
        "badge_label": badge_label,
        "severity": severity,
    }
