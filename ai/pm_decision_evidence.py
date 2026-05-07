"""PM decision evidence extractor.

Pure Python — no LLM calls, no DB calls.
Works with both plain dicts and sqlite3.Row-like objects.

Three public functions:

  extract_pm_ticket_summary(ticket, conversations=None) -> str
  extract_pm_current_behaviour(ticket, code_brief="", analysis="") -> str
  extract_pm_evidence(ticket, code_brief="", analysis="", kb_brief="") -> dict
"""
from __future__ import annotations

import html as _html_lib
import re
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

# ── Character limits ──────────────────────────────────────────────────────────
_MAX_SUMMARY_CHARS = 1000
_MAX_CURRENT_BEHAVIOUR_CHARS = 800

# ── Keyword sets for evidence signals ────────────────────────────────────────

_LEGAL_TERMS = [
    "legal", "loi ", "article ", "mandatory", "obligatoire", "obligation",
    "regulation", "regulatory", "compliance", "law ", "required by",
    "ecdf", "pcn", "rgd", "ifrs", "gaap", "code de commerce",
    "lux", "luxembourg law", "accounting standard",
]

_CUSTOM_WORDING_TERMS = [
    "our wording", "our own wording", "our preferred",
    "client wording", "preferred wording", "we prefer", "we want",
    "we'd like", "we would like", "custom wording", "our label",
    "our text", "preferred text", "libellé", "libelle", "formulation",
    "reformuler", "notre formulation", "notre texte",
]

_WORKAROUND_TERMS = [
    "workaround", "how to use", "how to set up", "how do i",
    "how can i", "how-to", "existing feature", "existing setting",
    "already exists", "can i use", "is there a way", "comment faire",
    "comment utiliser", "contournement",
]

_CORRECT_BEHAVIOUR_TERMS = [
    "correct", "standard", "expected", "accurate", "working as designed",
    "working as intended", "by design", "is correct", "is standard",
    "is expected", "wording is correct", "current wording",
    "comportement attendu", "conforme",
]

_WRONG_OUTPUT_TERMS = [
    "wrong", "incorrect", "error", "bug", "broken", "not working",
    "doesn't work", "does not work", "incorrect output", "wrong result",
    "wrong calculation", "ne fonctionne pas", "mauvais résultat",
    "résultat incorrect", "erreur", "calcul incorrect",
]


# ── Private helpers ───────────────────────────────────────────────────────────

def _get(obj: object, key: str, default: str = "") -> str:
    """Safely retrieve a string field from a dict or sqlite3.Row-like object."""
    try:
        val = obj[key]  # type: ignore[index]
        return str(val) if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


def _strip_html(text: str) -> str:
    """Minimal HTML stripper — mirrors app.strip_html without importing it."""
    if not text:
        return ""
    text = _html_lib.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _contains_any(text: str, terms: list) -> bool:
    """Return True when *text* (lower-cased) contains at least one term."""
    lower = text.lower()
    return any(t in lower for t in terms)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " …"


# ── Public API ────────────────────────────────────────────────────────────────

def extract_pm_ticket_summary(
    ticket: object,
    conversations: Optional[List] = None,
) -> str:
    """Build a concise ticket summary from subject + description.

    Parameters
    ----------
    ticket:
        A dict or sqlite3.Row-like with at least 'subject' and optionally
        'description_text' / 'description'.
    conversations:
        Optional list of conversation dicts; the first customer message body
        is appended when the description is very short (< 100 chars).

    Returns
    -------
    str
        Plain-text summary, max ~1000 chars.
    """
    subject = _get(ticket, "subject", "").strip()

    # Prefer pre-stripped description_text; fall back to HTML description
    desc = _get(ticket, "description_text", "").strip()
    if not desc:
        raw_desc = _get(ticket, "description", "")
        desc = _strip_html(raw_desc).strip()

    # If description is very short and conversations are available, append
    # the first customer message to give the gates more signal.
    if len(desc) < 100 and conversations:
        for conv in conversations:
            try:
                if conv.get("incoming", True):
                    extra = _strip_html(conv.get("body", "")).strip()
                    if extra:
                        desc = f"{desc}\n{extra}".strip()
                        break
            except Exception:
                pass

    parts = [p for p in (subject, desc) if p]
    summary = "\n".join(parts)
    return _truncate(summary, _MAX_SUMMARY_CHARS)


