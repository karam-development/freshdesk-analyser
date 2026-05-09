"""KB retrieval — deterministic keyword-based knowledge-base lookup.

No LLM calls. No writes. Pure Python + SQLite reads.

Public functions
----------------
normalize_text(text) -> str
    Lowercase and strip non-alphanumeric characters for comparison.

extract_ticket_keywords(subject, summary, template_name, workflow_name) -> list[str]
    Derive a de-duplicated keyword list from ticket metadata.

retrieve_relevant_kb_entries(db, subject, summary, template_name,
                             workflow_name, limit=8) -> list[dict]
    Query the knowledge_base table and return the top-N scored entries.
    Each entry dict has: id, category, title, content, score, matched_terms,
    evidence_type.

summarize_kb_evidence(entries, max_chars=2000) -> str
    Format entries into a compact prompt block or return "" when empty.

derive_kb_evidence_signals(entries) -> dict
    Aggregate boolean signals from a list of retrieved KB entries.
"""
from __future__ import annotations

import re
from typing import List, Optional

# ── Evidence-type classification ──────────────────────────────────────────────

_LEGAL_CATEGORY_TERMS = [
    "legal", "law", "regulation", "compliance", "mandatory",
    "statutory", "regulatory", "obligation", "gdpr", "lgpd", "hipaa",
]
_WORKAROUND_CATEGORY_TERMS = [
    "workaround", "guide", "how-to", "how to", "tutorial",
    "procedure", "instructions", "tip", "trick",
]
_SETTING_CATEGORY_TERMS = [
    "setting", "configuration", "feature", "option", "parameter",
    "config", "setup", "preference",
]
_PRODUCT_CATEGORY_TERMS = [
    "product", "standard", "default", "behaviour", "behavior",
    "design", "architecture", "specification",
]
_TERMINOLOGY_CATEGORY_TERMS = [
    "terminology", "glossary", "label", "wording", "term",
    "vocabulary", "definition", "lexicon",
]

# Content-level clue terms (for evidence_type when category is ambiguous)
_LEGAL_CONTENT_TERMS = [
    "required by law", "legally required", "legal requirement",
    "mandatory by regulation", "must include", "must display",
    "statutory requirement", "compliance requirement",
    "exigence légale", "obligation légale", "requis par la loi",
]
_WORKAROUND_CONTENT_TERMS = [
    "workaround", "bypass", "alternative approach", "can be done by",
    "can be achieved by", "there is a way to",
    "contournement", "solution de contournement",
]
_SETTING_CONTENT_TERMS = [
    "existing setting", "there is a setting", "configuration option",
    "you can configure", "already available", "option exists",
    "can be configured", "use the setting",
    "paramètre existant", "option de configuration",
]


# ── Stop-words (filtered out from keywords) ───────────────────────────────────

_STOP_WORDS = {
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "for",
    "and", "or", "but", "not", "with", "this", "that", "from", "are",
    "was", "be", "been", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might",
    "we", "our", "they", "their", "he", "she", "you", "your", "its",
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou",
    "en", "au", "aux", "par", "pour", "sur", "dans", "avec", "est",
    "sont", "que", "qui", "ce", "se", "il", "elle", "nous", "vous",
    # short noise words
    "s", "t", "d", "l", "m", "n", "j", "y",
}

# ── Private helpers ────────────────────────────────────────────────────────────


def _contains_any(text: str, terms: list) -> bool:
    lower = text.lower()
    return any(t in lower for t in terms)


def _classify_evidence_type(category: str, content: str) -> str:
    """Return one of: legal_evidence | workaround_evidence | existing_setting_evidence
    | product_evidence | terminology_evidence | general_evidence."""
    cat = (category or "").lower()
    cnt = (content or "").lower()

    if _contains_any(cat, _LEGAL_CATEGORY_TERMS) or _contains_any(cnt, _LEGAL_CONTENT_TERMS):
        return "legal_evidence"
    if _contains_any(cat, _WORKAROUND_CATEGORY_TERMS) or _contains_any(cnt, _WORKAROUND_CONTENT_TERMS):
        return "workaround_evidence"
    if _contains_any(cat, _SETTING_CATEGORY_TERMS) or _contains_any(cnt, _SETTING_CONTENT_TERMS):
        return "existing_setting_evidence"
    if _contains_any(cat, _PRODUCT_CATEGORY_TERMS):
        return "product_evidence"
    if _contains_any(cat, _TERMINOLOGY_CATEGORY_TERMS):
        return "terminology_evidence"
    return "general_evidence"


# ── Public API ─────────────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Lowercase and collapse non-alphanumeric runs to a single space."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def extract_ticket_keywords(
    subject: str = "",
    summary: str = "",
    template_name: str = "",
    workflow_name: str = "",
) -> List[str]:
    """Return a de-duplicated keyword list derived from ticket metadata.

    Short words (<= 2 chars) and common stop-words are removed.
    Template/workflow names are kept intact as multi-word strings when present.
    """
    seen: set = set()
    keywords: list = []

    def _add(token: str) -> None:
        token = token.strip()
        if token and token not in seen:
            seen.add(token)
            keywords.append(token)

    # Normalised individual tokens from subject + summary
    combined = f"{subject} {summary}"
    for word in normalize_text(combined).split():
        if len(word) > 2 and word not in _STOP_WORDS:
            _add(word)

    # Preserve template/workflow names as searchable phrases
    if template_name:
        _add(normalize_text(template_name))
        # Also add individual tokens from the name
        for w in normalize_text(template_name).split():
            if len(w) > 2 and w not in _STOP_WORDS:
                _add(w)

    if workflow_name:
        _add(normalize_text(workflow_name))
        for w in normalize_text(workflow_name).split():
            if len(w) > 2 and w not in _STOP_WORDS:
                _add(w)

    return keywords


