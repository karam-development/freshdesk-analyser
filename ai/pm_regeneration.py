"""PM regeneration instruction builder.

Public function:

  build_pm_regeneration_instruction(pm_decision, guard_warnings) -> str
      Build a block of text that tells the model how to correct a draft that
      triggered PM guard warnings.  Returns "" when there is nothing to say.
"""
from __future__ import annotations

from typing import Optional, List


# ── per-code correction instructions ─────────────────────────────────────────

_CODE_INSTRUCTIONS: dict = {
    "legal_reference_blocked": (
        "Remove all legal references, article numbers, and law citations from the draft. "
        "Do NOT mention any law, regulation, or legal obligation."
    ),
    "global_default_change_blocked": (
        "Do NOT propose any global default change, system-wide setting change, or "
        "change that would affect all users. Limit the response to the specific client's context."
    ),
    "editability_missing": (
        "Explicitly mention that the field/setting is editable, configurable, or "
        "can be adjusted per client. Use words like 'editable', 'configurable', or 'per client'."
    ),
    "bug_framed_as_feature": (
        "Frame the issue as a bug, defect, or fix — not as a new feature request. "
        "Use language like 'we will fix', 'this is a defect', or 'this will be corrected'."
    ),
    "support_escalated_to_dev": (
        "Provide practical workaround or support guidance directly to the client. "
        "Avoid escalating to development or suggesting the issue requires a developer."
    ),
    "prd_style_blocked": (
        "Remove all PRD-style headings, bullet-point requirement lists, and structured "
        "specification sections. Write in plain customer-support prose."
    ),
    "output_too_long": (
        "Make the response significantly shorter and more concise. "
        "Keep only the most essential information for the client."
    ),
}


def build_pm_regeneration_instruction(
    pm_decision: Optional[dict],
    guard_warnings: Optional[List[dict]] = None,
) -> str:
    """Build a correction instruction block from a PM decision and active guard warnings.

    Parameters
    ----------
    pm_decision:
        The PM decision dict (fields: decision, recommended_action, etc.).
        May be None or empty.
    guard_warnings:
        List of categorised warning dicts (each has a "code" key).
        May be None or empty.

    Returns
    -------
    str
        A block of text to inject into the prompt, or "" when nothing to add.
    """
    lines: List[str] = []

    # ── decision summary ──────────────────────────────────────────────────────
    if pm_decision:
        rec = pm_decision.get("recommended_action") or ""
        decision = pm_decision.get("decision") or ""
        depth = pm_decision.get("answer_depth") or ""
        max_words = pm_decision.get("max_words")

        if decision or rec:
            lines.append("PM DECISION SUMMARY:")
        if decision:
            lines.append(f"  decision={decision}")
        if rec:
            lines.append(f"  recommended_action={rec}")
        if depth:
            lines.append(f"  answer_depth={depth}")
        if max_words:
            lines.append(f"  max_words={max_words}")

    # ── per-warning corrections ───────────────────────────────────────────────
    if guard_warnings:
        correction_lines: List[str] = []
        seen_codes: set = set()
        for w in guard_warnings:
            code = (w.get("code") or "").strip()
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            instruction = _CODE_INSTRUCTIONS.get(code)
            if instruction:
                correction_lines.append(f"- [{code}] {instruction}")

        if correction_lines:
            lines.append("\nCORRECTIONS REQUIRED:")
            lines.extend(correction_lines)

    if not lines:
        return ""

    lines.insert(0, "PM REGENERATION INSTRUCTIONS:")
    lines.append(
        "\nRegenerate the draft respecting these corrections. "
        "Do not mention PM guard warnings to the client."
    )
    return "\n".join(lines)
