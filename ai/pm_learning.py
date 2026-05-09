"""Structured PM lesson extractor and upsert helper.

Pure deterministic Python — no LLM calls.

Public functions:

    extract_structured_pm_lessons(
        original_ai_output, final_po_output,
        pm_decision=None,
        ticket_subject="", template_name="", workflow_name="",
    ) -> list[dict]

    upsert_structured_pm_lesson(db, source_ticket_id, lesson) -> tuple[int | None, bool]
        Returns (lesson_id, was_duplicate).

Each lesson dict has stable keys:
    lesson_type, category, before, after, instruction,
    confidence, applies_to, template_name, workflow_name, source

Allowed lesson_type values:
    classification_correction | legal_reference_removed |
    global_change_to_editable | dev_to_support_guidance |
    workaround_added | bug_feature_framing | answer_depth_shortened |
    existing_solution_added | unknown
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Keyword sets ──────────────────────────────────────────────────────────────

_LEGAL_TERMS = [
    "article ", "loi ", "legal", "mandatory", "compliance",
    "obligatory", "obligation", "required by law", "law of",
    "ecdf", "rgd", "pcn", "réglementation", "réglementaire",
    "réglement", "legalement", "légalement",
]

_GLOBAL_CHANGE_TERMS = [
    "global", "default globally", "change the default", "change default",
    "all clients", "default wording", "standard wording", "globally",
    "pour tous les clients", "modifier le défaut",
]

_EDITABLE_TERMS = [
    "editable", "configurable", "per-client", "per client",
    "client-specific", "make editable", "rendre éditable",
    "configurable par client",
]

_DEV_TERMS = [
    "jira", "development", "create a ticket", "backlog",
    "implement", "build a", "new feature", "feature request",
    "enhancement", "développement", "créer un ticket",
    "create a jira", "développer",
]

_SUPPORT_GUIDANCE_TERMS = [
    "workaround", "existing setting", "can already", "already possible",
    "support guidance", "no development", "contact support",
    "already exists", "already available", "how to", "guide",
]

_WORKAROUND_TERMS = [
    "workaround", "existing setting", "already available",
    "existing solution", "existing workaround",
    "contournement", "paramètre existant",
]

_FEATURE_REQUEST_TERMS = [
    "feature request", "new feature", "enhancement request", "enhancement",
    "new functionality", "add feature", "demande de fonctionnalité",
    "nouvelle fonctionnalité",
]

_BUG_TERMS = [
    "bug", "defect", "fix", "anomaly", "broken", "incorrect",
    "not working", "anomalie", "bogue", "correction", "erreur",
]

_EXISTING_SOLUTION_TERMS = [
    "existing setting", "existing configuration", "already available",
    "existing workaround", "configuration option", "already configured",
    "paramètre existant", "déjà disponible",
]

# ── Category map ──────────────────────────────────────────────────────────────

_CATEGORY_MAP: dict = {
    "legal_reference_removed": "legal",
    "global_change_to_editable": "pm_decision",
    "dev_to_support_guidance": "pm_decision",
    "workaround_added": "pm_decision",
    "bug_feature_framing": "classification",
    "answer_depth_shortened": "tone",
    "existing_solution_added": "pm_decision",
    "classification_correction": "classification",
    "unknown": "general",
}

# ── Instruction map ───────────────────────────────────────────────────────────

_INSTRUCTION_MAP: dict = {
    "legal_reference_removed": (
        "Do not cite law or legal obligation unless PMDecision says "
        "should_mention_law=true or evidence explicitly supports it."
    ),
    "global_change_to_editable": (
        "Prefer editable/configurable per-client wording instead of "
        "global default changes for client preference cases."
    ),
    "dev_to_support_guidance": (
        "For support guidance decisions, do not suggest Jira or development work; "
        "explain the existing workaround or setting to the client instead."
    ),
    "workaround_added": (
        "When an existing workaround or setting is available, mention it explicitly "
        "instead of suggesting development."
    ),
    "bug_feature_framing": (
        "Do not frame a confirmed bug as a feature request or enhancement; "
        "identify and describe it as a bug fix."
    ),
    "answer_depth_shortened": (
        "Keep answers concise; do not over-explain or include unnecessary context. "
        "Match the answer depth to PMDecision answer_depth=short."
    ),
    "existing_solution_added": (
        "When evidence suggests an existing setting or configuration option covers "
        "the request, mention it explicitly rather than proposing development."
    ),
    "classification_correction": (
        "Align the response classification and recommended_action with the "
        "PMDecision deterministic output."
    ),
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _contains_any(text: str, terms: list) -> bool:
    lower = text.lower()
    return any(t in lower for t in terms)


def _truncate(text: str, max_chars: int = 200) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " …"


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _make_lesson(
    lesson_type: str,
    original: str,
    final: str,
    confidence: float,
    template_name: str,
    workflow_name: str,
    instruction: Optional[str] = None,
) -> dict:
    category = _CATEGORY_MAP.get(lesson_type, "general")
    inst = instruction or _INSTRUCTION_MAP.get(lesson_type, "")
    applies_to = template_name.strip() if template_name.strip() else "all"
    return {
        "lesson_type": lesson_type,
        "category": category,
        "before": _truncate(original),
        "after": _truncate(final),
        "instruction": inst,
        "confidence": round(confidence, 2),
        "applies_to": applies_to,
        "template_name": template_name or "",
        "workflow_name": workflow_name or "",
        "source": "pm_structured_edit",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def extract_structured_pm_lessons(
    original_ai_output: str,
    final_po_output: str,
    pm_decision: Optional[dict] = None,
    ticket_subject: str = "",
    template_name: str = "",
    workflow_name: str = "",
) -> list:
    """Extract structured PM lessons from PO edits deterministically.

    No LLM calls.  Returns a list of lesson dicts with stable keys.
    Returns [] if inputs are empty or no meaningful patterns are found.
    """
    if not original_ai_output or not final_po_output:
        return []

    orig = original_ai_output.strip()
    final = final_po_output.strip()
    if orig == final:
        return []

    lessons: list = []
    seen_types: set = set()

    def _add(lesson_type: str, confidence: float, instruction: Optional[str] = None) -> None:
        if lesson_type not in seen_types:
            seen_types.add(lesson_type)
            lessons.append(
                _make_lesson(lesson_type, orig, final, confidence,
                             template_name, workflow_name, instruction)
            )

    # ── Rule 1: legal reference removed ──────────────────────────────────────
    if _contains_any(orig, _LEGAL_TERMS) and not _contains_any(final, _LEGAL_TERMS):
        _add("legal_reference_removed", 0.85)

    # ── Rule 2: global change → editable ─────────────────────────────────────
    if _contains_any(orig, _GLOBAL_CHANGE_TERMS) and _contains_any(final, _EDITABLE_TERMS):
        _add("global_change_to_editable", 0.85)

    # ── Rule 3: dev request → support guidance ────────────────────────────────
    if _contains_any(orig, _DEV_TERMS) and _contains_any(final, _SUPPORT_GUIDANCE_TERMS):
        _add("dev_to_support_guidance", 0.80)

    # ── Rule 4: workaround added (final has it, original does not) ────────────
    if _contains_any(final, _WORKAROUND_TERMS) and not _contains_any(orig, _WORKAROUND_TERMS):
        # Only add if dev_to_support_guidance not already picked up
        if "dev_to_support_guidance" not in seen_types:
            _add("workaround_added", 0.75)

    # ── Rule 5: bug framed as feature request ─────────────────────────────────
    if _contains_any(orig, _FEATURE_REQUEST_TERMS) and _contains_any(final, _BUG_TERMS):
        _add("bug_feature_framing", 0.85)

    # ── Rule 6: answer depth shortened ───────────────────────────────────────
    orig_wc = _word_count(orig)
    final_wc = _word_count(final)
    if orig_wc > 120 and final_wc < orig_wc * 0.6:
        _add("answer_depth_shortened", 0.65)

    # ── Rule 7: existing solution added ──────────────────────────────────────
    if (
        _contains_any(final, _EXISTING_SOLUTION_TERMS)
        and not _contains_any(orig, _EXISTING_SOLUTION_TERMS)
        and "workaround_added" not in seen_types
        and "dev_to_support_guidance" not in seen_types
    ):
        _add("existing_solution_added", 0.75)

    # ── Rule 8: classification correction (pm_decision context) ──────────────
    if pm_decision and isinstance(pm_decision, dict):
        rec_action = pm_decision.get("recommended_action", "")
        classification = pm_decision.get("classification", "")

        # PM says support guidance, original used dev language, final corrected it
        if rec_action in ("explain_workaround", "explain_existing_setting") and (
            _contains_any(orig, _DEV_TERMS) and not _contains_any(final, _DEV_TERMS)
        ):
            if "dev_to_support_guidance" not in seen_types:
                _add(
                    "classification_correction",
                    0.80,
                    instruction=(
                        f"PMDecision recommended_action={rec_action}; "
                        "do not suggest development in the response."
                    ),
                )

        # PM says make_editable, original had global change language
        elif rec_action == "make_editable" and (
            _contains_any(orig, _GLOBAL_CHANGE_TERMS)
            and not _contains_any(final, _GLOBAL_CHANGE_TERMS)
        ):
            if "global_change_to_editable" not in seen_types:
                _add(
                    "classification_correction",
                    0.80,
                    instruction=(
                        "PMDecision recommended_action=make_editable; "
                        "propose per-client editability, not a global change."
                    ),
                )

        # PM says bug, original framed as feature
        elif classification == "bug" and (
            _contains_any(orig, _FEATURE_REQUEST_TERMS)
            and _contains_any(final, _BUG_TERMS)
        ):
            if "bug_feature_framing" not in seen_types:
                _add(
                    "classification_correction",
                    0.80,
                    instruction=(
                        "PMDecision classification=bug; "
                        "frame the response as a bug fix, not a feature request."
                    ),
                )

    return lessons


# ── Lesson → signal mapping ───────────────────────────────────────────────────

_LESSON_SIGNAL_MAP: dict = {
    "legal_reference_removed":  "avoid_legal_references",
    "global_change_to_editable": "prefer_make_editable",
    "dev_to_support_guidance":   "prefer_support_guidance",
    "workaround_added":          "prefer_support_guidance",
    "bug_feature_framing":       "prefer_bug_framing",
    "answer_depth_shortened":    "prefer_short_answer",
    "existing_solution_added":   "prefer_existing_solution",
}


def find_relevant_structured_pm_lessons(
    db,
    ticket_subject: str = "",
    template_name: str = "",
    workflow_name: str = "",
    limit: int = 8,
) -> list:
    """Return active structured PM lessons relevant to this ticket.

    Priority order (SQL ORDER BY):
      1. Same template_name (non-empty match)
      2. Same workflow_name (non-empty match)
      3. Highest hit_count
      4. Highest confidence
      5. Newest created_at

    Returns [] defensively on any error or missing table.
    """
    if db is None:
        return []
    try:
        tmpl = (template_name or "").strip()
        wf = (workflow_name or "").strip()
        rows = db.execute(
            """
            SELECT * FROM pm_structured_lessons
            WHERE active = 1
            ORDER BY
                CASE WHEN template_name = ? AND ? != '' THEN 0 ELSE 1 END,
                CASE WHEN workflow_name  = ? AND ? != '' THEN 0 ELSE 1 END,
                hit_count  DESC,
                confidence DESC,
                created_at DESC
            LIMIT ?
            """,
            (tmpl, tmpl, wf, wf, limit),
        ).fetchall()
        result = []
        for row in rows:
            result.append(dict(row) if hasattr(row, "keys") else row)
        return result
    except Exception as exc:
        logger.warning("find_relevant_structured_pm_lessons failed: %s", exc)
        return []


def format_structured_pm_lessons_for_prompt(lessons: list) -> str:
    """Format active structured PM lessons as a concise prompt block.

    Returns "" when lessons is empty or all instructions are blank.

    Format::

        STRUCTURED PM LESSONS:
        - [lesson_type, XX%, hits N] instruction text
    """
    if not lessons:
        return ""
    lines = ["STRUCTURED PM LESSONS:"]
    for lesson in lessons[:8]:
        ltype = lesson.get("lesson_type") or "unknown"
        conf  = lesson.get("confidence") or 0.0
        hits  = lesson.get("hit_count")  or 1
        instr = (lesson.get("instruction") or "").strip()
        if not instr:
            continue
        conf_pct = int(round(float(conf) * 100))
        lines.append(f"- [{ltype}, {conf_pct}%, hits {hits}] {instr}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def derive_pm_lesson_signals(lessons: list) -> dict:
    """Derive deterministic aggregate boolean signals from a list of lessons.

    Returns::

        {
          "avoid_legal_references": bool,
          "prefer_make_editable":   bool,
          "prefer_support_guidance": bool,
          "prefer_bug_framing":     bool,
          "prefer_short_answer":    bool,
          "prefer_existing_solution": bool,
          "lesson_count":  int,
          "lesson_types":  list[str],
        }

    Mapping rules:
    - legal_reference_removed       → avoid_legal_references
    - global_change_to_editable     → prefer_make_editable
    - dev_to_support_guidance /
      workaround_added              → prefer_support_guidance
    - bug_feature_framing           → prefer_bug_framing
    - answer_depth_shortened        → prefer_short_answer
    - existing_solution_added       → prefer_existing_solution
    - classification_correction     → derived from instruction content only
    """
    signals: dict = {
        "avoid_legal_references":  False,
        "prefer_make_editable":    False,
        "prefer_support_guidance": False,
        "prefer_bug_framing":      False,
        "prefer_short_answer":     False,
        "prefer_existing_solution": False,
        "lesson_count": len(lessons),
        "lesson_types": [],
    }
    seen_types: set = set()
    for lesson in lessons:
        ltype = lesson.get("lesson_type") or "unknown"
        seen_types.add(ltype)
        mapped = _LESSON_SIGNAL_MAP.get(ltype)
        if mapped:
            signals[mapped] = True
        # classification_correction: infer signal from instruction text
        if ltype == "classification_correction":
            instr = (lesson.get("instruction") or "").lower()
            if "make_editable" in instr:
                signals["prefer_make_editable"] = True
            elif "workaround" in instr or "support" in instr:
                signals["prefer_support_guidance"] = True
            elif "bug" in instr:
                signals["prefer_bug_framing"] = True
    signals["lesson_types"] = sorted(seen_types)
    return signals


def upsert_structured_pm_lesson(
    db,
    source_ticket_id,
    lesson: dict,
) -> tuple:
    """Insert or update a structured PM lesson row.

    Deduplication key: lesson_type + instruction + template_name + workflow_name.

    Returns (lesson_id, was_duplicate).
    Returns (None, False) defensively on error.
    """
    try:
        lesson_type = str(lesson.get("lesson_type") or "unknown")
        instruction = str(lesson.get("instruction") or "")
        template_name = str(lesson.get("template_name") or "")
        workflow_name = str(lesson.get("workflow_name") or "")

        row = db.execute(
            """
            SELECT id, hit_count FROM pm_structured_lessons
            WHERE lesson_type = ? AND instruction = ?
              AND template_name = ? AND workflow_name = ?
            LIMIT 1
            """,
            (lesson_type, instruction, template_name, workflow_name),
        ).fetchone()

        if row:
            db.execute(
                """
                UPDATE pm_structured_lessons
                SET hit_count = hit_count + 1,
                    last_reinforced_at = datetime('now')
                WHERE id = ?
                """,
                (row[0],),
            )
            return (row[0], True)

        cur = db.execute(
            """
            INSERT INTO pm_structured_lessons
                (source_ticket_id, template_name, workflow_name,
                 lesson_type, category, before, after,
                 instruction, confidence, applies_to, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_ticket_id,
                template_name,
                workflow_name,
                lesson_type,
                str(lesson.get("category") or "general"),
                str(lesson.get("before") or ""),
                str(lesson.get("after") or ""),
                instruction,
                float(lesson.get("confidence") or 0.0),
                str(lesson.get("applies_to") or "all"),
                str(lesson.get("source") or "pm_structured_edit"),
            ),
        )
        return (cur.lastrowid, False)

    except Exception as exc:
        logger.warning("upsert_structured_pm_lesson failed: %s", exc)
        return (None, False)
