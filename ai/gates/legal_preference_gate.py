"""Legal vs preference gate — pure deterministic Python, no LLM calls.

Determines whether a ticket is driven by a genuine legal/accounting requirement
or by a client wording preference, and sets should_mention_law accordingly.

Rule: should_mention_law is false UNLESS evidence explicitly confirms a legal
or accounting requirement.  Keyword detection in the ticket text alone is NOT
sufficient to set should_mention_law = True.

Priority order (first match wins):
  1. Explicit mandatory evidence key  → mandatory / accounting_required
  2. evidence["mentions_custom_wording"] is True  → client_preference
  3. evidence["mentions_correct_current_behaviour"] is True  → product_standard
  4. Ticket-text preference keywords  → client_preference
  5. evidence["mentions_legal_terms"] is True (no other match)  → unclear, note the signal
  6. Default  → unclear
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

    # ── Priority 1: Explicit mandatory evidence (highest authority) ───────────
    # Only explicit evidence keys — not ticket keywords — can set
    # should_mention_law = True.

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
        # Key present but value indicates accounting/regulatory standard
        return {
            "legal_status": "accounting_required",
            "should_mention_law": True,
            "reason": (
                f"Evidence key '{key}' indicates an accounting or regulatory requirement."
            ),
            "confidence": 0.8,
        }

    # ── Priority 2: Evidence confirms custom wording preference ───────────────

    if evidence.get("mentions_custom_wording") is True:
        return {
            "legal_status": "client_preference",
            "should_mention_law": False,
            "reason": (
                "Evidence confirms a client custom-wording preference; "
                "no legal or accounting requirement found."
            ),
            "confidence": 0.85,
        }

    # ── Priority 3: Evidence confirms correct current behaviour ───────────────
    # Current behaviour is correct/standard → request is a client deviation,
    # not a legal fix → product_standard.

    if evidence.get("mentions_correct_current_behaviour") is True:
        return {
            "legal_status": "product_standard",
            "should_mention_law": False,
            "reason": (
                "Evidence confirms the current behaviour is correct and standard; "
                "request is a client-specific deviation, not a legal correction."
            ),
            "confidence": 0.75,
        }

    # ── Priority 4: Ticket-text preference keywords ────────────────────────────

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

    # ── Priority 5: Legal terms mentioned but no explicit requirement ──────────
    # Presence of legal vocabulary alone does NOT permit citing law.

    if evidence.get("mentions_legal_terms") is True:
        return {
            "legal_status": "unclear",
            "should_mention_law": False,
            "reason": (
                "Legal terms were mentioned in the ticket, but no explicit legal "
                "requirement evidence was provided; treating as unclear — "
                "do not cite law without confirmed obligation."
            ),
            "confidence": 0.4,
        }

    # ── Priority 6: No clear signal ───────────────────────────────────────────

    return {
        "legal_status": "unclear",
        "should_mention_law": False,
        "reason": (
            "No clear legal, accounting, or preference signal found in the ticket."
        ),
        "confidence": 0.4,
    }
