"""Existing solution / workaround detector.

Pure deterministic Python — no LLM calls, no DB calls.

Public function:

    detect_existing_solution(
        ticket_summary="",
        current_behaviour="",
        evidence=None,
        kb_brief="",
        code_brief="",
        research_brief="",
    ) -> dict

Returns a dict with keys:
    has_existing_solution : bool
    solution_type         : "existing_setting" | "existing_workaround" |
                            "existing_template_pattern" | "make_editable" |
                            "no_existing_solution" | "unclear"
    recommended_action    : "explain_existing_setting" | "explain_workaround" |
                            "reference_existing_template_pattern" | "make_editable" |
                            "continue_analysis"
    confidence            : float  (0.0 – 1.0)
    reason                : str
    sources               : list[str]
    signals               : dict

Priority rules (first match wins):
  0. evidence_wrong_output=True  → no_existing_solution  (it is a bug)
  1. evidence_workaround=True    → existing_workaround
  2. context_existing_setting    → existing_setting
  3. context_existing_workaround → existing_workaround
  4. context_template_pattern    → existing_template_pattern
  5. custom_wording + correct_behaviour → make_editable
  6. fallback                    → unclear
"""
from __future__ import annotations

from typing import Optional

# ── Keyword sets ──────────────────────────────────────────────────────────────

_EXISTING_SETTING_TERMS = [
    "existing setting", "there is a setting", "there's a setting",
    "configuration option", "you can configure", "already available",
    "option exists", "you can set", "it is configurable", "is configurable",
    "the setting allows", "use the setting", "can be configured",
    "paramètre existant", "option de configuration", "il existe un paramètre",
]

_EXISTING_WORKAROUND_TERMS = [
    "workaround", "existing workaround", "bypass", "alternative approach",
    "can be done by", "can be achieved by", "there is a way to",
    "contournement", "solution de contournement", "il existe un contournement",
]

_TEMPLATE_PATTERN_TERMS = [
    "existing template", "template pattern", "standard template",
    "already a template", "existing pattern", "template for this",
    "modèle existant", "patron existant", "il existe un modèle",
]

_CUSTOM_WORDING_TERMS = [
    "our wording", "our own wording", "our preferred", "preferred wording",
    "client wording", "we prefer", "we want", "we'd like", "we would like",
    "custom wording", "our label", "our text", "preferred text",
    "libellé", "formulation", "notre formulation", "notre texte",
]

_CORRECT_BEHAVIOUR_TERMS = [
    "correct", "standard", "expected", "accurate", "working as designed",
    "working as intended", "by design", "is correct", "is standard",
    "is expected", "wording is correct", "current wording",
    "comportement attendu", "conforme",
]


# ── Private helpers ───────────────────────────────────────────────────────────

def _contains_any(text: str, terms: list) -> bool:
    """Return True when *text* (lower-cased) contains at least one of *terms*."""
    lower = text.lower()
    return any(t in lower for t in terms)


# ── Public API ────────────────────────────────────────────────────────────────