def retrieve_relevant_kb_entries(
    db,
    subject: str = "",
    summary: str = "",
    template_name: str = "",
    workflow_name: str = "",
    limit: int = 8,
) -> List[dict]:
    """Query the knowledge_base table and return the top-N scored entries.

    Scoring rules (additive):
      +4  exact normalised subject phrase in title
      +3  keyword exact-match in title
      +2  keyword exact-match in content
      +2  template_name / workflow_name match in title or content
      +1  keyword appears anywhere in content (partial)

    Returns
    -------
    list of dict
        Each dict has: id, category, title, content, score (int),
        matched_terms (list[str]), evidence_type (str).
        Ordered by score descending. Empty list on any error.
    """
    try:
        rows = db.execute(
            "SELECT id, category, title, content FROM knowledge_base ORDER BY category, title"
        ).fetchall()
    except Exception:
        return []

    if not rows:
        return []

    keywords = extract_ticket_keywords(
        subject=subject,
        summary=summary,
        template_name=template_name,
        workflow_name=workflow_name,
    )

    norm_subject = normalize_text(subject)
    norm_template = normalize_text(template_name)
    norm_workflow = normalize_text(workflow_name)

    scored: list = []

    for row in rows:
        title_raw = row["title"] or ""
        content_raw = row["content"] or ""
        category_raw = row["category"] or ""

        norm_title = normalize_text(title_raw)
        norm_content = normalize_text(content_raw)

        score = 0
        matched: list = []

        # Exact normalised subject phrase match
        if norm_subject and norm_subject in norm_title:
            score += 4
            matched.append(f"subject_in_title:{norm_subject[:30]}")
        elif norm_subject and norm_subject in norm_content:
            score += 2
            matched.append(f"subject_in_content:{norm_subject[:30]}")

        # Template / workflow name match
        if norm_template and (norm_template in norm_title or norm_template in norm_content):
            score += 2
            matched.append(f"template:{template_name[:30]}")

        if norm_workflow and (norm_workflow in norm_title or norm_workflow in norm_content):
            score += 2
            matched.append(f"workflow:{workflow_name[:30]}")

        # Per-keyword scoring
        for kw in keywords:
            if len(kw) < 3:
                continue
            norm_kw = normalize_text(kw)
            if not norm_kw:
                continue

            in_title = norm_kw in norm_title
            in_content = norm_kw in norm_content

            if in_title:
                score += 3
                matched.append(f"title:{kw}")
            elif in_content:
                score += 1
                matched.append(f"content:{kw}")

        if score > 0:
            scored.append({
                "id": row["id"],
                "category": category_raw,
                "title": title_raw,
                "content": content_raw,
                "score": score,
                "matched_terms": matched,
                "evidence_type": _classify_evidence_type(category_raw, content_raw),
            })

    # Sort by score descending; stable secondary sort by id ascending
    scored.sort(key=lambda e: (-e["score"], e["id"]))
    return scored[:limit]


def summarize_kb_evidence(
    entries: List[dict],
    max_chars: int = 2000,
) -> str:
    """Format retrieved KB entries into a compact prompt block.

    Returns an empty string when *entries* is empty.

    Format::

        RELEVANT KB EVIDENCE:
        - [evidence_type | score 5] Title: first 200 chars of content...
        - ...
    """
    if not entries:
        return ""

    lines: list = []
    total = 0

    for entry in entries:
        evidence_type = entry.get("evidence_type", "general_evidence")
        score = entry.get("score", 0)
        title = (entry.get("title") or "").strip()
        content = (entry.get("content") or "").strip()

        snippet = content[:200].replace("\n", " ")
        if len(content) > 200:
            snippet += "..."

        line = f"- [{evidence_type} | score {score}] {title}: {snippet}"

        if total + len(line) > max_chars:
            break

        lines.append(line)
        total += len(line) + 1  # +1 for newline

    if not lines:
        return ""

    return "RELEVANT KB EVIDENCE:\n" + "\n".join(lines)


def derive_kb_evidence_signals(entries: List[dict]) -> dict:
    """Aggregate boolean signals from a list of retrieved KB entries.

    Returns
    -------
    dict with keys:
        has_legal_evidence          : bool
        has_workaround_evidence     : bool
        has_existing_setting_evidence : bool
        has_product_evidence        : bool
        has_terminology_evidence    : bool
        kb_evidence_types           : list[str]  (unique evidence_types found)
        kb_evidence_count           : int
        matched_terms               : list[str]  (all unique matched_terms)
    """
    if not entries:
        return {
            "has_legal_evidence": False,
            "has_workaround_evidence": False,
            "has_existing_setting_evidence": False,
            "has_product_evidence": False,
            "has_terminology_evidence": False,
            "kb_evidence_types": [],
            "kb_evidence_count": 0,
            "matched_terms": [],
        }

    evidence_types: set = set()
    all_terms: list = []
    seen_terms: set = set()

    for entry in entries:
        et = entry.get("evidence_type", "general_evidence")
        evidence_types.add(et)
        for term in (entry.get("matched_terms") or []):
            if term not in seen_terms:
                seen_terms.add(term)
                all_terms.append(term)

    return {
        "has_legal_evidence": "legal_evidence" in evidence_types,
        "has_workaround_evidence": "workaround_evidence" in evidence_types,
        "has_existing_setting_evidence": "existing_setting_evidence" in evidence_types,
        "has_product_evidence": "product_evidence" in evidence_types,
        "has_terminology_evidence": "terminology_evidence" in evidence_types,
        "kb_evidence_types": sorted(evidence_types),
        "kb_evidence_count": len(entries),
        "matched_terms": all_terms,
    }
