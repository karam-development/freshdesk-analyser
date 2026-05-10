"""KB retrieval — deterministic keyword-based knowledge-base lookup.

No LLM calls. No writes. Pure Python + SQLite reads.

Public functions
----------------
normalize_text(text) -> str
    Lowercase and strip non-alphanumeric characters for comparison.

extract_ticket_keywords(subject, summary, template_name, workflow_name) -> list[str]
    Derive a de-duplicated keyword list from ticket metadata.

retrieve_relevant_kb_entries(db, subject, summary, template_name,
                             workflow_name, limit=8, min_score=3) -> list[dict]
    Query the knowledge_base table and return the top-N scored entries.
    Each entry dict has: id, category, title, content, score, matched_terms,
    evidence_type, score_reasons.

summarize_kb_evidence(entries, max_chars=2000) -> str
    Format entries into a compact prompt block or return "" when empty.

derive_kb_evidence_signals(entries) -> dict
    Aggregate boolean signals from a list of retrieved KB entries.

Scoring model (PR 22)
---------------------
  +5  exact normalised subject phrase in title (multi-word subjects only)
  +5  template_name phrase match in title / content / category
  +4  keyword in title
  +4  workflow_name phrase match in title / content / category
  +3  keyword in category (not in title)
  +3  workaround / setting context boost (ticket has wording/config context)
  +2  legal context boost (legal ticket + legal entry + ≥1 other match)
  +1  keyword in content (not in title or category)
  −2  legal entry but no legal signal in ticket (conservative penalty)

  min_score = 3  (default): single weak content-only matches are suppressed.

Evidence-type priority (legal > existing_setting > workaround > product > terminology > general)
"""
from __future__ import annotations

import re
from typing import List

# ── Evidence-type category signals ────────────────────────────────────────────

_LEGAL_CATEGORY_TERMS = [
    "legal", "law", "regulation", "statutory", "regulatory",
    "mandatory", "obligation", "gdpr", "lgpd", "hipaa", "rgd", "ecdf",
]
_SETTING_CATEGORY_TERMS = [
    "setting", "configuration", "configurable", "feature", "option",
    "parameter", "config", "setup", "preference", "toggle",
]
_WORKAROUND_CATEGORY_TERMS = [
    "workaround", "workarounds", "bypass", "alternative",
]
_PRODUCT_CATEGORY_TERMS = [
    "product", "standard", "default", "behaviour", "behavior",
    "design", "architecture", "specification",
]
_TERMINOLOGY_CATEGORY_TERMS = [
    "terminology", "glossary", "label", "wording", "term",
    "vocabulary", "definition", "lexicon", "translation",
]

# ── Evidence-type content signals ─────────────────────────────────────────────

# Legal — requires strong explicit legal terminology
_LEGAL_CONTENT_TERMS = [
    "required by law", "legally required", "legal requirement", "legal obligation",
    "mandatory by regulation", "statutory requirement",
    "obligation légale", "exigence légale", "requis par la loi",
    "rgd", "ecdf", "accounting requirement",
]

# Workaround — specific workaround / alternative language
_WORKAROUND_CONTENT_TERMS = [
    "workaround", "bypass", "alternative approach", "can be done by",
    "can be achieved by", "there is a way to",
    "temporary solution", "can already be done", "manual workaround",
    "instead of", "alternative to",
    "contournement", "solution de contournement",
]

# Existing setting — configuration / option already available
_SETTING_CONTENT_TERMS = [
    "existing setting", "setting already exists", "there is a setting",
    "configuration option", "you can configure", "already available",
    "option exists", "can be configured", "use the setting",
    "configurable", "toggle", "dropdown", "option available",
    "paramètre existant", "option de configuration",
]

# Product — describes current product behaviour / standard
_PRODUCT_CONTENT_TERMS = [
    "current behaviour", "template pattern", "product standard",
    "existing feature", "supported", "not supported",
    "working as designed", "working as intended", "by design",
    "comportement actuel", "comportement standard",
]

# ── Ticket context detection (for scoring boosts/penalties) ──────────────────

# Terms that indicate the ticket is about a legal/regulatory matter
_TICKET_LEGAL_SIGNAL_TERMS = [
    "law", "legal", "article", "regulation", "rgd", "ecdf",
    "mandatory", "obligatory", "obligation", "statutory",
    "required by law", "accounting requirement",
]

