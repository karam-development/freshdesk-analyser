"""PM prompt block builder.

Public function:

  build_pm_prompt_block(pm_decision, regeneration_instruction="") -> str
      Combines PM context sections in the required order:
        1. regeneration_instruction  (if provided)
        2. PM DRAFTING INSTRUCTIONS  (build_pm_draft_instructions)
        3. PM DECISION CONSTRAINTS   (format_pm_decision_for_prompt)
      Returns "" when all parts are empty.
      No LLM calls.  Defensive with None/empty inputs.
"""
from __future__ import annotations

from typing import Optional

from ai.pm_draft_instructions import build_pm_draft_instructions
from ai.pm_decision_formatter import format_pm_decision_for_prompt


def build_pm_prompt_block(
    pm_decision: Optional[dict],
    regeneration_instruction: str = "",
) -> str:
    """Return a combined PM context block ready for prompt injection.

    Sections are joined with a blank line between them.  Returns "" when
    every part evaluates to an empty/whitespace string.

    Order (first to last):
      1. regeneration_instruction, if non-empty
      2. PM DRAFTING INSTRUCTIONS section
      3. PM DECISION CONSTRAINTS section
    """
    parts: list = []

    regen = (regeneration_instruction or "").strip()
    if regen:
        parts.append(regen)

    instr = build_pm_draft_instructions(pm_decision)
    if instr:
        parts.append(instr)

    ctx = format_pm_decision_for_prompt(pm_decision)
    if ctx:
        parts.append(ctx)

    if not parts:
        return ""

    return "\n\n".join(parts)
