"""Legal vs preference gate — pure deterministic Python, no LLM calls.

Determines whether a ticket is driven by a genuine legal/accounting requirement
or by a client wording preference, and sets should_mention_law accordingly.

Rule: should_mention_law is false UNLESS evidence explicitly confirms a legal
or accounting requirement.  Keyword detection in the ticket text alone is NOT
sufficient to set should_mention_law = True.
"""
from __future__ import annotations

# ── Client preference signals ─────────────────────────────────────────────────

_PREFERENCE_KEYWORDS = [
    "our wording", "client wording", "preferred wording", "custom wording",
    "our preferred", "their wording", "we prefer", "we want", "we'd like",
    "would like", "client preference", "client request",
    "client-specific", "company preference",
    "they want", "they prefer", "their preference",
]

# ── Evidence keys that confirm a mandatory legal/accounting requirement ────────

_MANDATORY_EVIDENCE_KEYS = {
    "legal_requirement",
    "mandatory",
    "law_reference",
    "accounting_standard",
    "regulatory_requirement",
}

# Evidence value strings that indicate mandatory status
_MANDATORY_VALUES = {"mandatory", "required", "obligatory", "compulsory"}


def evaluate_legal_preference(
    ticket_summary: str,
    current_behaviour: str = "",
    evidence: dict | None = None,
) -> dict:
    """Return a legal/preference assessment dict.

    Keys returned:
        legal_status        : "mandatory" | "accounting_required" |
                              "product_standard" | "client_preference" |
                              "optional" | "unclear"
        should_mention_law  : bool
        reason              : str
        confidence          : float
    """
    evidence = evidence or {}
    combined = (ticket_summary + " " + current_behaviour).lower()

    # ── Evidence-based checks (highest priority) ──────────────────────────────
    # Only evidence — not ticket keywords — can set should_mention_law = True.

    for key in _MANDATORY_EVIDENCE_KEYS:
        val = str(evidence.get(key, "")).lower().strip()
        if not val:
            continue
        if val in _MANDATORY_VALUES or val == "mandatory":
            return {
                "legal_status": "mandatory",
                "should_mention_law": True,
                "reason": (
                    f"Evidence key '{key}' explicitly states a mandatory legal requirement."
                ),
                "confidence": 0.9,
            }
        # Key present but value indicates accounting/product standard
        return {
            "legal_status": "accounting_required",
            "should_mention_law": True,
            "reason": (
                f"Evidence key '{key}' indicates an accounting or regulatory requirement."
            ),
            "confidence": 0.8,
        }

    # ── Ticket-text preference signals ────────────────────────────────────────

    if any(kw in combined for kw in _PREFERENCE_KEYWORDS):
        return {
            "legal_status": "client_preference",
            "should_mention_law": False,
            "reason": (
                "Ticket describes a client wording preference; "
                "no legal or accounting evidence found."
            ),
            "confidence": 0.85,
        }

    # ── No clear signal ───────────────────────────────────────────────────────

    return {
        "legal_status": "unclear",
        "should_mention_law": False,
        "reason": (
            "No clear legal, accounting, or preference signal found in the ticket."
        ),
        "confidence": 0.4,
    }