# Terms that indicate the ticket wants a workaround / configurable change
_TICKET_WORKAROUND_CONTEXT_TERMS = [
    "workaround", "alternative", "setting", "configuration", "configure",
    "configurable", "option", "editable", "custom", "bypass",
    "instead", "different approach",
]

# ── Stop-words ────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    # Common English function words
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "for",
    "and", "or", "but", "not", "with", "this", "that", "from", "are",
    "was", "be", "been", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might",
    "we", "our", "they", "their", "he", "she", "you", "your", "its",
    # Common French function words
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou",
    "en", "au", "aux", "par", "pour", "sur", "dans", "avec", "est",
    "sont", "que", "qui", "ce", "se", "il", "elle", "nous", "vous",
    # Very short noise tokens
    "s", "t", "d", "l", "m", "n", "j", "y",
    # Generic support / ticket wording (PR 22 additions)
    "issue", "problem", "request", "question", "client", "customer",
    "ticket", "note", "template", "change", "changes", "wrong", "error",
    "please", "need", "needs", "want", "wants", "possible",
    "display", "show", "showing",
}

# ── Private helpers ────────────────────────────────────────────────────────────


def _contains_any(text: str, terms: list) -> bool:
    lower = text.lower()
    return any(t in lower for t in terms)


def _classify_evidence_type(category: str, content: str) -> str:
    """Classify a KB entry.

    Priority (first match wins):
      legal_evidence (requires strong legal terms)
      → existing_setting_evidence
      → workaround_evidence
      → product_evidence
      → terminology_evidence
      → general_evidence
    """
    cat = (category or "").lower()
    cnt = (content or "").lower()

    # Legal — category OR strong content terms
    if _contains_any(cat, _LEGAL_CATEGORY_TERMS) or _contains_any(cnt, _LEGAL_CONTENT_TERMS):
        return "legal_evidence"

    # Existing setting — category OR specific content terms
    if _contains_any(cat, _SETTING_CATEGORY_TERMS) or _contains_any(cnt, _SETTING_CONTENT_TERMS):
        return "existing_setting_evidence"

    # Workaround
    if _contains_any(cat, _WORKAROUND_CATEGORY_TERMS) or _contains_any(cnt, _WORKAROUND_CONTENT_TERMS):
        return "workaround_evidence"

    # Product behaviour / standard
    if _contains_any(cat, _PRODUCT_CATEGORY_TERMS) or _contains_any(cnt, _PRODUCT_CONTENT_TERMS):
        return "product_evidence"

    # Terminology / glossary
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
    """Return a de-duplicated keyword list from ticket metadata.

    Filters:
    - Stop-words and very short tokens (≤ 2 chars).
    - Generic support/ticket words (issue, problem, client, display, etc.).
    - Multi-word template/workflow phrases are preserved as searchable tokens
      even when their individual words are generic.
    """
    seen: set = set()
    keywords: list = []

    def _add(token: str) -> None:
        token = token.strip()
        if token and token not in seen:
            seen.add(token)
            keywords.append(token)

    # Individual tokens from subject + summary
    combined = f"{subject} {summary}"
    for word in normalize_text(combined).split():
        if len(word) > 2 and word not in _STOP_WORDS:
            _add(word)

    # Template/workflow: add as a full phrase AND as individual meaningful tokens.
    # The phrase is always added (even if it contains generic-ish words) because
    # specificity comes from the combination, not individual words.
    if template_name:
        phrase = normalize_text(template_name)
        if phrase:
            _add(phrase)  # multi-word phrase for phrase-level scoring
        for w in phrase.split():
            if len(w) > 2 and w not in _STOP_WORDS:
                _add(w)

    if workflow_name:
        phrase = normalize_text(workflow_name)
        if phrase:
            _add(phrase)
        for w in phrase.split():
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
    min_score: float = 3.0,
) -> List[dict]:
    """Query the knowledge_base table and return top-N scored entries.

    Scoring (additive, see module docstring for full table).
    Entries with score < min_score are discarded to suppress noise.

    Returns
    -------
    list of dict
        Keys: id, category, title, content, score (float), matched_terms
        (list[str]), evidence_type (str), score_reasons (list[str]).
        Ordered by score descending then id ascending.
        Empty list on any DB error.
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

    # Ticket-level context flags (used for evidence type boosts / penalties)
    ticket_text = normalize_text(f"{subject} {summary}")
    has_legal_signal = _contains_any(ticket_text, _TICKET_LEGAL_SIGNAL_TERMS)
    has_workaround_context = _contains_any(ticket_text, _TICKET_WORKAROUND_CONTEXT_TERMS)

    scored: list = []

    for row in rows:
        title_raw = row["title"] or ""
        content_raw = row["content"] or ""
        category_raw = row["category"] or ""

        norm_title = normalize_text(title_raw)
        norm_content = normalize_text(content_raw)
        norm_category = normalize_text(category_raw)

        score: float = 0.0
        score_reasons: list = []
        matched: list = []

        # ── Phrase-level matches ──────────────────────────────────────────────

        # Exact normalised subject phrase in title only (multi-word subjects).
        # Content matching is handled entirely by the per-keyword loop to avoid
        # double-counting. Single-word subjects are also covered by the keyword loop.
        if norm_subject and " " in norm_subject and norm_subject in norm_title:
            score += 5
            score_reasons.append("subject_phrase:title +5")
            matched.append(f"subject_in_title:{norm_subject[:30]}")

        # Template phrase match (title / content / category)
        if norm_template:
            if (norm_template in norm_title
                    or norm_template in norm_content
                    or norm_template in norm_category):
                score += 5
                score_reasons.append("template_phrase:match +5")
                matched.append(f"template:{template_name[:30]}")

        # Workflow phrase match
        if norm_workflow:
            if (norm_workflow in norm_title
                    or norm_workflow in norm_content
                    or norm_workflow in norm_category):
                score += 4
                score_reasons.append("workflow_phrase:match +4")
                matched.append(f"workflow:{workflow_name[:30]}")

        # ── Per-keyword scoring ───────────────────────────────────────────────
        for kw in keywords:
            if len(kw) < 3:
                continue
            norm_kw = normalize_text(kw)
            if not norm_kw:
                continue
            # Skip multi-word phrases — already handled at phrase level above
            if " " in norm_kw:
                continue

            in_title = norm_kw in norm_title
            in_category = norm_kw in norm_category
            in_content = norm_kw in norm_content

            if in_title:
                score += 4
                score_reasons.append(f"title:{kw} +4")
                matched.append(f"title:{kw}")
            elif in_category:
                score += 3
                score_reasons.append(f"category:{kw} +3")
                matched.append(f"category:{kw}")
            elif in_content:
                score += 1
                score_reasons.append(f"content:{kw} +1")
                matched.append(f"content:{kw}")

        # ── Evidence type context boost / penalty ─────────────────────────────
        ev_type = _classify_evidence_type(category_raw, content_raw)

        if ev_type in ("workaround_evidence", "existing_setting_evidence"):
            if has_workaround_context:
                score += 3
                score_reasons.append("evidence_type:workaround_context +3")
                matched.append("evidence_type:context_boost")

        elif ev_type == "legal_evidence":
            if has_legal_signal and score > 0:
                # Contextual boost: ticket is about a legal matter AND entry matched
                score += 2
                score_reasons.append("evidence_type:legal_context +2")
                matched.append("evidence_type:legal_boost")
            elif not has_legal_signal:
                # Conservative penalty: do not surface legal entries for non-legal tickets
                score -= 2
                score_reasons.append("legal_no_context_penalty -2")

        # ── Min-score filter ──────────────────────────────────────────────────
        if score >= min_score:
            scored.append({
                "id": row["id"],
                "category": category_raw,
                "title": title_raw,
                "content": content_raw,
                "score": score,
                "matched_terms": matched,
                "evidence_type": ev_type,
                "score_reasons": score_reasons,
            })

    # Sort by score descending; stable secondary key: id ascending
    scored.sort(key=lambda e: (-e["score"], e["id"]))
    return scored[:limit]


def summarize_kb_evidence(
    entries: List[dict],
    max_chars: int = 2000,
) -> str:
    """Format retrieved KB entries into a compact prompt block.

    Returns an empty string when *entries* is empty.
    Tolerates extra keys such as ``score_reasons`` in entries.

    Format::

        RELEVANT KB EVIDENCE:
        - [evidence_type | score 5] Title: first 200 chars of content...
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
        total += len(line) + 1

    if not lines:
        return ""

    return "RELEVANT KB EVIDENCE:\n" + "\n".join(lines)