def detect_existing_solution(
    ticket_summary: str = "",
    current_behaviour: str = "",
    evidence: Optional[dict] = None,
    kb_brief: str = "",
    code_brief: str = "",
    research_brief: str = "",
) -> dict:
    """Detect whether a ticket can be resolved with an existing solution.

    Checks evidence signals first, then keyword signals in the context briefs
    (kb_brief, code_brief, research_brief) and the ticket text.

    Parameters
    ----------
    ticket_summary:
        Concise ticket text (subject + description).
    current_behaviour:
        Plain-text description of what the system currently does.
    evidence:
        Dict of boolean signals from ``extract_pm_evidence``.
    kb_brief:
        Plain-text KB / knowledge-base context.
    code_brief:
        Plain-text description of the template logic from the Code Agent.
    research_brief:
        Plain-text research / investigation results.

    Returns
    -------
    dict
        has_existing_solution, solution_type, recommended_action,
        confidence, reason, sources, signals.
    """
    ev = evidence or {}
    sources: list = []
    signals: dict = {}

    all_context = " ".join(t for t in (kb_brief, code_brief, research_brief) if t)
    ticket_text = ticket_summary or ""
    behaviour_text = current_behaviour or ""

    # ── Signal collection ─────────────────────────────────────────────────────

    signals["evidence_workaround"] = bool(ev.get("mentions_existing_workaround", False))
    signals["evidence_custom_wording"] = bool(ev.get("mentions_custom_wording", False))
    signals["evidence_correct_behaviour"] = bool(
        ev.get("mentions_correct_current_behaviour", False)
    )
    signals["evidence_wrong_output"] = bool(ev.get("mentions_wrong_output", False))

    # ── KB retrieval signals (conservative boost — additive only) ─────────────
    _kb_sigs = ev.get("kb_evidence_signals") or {}
    signals["kb_workaround_evidence"] = bool(_kb_sigs.get("has_workaround_evidence", False))
    signals["kb_existing_setting_evidence"] = bool(
        _kb_sigs.get("has_existing_setting_evidence", False)
    )
    signals["kb_product_evidence"] = bool(_kb_sigs.get("has_product_evidence", False))

    signals["context_existing_setting"] = _contains_any(
        all_context, _EXISTING_SETTING_TERMS
    )
    signals["context_existing_workaround"] = _contains_any(
        all_context, _EXISTING_WORKAROUND_TERMS
    )
    signals["context_template_pattern"] = _contains_any(
        all_context, _TEMPLATE_PATTERN_TERMS
    )
    signals["ticket_custom_wording"] = _contains_any(ticket_text, _CUSTOM_WORDING_TERMS)
    signals["context_correct_behaviour"] = _contains_any(
        f"{behaviour_text} {all_context}", _CORRECT_BEHAVIOUR_TERMS
    )

    # Track sources
    if kb_brief:
        sources.append("kb_brief")
    if code_brief:
        sources.append("code_brief")
    if research_brief:
        sources.append("research_brief")
    if ev:
        sources.append("evidence")

    # ── Priority rules ────────────────────────────────────────────────────────

    # Priority 0: wrong output confirmed → not an existing-solution case (bug)
    if signals["evidence_wrong_output"]:
        return {
            "has_existing_solution": False,
            "solution_type": "no_existing_solution",
            "recommended_action": "continue_analysis",
            "confidence": 0.9,
            "reason": (
                "Evidence confirms wrong/incorrect output; "
                "this is a bug that requires a fix, not an existing solution."
            ),
            "sources": sources,
            "signals": signals,
        }

    # Priority 1: evidence-confirmed workaround / existing feature
    if signals["evidence_workaround"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_workaround",
            "recommended_action": "explain_workaround",
            "confidence": 0.9,
            "reason": (
                "Evidence confirms an existing workaround or setting covers the "
                "request; support guidance is sufficient — no development needed."
            ),
            "sources": sources,
            "signals": signals,
        }

    # Priority 1.5: KB retrieval independently confirms a workaround (no text in briefs needed)
    if signals["kb_workaround_evidence"] and not signals["evidence_wrong_output"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_workaround",
            "recommended_action": "explain_workaround",
            "confidence": 0.8,
            "reason": (
                "KB retrieval found a relevant workaround entry for this request; "
                "support guidance should be sufficient."
            ),
            "sources": sources + ["kb_evidence_signals"],
            "signals": signals,
        }

    # Priority 1.6: KB retrieval confirms an existing setting
    if signals["kb_existing_setting_evidence"] and not signals["evidence_wrong_output"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_setting",
            "recommended_action": "explain_existing_setting",
            "confidence": 0.8,
            "reason": (
                "KB retrieval found a relevant existing-setting entry for this request."
            ),
            "sources": sources + ["kb_evidence_signals"],
            "signals": signals,
        }

    # Priority 2: KB / code / research describes an existing setting
    if signals["context_existing_setting"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_setting",
            "recommended_action": "explain_existing_setting",
            "confidence": 0.8,
            "reason": (
                "KB, code brief, or research describes an existing setting or "
                "configuration option that covers this request."
            ),
            "sources": sources,
            "signals": signals,
        }

    # Priority 3: KB / code / research describes a workaround
    if signals["context_existing_workaround"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_workaround",
            "recommended_action": "explain_workaround",
            "confidence": 0.75,
            "reason": (
                "Context (KB/code/research) describes a workaround "
                "for this type of request."
            ),
            "sources": sources,
            "signals": signals,
        }

    # Priority 4: existing template pattern covers the request
    if signals["context_template_pattern"]:
        return {
            "has_existing_solution": True,
            "solution_type": "existing_template_pattern",
            "recommended_action": "reference_existing_template_pattern",
            "confidence": 0.75,
            "reason": "An existing template pattern covers this request.",
            "sources": sources,
            "signals": signals,
        }

    # Priority 5: client preference on correct current behaviour → make_editable
    has_custom_wording = (
        signals["evidence_custom_wording"] or signals["ticket_custom_wording"]
    )
    has_correct_behaviour = (
        signals["evidence_correct_behaviour"] or signals["context_correct_behaviour"]
    )
    if has_custom_wording and has_correct_behaviour:
        return {
            "has_existing_solution": True,
            "solution_type": "make_editable",
            "recommended_action": "make_editable",
            "confidence": 0.85,
            "reason": (
                "Client preference on correct current behaviour — "
                "the solution is to make the field editable per-client."
            ),
            "sources": sources,
            "signals": signals,
        }

    # Fallback: insufficient context to determine existing solution
    return {
        "has_existing_solution": False,
        "solution_type": "unclear",
        "recommended_action": "continue_analysis",
        "confidence": 0.3,
        "reason": (
            "Insufficient context to determine whether an existing solution applies."
        ),
        "sources": sources,
        "signals": signals,
    }