def extract_pm_current_behaviour(
    ticket: object,
    code_brief: str = "",
    analysis: str = "",
) -> str:
    """Build a description of what the system currently does.

    Priority:
      1. code_brief — most authoritative (comes from Code Agent describing template logic)
      2. analysis   — fallback (AI analysis may describe current state)

    Only the first *_MAX_CURRENT_BEHAVIOUR_CHARS* characters are returned.
    """
    # Code brief is the best source: the Code Agent explicitly describes what
    # the template currently does in plain language.
    if code_brief:
        return _truncate(code_brief.strip(), _MAX_CURRENT_BEHAVIOUR_CHARS)

    # Fallback: the AI analysis describes behaviour in its own words.
    if analysis:
        return _truncate(analysis.strip(), _MAX_CURRENT_BEHAVIOUR_CHARS)

    return ""


def extract_pm_evidence(
    ticket: object,
    code_brief: str = "",
    analysis: str = "",
    kb_brief: str = "",
) -> dict:
    """Extract explicit evidence signals from available ticket context.

    Returns a dict of boolean signals and a ``source_fields`` list.
    None of these signals alone set ``should_mention_law=True`` — that
    decision remains inside the legal_preference_gate which requires an
    *explicit* mandatory evidence key.

    Keys returned
    -------------
    has_code_context          : bool  — code_brief is non-empty
    has_analysis_context      : bool  — analysis is non-empty
    has_kb_context            : bool  — kb_brief is non-empty
    mentions_legal_terms      : bool  — legal words appear in ticket/analysis
    mentions_custom_wording   : bool  — client's own-wording preference detected
    mentions_existing_workaround : bool — workaround / how-to language detected
    mentions_correct_current_behaviour : bool — current behaviour described as correct
    mentions_wrong_output     : bool  — wrong / incorrect / bug language detected
    source_fields             : list[str] — field names that contributed non-empty text
    """
    subject = _get(ticket, "subject", "")
    desc = _get(ticket, "description_text", "").strip()
    if not desc:
        desc = _strip_html(_get(ticket, "description", ""))

    # Combined text for keyword scanning
    ticket_text = f"{subject} {desc}".lower()
    context_text = f"{ticket_text} {analysis.lower()} {code_brief.lower()}"

    source_fields: list = []
    if subject:
        source_fields.append("subject")
    if desc:
        source_fields.append("description")
    if code_brief:
        source_fields.append("code_brief")
    if analysis:
        source_fields.append("analysis")
    if kb_brief:
        source_fields.append("kb_brief")

    return {
        "has_code_context": bool(code_brief),
        "has_analysis_context": bool(analysis),
        "has_kb_context": bool(kb_brief),
        # Signal only — does NOT imply legal obligation (gate decides that)
        "mentions_legal_terms": _contains_any(context_text, _LEGAL_TERMS),
        "mentions_custom_wording": _contains_any(ticket_text, _CUSTOM_WORDING_TERMS),
        "mentions_existing_workaround": _contains_any(ticket_text, _WORKAROUND_TERMS),
        # Current-behaviour signals use analysis/code where we know what it does
        "mentions_correct_current_behaviour": _contains_any(
            f"{analysis.lower()} {code_brief.lower()}", _CORRECT_BEHAVIOUR_TERMS
        ),
        "mentions_wrong_output": _contains_any(ticket_text, _WRONG_OUTPUT_TERMS),
        "source_fields": source_fields,
    }