def retrieve_hybrid_kb_entries(
    db,
    ticket_context: dict,
    keyword_entries: List[dict],
    semantic_entries: List[dict],
    top_n: int = 8,
) -> List[dict]:
    """Merge keyword and semantic KB entries into a single ranked list.

    Rules
    -----
    - Keyword entries are the primary results and keep their original scores.
    - Semantic entries not already covered by keyword results are appended.
    - Deduplication is by ``entry_id`` (falling back to normalised title).
    - Entries that appear in both sets receive ``source="hybrid"``.
    - Keyword-only entries receive ``source="keyword"``.
    - Semantic-only entries receive ``source="semantic"``.
    - The merged list is capped to *top_n*.

    Parameters
    ----------
    db :
        Unused in current implementation; reserved for future score fusion.
    ticket_context : dict
        Unused in current implementation; reserved for future re-ranking.
    keyword_entries : list[dict]
        Entries from ``retrieve_relevant_kb_entries``.
    semantic_entries : list[dict]
        Entries from ``build_semantic_evidence_entries``.
    top_n : int
        Maximum number of entries to return.

    Returns
    -------
    list[dict]
        Does NOT alter ``retrieve_relevant_kb_entries`` default behaviour —
        this function is only called when semantic RAG is explicitly enabled.
        Never raises.
    """
    try:
        merged: List[dict] = []
        seen_ids: set = set()

        def _entry_key(e: dict) -> str:
            raw_id = e.get("entry_id") or e.get("id")
            if raw_id is not None:
                return str(raw_id)
            return normalize_text(e.get("title") or "")

        # Pass 1: keyword entries (primary, mark as keyword)
        for entry in (keyword_entries or []):
            key = _entry_key(entry)
            e = dict(entry)
            e["source"] = "keyword"
            merged.append(e)
            if key:
                seen_ids.add(key)

        # Pass 2: semantic entries — upgrade to hybrid if duplicate, else append
        for entry in (semantic_entries or []):
            key = _entry_key(entry)
            if key and key in seen_ids:
                # Mark the existing keyword entry as hybrid
                for m in merged:
                    if _entry_key(m) == key:
                        m["source"] = "hybrid"
                        break
            else:
                e = dict(entry)
                e["source"] = "semantic"
                merged.append(e)
                if key:
                    seen_ids.add(key)

        return merged[:top_n]
    except Exception:
        # Fail-safe: return keyword results unchanged
        return list(keyword_entries or [])[:top_n]


