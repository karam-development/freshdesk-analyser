"""Complexity gate — pure deterministic Python, no LLM calls.

Classifies a ticket into simple / medium / complex / needs_analysis and
derives the answer_depth, max_words, and needs_prd constraints.
"""
from __future__ import annotations

# ── Keyword lists ─────────────────────────────────────────────────────────────

# Signals that a ticket is a simple wording/label/UX change.
_SIMPLE_KEYWORDS = [
    "wording", "label", "typo", "spelling", "translation", "rephrase",
    "rename", "text change", "make editable", "editable", "workaround",
    "support guidance", "how to", "how-to", "no development", "no dev",
    "simple fix", "quick fix", "cosmetic",
]

# Signals of medium complexity (single-template behaviour, visibility).
_MEDIUM_KEYWORDS = [
    "visibility", "condition", "dropdown", "checkbox", "toggle",
    "single template", "one template", "infobox", "small behaviour",
    "note behaviour",
]

# Signals of complex scope (multi-template, calculation, cross-entity).
_COMPLEX_KEYWORDS = [
    "multi-template", "multiple templates", "cross-template", "cross template",
    "calculation", "formula", "account range", "accounts 6", "accounts 7",
    "multiple notes", "intercompany", "consolidation",
]

# Signals that expert analysis is needed before deciding complexity.
_NEEDS_ANALYSIS_KEYWORDS = [
    "unclear", "uncertain", "not sure", "unknown", "depends on",
    "legal", "law", "mandatory", "accounting standard", "pcn",
    "plan comptable", "ifrs", "gaap",
]


def evaluate_complexity(
    ticket_summary: str,
    requested_change: str = "",
    evidence: dict | None = None,
) -> dict:
    """Return a complexity assessment dict.

    Keys returned:
        complexity      : "simple" | "medium" | "complex" | "needs_analysis"
        answer_depth    : "short"  | "normal"  | "detailed" | "prd"
        max_words       : int  (upper word-count limit for the response)
        needs_prd       : bool
        reason          : str
    """
    combined = (ticket_summary + " " + requested_change).lower()

    # Complex scope is checked first: multi-template / calculation tickets are
    # explicitly complex even when they mention standards like IFRS in passing.
    if any(kw in combined for kw in _COMPLEX_KEYWORDS):
        return {
            "complexity": "complex",
            "answer_depth": "detailed",
            "max_words": 800,
            "needs_prd": True,
            "reason": (
                "Ticket affects multiple templates, calculations, or "
                "cross-entity logic; complex scope."
            ),
        }

    # needs_analysis: legal / accounting ambiguity that doesn't match a clear
    # complex pattern — expert analysis required before deciding complexity.
    if any(kw in combined for kw in _NEEDS_ANALYSIS_KEYWORDS):
        return {
            "complexity": "needs_analysis",
            "answer_depth": "normal",
            "max_words": 500,
            "needs_prd": False,
            "reason": (
                "Ticket involves legal, accounting, or unclear scope; "
                "expert analysis required before deciding complexity."
            ),
        }

    # Simple wording/label/typo signals outrank medium (e.g. a wording change
    # on a dropdown field is still a simple request even though it mentions
    # "dropdown").
    if any(kw in combined for kw in _SIMPLE_KEYWORDS):
        return {
            "complexity": "simple",
            "answer_depth": "short",
            "max_words": 200,
            "needs_prd": False,
            "reason": (
                "Ticket is a simple wording, label, typo, or workaround request; "
                "short response is sufficient."
            ),
        }

    if any(kw in combined for kw in _MEDIUM_KEYWORDS):
        return {
            "complexity": "medium",
            "answer_depth": "normal",
            "max_words": 500,
            "needs_prd": False,
            "reason": (
                "Ticket involves a single-template behaviour change; medium complexity."
            ),
        }

    # Default: simple
    return {
        "complexity": "simple",
        "answer_depth": "short",
        "max_words": 200,
        "needs_prd": False,
        "reason": (
            "Ticket is a simple wording, label, typo, or workaround request; "
            "short response is sufficient."
        ),
    }
