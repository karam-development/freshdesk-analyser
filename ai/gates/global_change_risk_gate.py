"""Global change risk gate — pure deterministic Python, no LLM calls.

Determines whether changing the default template behaviour globally is safe,
risky, or unacceptable based on the current behaviour and the legal/preference
classification of the request.
"""
from __future__ import annotations

# ── Signals that current behaviour is correct/standard ───────────────────────

_CORRECT_BEHAVIOUR_KEYWORDS = [
    "correct", "standard", "expected", "accurate", "proper",
    "already correct", "is correct", "works correctly", "currently correct",
    "standard wording", "default wording", "standard behaviour",
]

# ── Signals that current behaviour is wrong/incorrect ────────────────────────

_WRONG_BEHAVIOUR_KEYWORDS = [
    "wrong", "incorrect", "error", "bug", "broken", "mistake",
    "inaccurate", "not correct", "is wrong", "wrong wording",
    "wrong output", "wrong result",
]

# ── Legal statuses that allow a safe global fix ───────────────────────────────

_SAFE_FIX_STATUSES = {"mandatory", "accounting_required"}

# ── Legal statuses that flag client-preference / high-risk changes ────────────

_PREFERENCE_STATUSES = {"client_preference", "optional", "product_standard"}


def evaluate_global_change_risk(
    ticket_summary: str,
    current_behaviour: str = "",
    legal_status: str = "",
    evidence: dict | None = None,
) -> dict:
    """Return a global change risk assessment dict.

    Keys returned:
        global_change_risk      : "low" | "medium" | "high" | "unclear"
        safe_to_change_default  : bool
        recommended_action      : str   (one of the PMDecision DECISION_VALUES)
        reason                  : str
    """
    evidence = evidence or {}
    combined = (ticket_summary + " " + current_behaviour).lower()

    # Supplement keyword detection with evidence signals
    has_wrong = (
        any(kw in combined for kw in _WRONG_BEHAVIOUR_KEYWORDS)
        or evidence.get("mentions_wrong_output", False)
    )
    has_correct = (
        any(kw in combined for kw in _CORRECT_BEHAVIOUR_KEYWORDS)
        or evidence.get("mentions_correct_current_behaviour", False)
    )
    has_custom_wording = evidence.get("mentions_custom_wording", False)
    is_preference = legal_status in _PREFERENCE_STATUSES

    # ── Current behaviour is wrong + legal/accounting fix required → safe fix ─

    if has_wrong and legal_status in _SAFE_FIX_STATUSES:
        return {
            "global_change_risk": "low",
            "safe_to_change_default": True,
            "recommended_action": "accept_global_fix",
            "reason": (
                "Current behaviour is incorrect and a legal or accounting standard "
                "requires fixing it; a global change is appropriate."
            ),
        }

    # ── Wrong behaviour but no legal mandate → medium risk, needs scoping ─────

    if has_wrong and not is_preference:
        return {
            "global_change_risk": "medium",
            "safe_to_change_default": False,
            "recommended_action": "needs_analysis",
            "reason": (
                "Current behaviour appears wrong, but legal status is unclear; "
                "needs scoping before a global change."
            ),
        }

    # ── product_standard status → high risk, refuse global change ─────────────
    # Current behaviour is correct by product design; client deviation should
    # not affect all other clients.

    if legal_status == "product_standard":
        return {
            "global_change_risk": "high",
            "safe_to_change_default": False,
            "recommended_action": "make_editable",
            "reason": (
                "Current behaviour is correct and standard (product_standard); "
                "client-specific deviation must not affect all clients. "
                "Making the field editable is the appropriate solution."
            ),
        }

    # ── Client preference (with or without custom-wording evidence) → high risk

    if is_preference or has_custom_wording:
        return {
            "global_change_risk": "high",
            "safe_to_change_default": False,
            "recommended_action": "make_editable",
            "reason": (
                "Request is a client-specific wording or behaviour preference; "
                "a global change would affect all clients. "
                "Making the field editable is the appropriate solution."
            ),
        }

    # ── Correct current behaviour (no explicit preference status) → high risk ──

    if has_correct and not has_wrong:
        return {
            "global_change_risk": "high",
            "safe_to_change_default": False,
            "recommended_action": "make_editable",
            "reason": (
                "Current wording/behaviour is correct; changing it globally would "
                "affect all clients for a client-specific preference. "
                "Making the field editable is the appropriate solution."
            ),
        }

    # ── Fallback: unclear ─────────────────────────────────────────────────────

    return {
        "global_change_risk": "unclear",
        "safe_to_change_default": False,
        "recommended_action": "needs_analysis",
        "reason": "Insufficient signal to determine global change risk.",
    }