def prepare_kb_entries_for_semantic(entries: List[dict]) -> List[dict]:
    """Build semantic-ready chunk records from retrieved KB entries.

    This is a thin bridge to ``ai.kb_semantic_foundation.build_semantic_kb_records``.
    It is provided here for convenience so callers can stay within this module.

    Important
    ---------
    - Does NOT change ``retrieve_relevant_kb_entries`` in any way.
    - Does NOT persist records to the DB.
    - Should NOT be called from production routes yet (PR 37 is foundation-only).
    - Safe to call at any time: returns ``[]`` on import failure or empty input.

    Parameters
    ----------
    entries : list[dict]
        Typically the output of ``retrieve_relevant_kb_entries``.

    Returns
    -------
    list[dict]  — semantic records as defined in ``kb_semantic_foundation``.
    """
    try:
        from ai.kb_semantic_foundation import build_semantic_kb_records  # noqa: PLC0415
        return build_semantic_kb_records(entries)
    except Exception:
        return []


def derive_kb_evidence_signals(entries: List[dict]) -> dict:
    """Aggregate boolean signals from a list of retrieved KB entries.

    Unaffected by the addition of ``score_reasons`` to entry dicts.

    Returns
    -------
    dict with keys:
        has_legal_evidence            : bool
        has_workaround_evidence       : bool
        has_existing_setting_evidence : bool
        has_product_evidence          : bool
        has_terminology_evidence      : bool
        kb_evidence_types             : list[str]
        kb_evidence_count             : int
        matched_terms                 : list[str]
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
