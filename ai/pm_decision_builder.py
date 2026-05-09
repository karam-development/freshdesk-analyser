"""PM decision builder — combines gate results into a validated PMDecision dict.

Priority rules (applied in order, first match wins):
  1. client_preference + high global-change risk → refuse_global_change / make_editable
  2. support_guidance or no_dev → explain_workaround / support_guidance
  3. bug_fix → accept_bug
  4. legal_status unclear or complexity needs_analysis → needs_analysis
  5. default → needs_analysis

Safe defaults are always applied:
  - answer_depth = "short" for simple complexity
  - max_words <= 250 for simple complexity
  - needs_prd = False unless complexity is complex AND evidence supports it
  - should_mention_law = False unless legal gate explicitly set it True
"""
from __future__ import annotations

from ai.schemas import SAFE_DEFAULTS


def build_pm_decision_from_gates(
    ticket_summary: str,
    gate_results: dict,
    evidence_used: list | None = None,
) -> dict:
    """Combine gate results into a validated PMDecision-compatible dict.

    Args:
        ticket_summary  : Original ticket text (used for reason construction).
        gate_results    : Dict with keys: "complexity", "legal_preference",
                          "global_change_risk", "development_need".
                          Each value is the dict returned by the corresponding gate.
        evidence_used   : Optional list of evidence labels used during analysis.

    Returns:
        A dict matching the PMDecision schema with all required fields.
    """
    # Start from safe defaults so partial gate results never produce blanks.
    out = dict(SAFE_DEFAULTS)
    out["evidence_used"] = list(evidence_used or [])

    # ── Unpack gate results (all optional — gates may be missing) ─────────────

    cx = gate_results.get("complexity") or {}
    lp = gate_results.get("legal_preference") or {}
    gr = gate_results.get("global_change_risk") or {}
    dn = gate_results.get("development_need") or {}

    # ── Unpack structured PM lesson signals (conservative hints only) ─────────
    _struct       = gate_results.get("structured_pm_lessons") or {}
    _lesson_sigs  = _struct.get("signals") or {}

    # ── Copy gate fields into output ──────────────────────────────────────────

    complexity      = cx.get("complexity",          out["complexity"])
    answer_depth    = cx.get("answer_depth",        out["answer_depth"])
    max_words       = cx.get("max_words",           out["max_words"])
    needs_prd_gate  = cx.get("needs_prd",           False)

    legal_status        = lp.get("legal_status",        out["legal_status"])
    should_mention_law  = lp.get("should_mention_law",  False)  # safe default: False

    global_change_risk      = gr.get("global_change_risk",      out["global_change_risk"])
    safe_to_change_default  = gr.get("safe_to_change_default",  False)
    gr_action               = gr.get("recommended_action",       "needs_analysis")

    needs_development  = dn.get("needs_development",  False)
    development_type   = dn.get("development_type",   out["development_type"])
    dn_action          = dn.get("recommended_action",  "needs_analysis")

    # ── Propagate safe-default constraints ────────────────────────────────────
    # needs_prd is only True when complexity is "complex" AND the gate said so.
    needs_prd = needs_prd_gate and complexity == "complex"

    # For simple tickets always cap max_words at 250 and keep answer_depth short.
    if complexity == "simple":
        max_words    = min(max_words, 250)
        answer_depth = "short"
        needs_prd    = False

    # ── Classification ────────────────────────────────────────────────────────
    # (computed before lesson-signal adjustments so signals can reference it)
    # Derive from legal_preference gate where possible.

    if development_type == "bug_fix":
        # Bug classification wins over legal/product status — a bug is always a bug.
        classification = "bug"
    elif legal_status == "client_preference":
        classification = "client_preference"
    elif legal_status in ("mandatory", "accounting_required"):
        classification = "expected_behaviour"
    elif legal_status == "product_standard":
        classification = "expected_behaviour"
    elif development_type == "feature_request":
        classification = "feature_request"
    elif development_type == "support_guidance":
        classification = "how_to"
    else:
        classification = "needs_analysis"

    # ── Structured PM lesson adjustments (applied after classification) ──────
    # prefer_short_answer: nudge answer_depth to "short" for safe classifications.
    # Only applies when complexity is not "complex" to avoid truncating PRD output.
    _SHORT_ANSWER_SAFE = ("client_preference", "how_to", "expected_behaviour", "product_standard")
    if (
        _lesson_sigs.get("prefer_short_answer")
        and complexity != "complex"
        and classification in _SHORT_ANSWER_SAFE
    ):
        answer_depth = "short"

    # ── Decision (priority rules) ─────────────────────────────────────────────

    reasons: list[str] = []

    # Rule 1: client preference / product_standard + high global-change risk
    if legal_status in ("client_preference", "optional", "product_standard") and global_change_risk == "high":
        decision           = gr_action if gr_action in ("refuse_global_change", "make_editable") \
                             else "refuse_global_change"
        recommended_action = decision
        reasons.append(
            "Client preference with high global-change risk: "
            "changing the default would affect all clients."
        )

    # Rule 2: support/no-dev
    elif development_type in ("support_guidance", "no_dev") and not needs_development:
        # Prefer the gate's specific action when it is one of the known solution types.
        _specific_actions = (
            "explain_existing_setting",
            "explain_workaround",
            "reference_existing_template_pattern",
        )
        if dn_action in _specific_actions:
            decision = dn_action
        elif development_type == "support_guidance":
            decision = "explain_workaround"
        else:
            decision = "support_guidance"
        recommended_action = decision
        reasons.append("Workaround or existing feature is sufficient; no development needed.")

    # Rule 3: bug fix
    elif development_type == "bug_fix":
        decision           = "accept_bug"
        recommended_action = "accept_bug"
        reasons.append("Ticket describes a reproducible bug.")

    # Rule 4: unclear legal status or complexity needs expert analysis
    elif legal_status == "unclear" or complexity == "needs_analysis":
        decision           = "needs_analysis"
        recommended_action = "needs_analysis"
        reasons.append(
            "Legal status or complexity is unclear; expert analysis required."
        )

    # Rule 4.5: lesson signal nudge — prefer_make_editable when status is unclear
    # Only fires when no earlier rule matched AND legal status is not mandatory.
    # Lessons are hints; this only promotes make_editable over pure needs_analysis.
    elif (
        _lesson_sigs.get("prefer_make_editable")
        and legal_status not in ("mandatory", "accounting_required")
        and development_type != "bug_fix"
    ):
        decision           = "make_editable"
        recommended_action = "make_editable"
        reasons.append(
            "Structured PM lesson history suggests make_editable for similar "
            "client preference patterns."
        )

    # Rule 5: default
    else:
        decision           = "needs_analysis"
        recommended_action = "needs_analysis"
        reasons.append("Insufficient signal to make a confident decision.")

    # ── Assemble final output ─────────────────────────────────────────────────

    out.update({
        "decision":            decision,
        "classification":      classification,
        "complexity":          complexity,
        "answer_depth":        answer_depth,
        "max_words":           max_words,
        "needs_prd":           needs_prd,
        "needs_development":   needs_development,
        "development_type":    development_type,
        "legal_status":        legal_status,
        "should_mention_law":  should_mention_law,
        "global_change_risk":  global_change_risk,
        "recommended_action":  recommended_action,
        "reason":              " | ".join(reasons),
        "confidence":          lp.get("confidence", gr.get("confidence", 0.5)),
    })

    return out
