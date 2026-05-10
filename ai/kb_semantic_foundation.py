"""Semantic KB retrieval foundation — chunking, normalisation, and metadata helpers.

No embeddings.  No API calls.  No DB writes.  Pure Python.

This module prepares the KB system for future semantic / RAG retrieval by providing
deterministic chunking and metadata helpers.  Current production retrieval in
``ai/kb_retrieval.py`` is NOT changed.

Public functions
----------------
normalize_kb_text_for_semantic(text) -> str
    Strip HTML tags, collapse whitespace, preserve casing and meaningful punctuation.

chunk_kb_text(text, max_chars=1200, overlap_chars=150) -> list[str]
    Split text into overlapping chunks with preference for paragraph / sentence
    boundaries.  Returns an empty list for empty / whitespace-only input.

build_semantic_kb_records(entries, max_chars=1200, overlap_chars=150) -> list[dict]
    Produce stable, semantic-ready records from a list of raw KB entry dicts.
    Invalid or empty entries are silently skipped.

Record shape
------------
{
  "record_id":     str,   # stable SHA-256 prefix of (entry_id, title, chunk_index, chunk)
  "entry_id":      str,   # entry["id"] → entry["entry_id"] → hash(title+content)
  "chunk_index":   int,
  "title":         str,
  "category":      str,
  "evidence_type": str,
  "text":          str,   # semantic-friendly: "<title>. <chunk>"
  "source_text":   str,   # raw chunk (no title prefix)
  "metadata":      dict,  # title, category, evidence_type, chunk_index,
                          # total_chunks, source_fields
}

Design notes
------------
- Fully deterministic: same input → same output on every call.
- Defensive: never raises; invalid entries are skipped.
- No mutation of input entries.
- No API calls, no DB reads or writes.
- Casing is preserved: legal / accounting / entity names are case-sensitive.
"""
from __future__ import annotations

import hashlib
import re
from typing import List

# ── HTML stripping ─────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)

# Common HTML entities relevant in legal / accounting / support text
_ENTITY_MAP: dict = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&nbsp;": " ",
    "&ndash;": "–",
    "&mdash;": "—",
    "&laquo;": "«",
    "&raquo;": "»",
    "&hellip;": "…",
}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common HTML entities."""
    text = _HTML_TAG_RE.sub(" ", text)
    for entity, replacement in _ENTITY_MAP.items():
        text = text.replace(entity, replacement)
    # Remove any remaining numeric entities (&#123; style)
    text = re.sub(r"&#\d+;", " ", text)
    return text


# ── Text normalisation ─────────────────────────────────────────────────────────


def normalize_kb_text_for_semantic(text: str) -> str:
    """Normalise *text* for semantic processing.

    What this does
    --------------
    - Strips HTML tags and decodes common entities.
    - Normalises newline sequences (CRLF / CR → LF).
    - Collapses three-or-more consecutive newlines to a single paragraph break
      (``\\n\\n``).
    - Replaces lone newlines *within* a paragraph with a space.
    - Collapses horizontal whitespace (spaces / tabs) to a single space.
    - Trims leading / trailing whitespace from each paragraph.

    What this does NOT do
    ---------------------
    - Does NOT lowercase: legal entity names, regulation codes (GDPR, RGD, ECDF),
      and accounting terms are case-sensitive.
    - Does NOT remove punctuation: commas, periods, colons, semicolons, and
      parentheses carry meaning in legal / accounting text.

    Returns
    -------
    str — empty string for ``None`` or whitespace-only input.
          Never raises.
    """
    if not text:
        return ""
    try:
        text = _strip_html(text)
        # Normalise newline variants
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse 3+ newlines to paragraph break
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Single newlines within a paragraph → space
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        # Collapse horizontal whitespace
        text = re.sub(r"[ \t]+", " ", text)
        # Trim each paragraph
        paragraphs = [p.strip() for p in text.split("\n\n")]
        paragraphs = [p for p in paragraphs if p]
        return "\n\n".join(paragraphs)
    except Exception:
        return ""


# ── Chunking helpers ───────────────────────────────────────────────────────────

# Sentence boundary: after a sentence-ending punctuation followed by whitespace
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _hard_split(text: str, max_chars: int) -> List[str]:
    """Split *text* into pieces of at most *max_chars*, preferring word boundaries."""
    if not text:
        return []
    chunks: List[str] = []
    while len(text) > max_chars:
        split_at = text.rfind(" ", 0, max_chars)
        if split_at <= 0:
            # No space within max_chars — hard character split
            chunks.append(text[:max_chars])
            text = text[max_chars:]
        else:
            chunks.append(text[:split_at])
            text = text[split_at + 1:]
    if text.strip():
        chunks.append(text)
    return [c.strip() for c in chunks if c.strip()]


def _split_paragraph_by_sentences(para: str, max_chars: int) -> List[str]:
    """Split *para* at sentence boundaries, hard-splitting only when necessary."""
    if len(para) <= max_chars:
        return [para]

    sentences = _SENTENCE_SPLIT_RE.split(para)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            # Very long sentence — flush current, then hard-split
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence, max_chars))
        elif current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [para[:max_chars]]


def chunk_kb_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[str]:
    """Split *text* into overlapping chunks.

    Boundary preference (highest → lowest)
    ---------------------------------------
    1. Paragraph boundaries (``\\n\\n``).
    2. Sentence-ish boundaries (``.`` / ``!`` / ``?`` followed by whitespace).
    3. Word boundaries (last space within *max_chars*).
    4. Hard character split for extremely long unbroken strings.

    Overlap
    -------
    Each chunk (except the first) is prepended with the tail of the previous
    base chunk trimmed to the nearest word boundary.  Chunks therefore may
    slightly exceed *max_chars* — this is intentional; the overlap text is
    supplementary context, not new primary content.

    Parameters
    ----------
    text : str
        Input text, ideally already normalised.
    max_chars : int
        Soft maximum characters per base chunk (before overlap is prepended).
    overlap_chars : int
        How many characters from the end of the previous chunk to prepend to
        the next.  Set to 0 to disable overlap.

    Returns
    -------
    list[str] — empty for empty / whitespace-only input.
                Never raises.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Fast path: text fits in a single chunk
    if len(text) <= max_chars:
        return [text]

    # ── Phase 1: split at paragraph boundaries ────────────────────────────────
    raw_paragraphs = re.split(r"\n\n+", text)
    base_chunks: List[str] = []
    current = ""

    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > max_chars:
            # Flush accumulator first
            if current:
                base_chunks.append(current)
                current = ""
            # Phase 2: sentence-level split within the oversized paragraph
            base_chunks.extend(_split_paragraph_by_sentences(para, max_chars))
        elif current and len(current) + 2 + len(para) > max_chars:
            # Adding this paragraph would exceed the limit → flush
            base_chunks.append(current)
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para

    if current:
        base_chunks.append(current)

    # ── Phase 3: filter empties ────────────────────────────────────────────────
    base_chunks = [c for c in base_chunks if c.strip()]
    if not base_chunks:
        return []

    if len(base_chunks) == 1 or overlap_chars <= 0:
        return base_chunks

    # ── Phase 4: apply overlap ─────────────────────────────────────────────────
    overlapped: List[str] = [base_chunks[0]]

    for i in range(1, len(base_chunks)):
        prev = base_chunks[i - 1]
        tail = prev[-overlap_chars:] if len(prev) >= overlap_chars else prev
        # Trim to the first word boundary so we don't start mid-word
        first_space = tail.find(" ")
        if first_space >= 0:
            tail = tail[first_space + 1:].strip()
        else:
            # No space in tail — skip overlap to avoid a confusing fragment
            tail = ""
        if tail:
            chunk = (tail + " " + base_chunks[i]).strip()
        else:
            chunk = base_chunks[i]
        overlapped.append(chunk)

    return overlapped


# ── Stable ID helpers ──────────────────────────────────────────────────────────


def _sha256_prefix(*parts: str, length: int = 16) -> str:
    """Return the first *length* hex characters of SHA-256(joined parts)."""
    combined = "\x00".join(parts)
    return hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()[:length]


def _stable_entry_id(entry: dict) -> str:
    """Derive a stable string entry_id from a KB entry dict.

    Fallback order
    --------------
    1. ``entry["id"]``  (integer or string primary key)
    2. ``entry["entry_id"]``  (explicit string key)
    3. SHA-256 prefix of ``title + content`` (content-based hash)
    """
    raw_id = entry.get("id")
    if raw_id is not None:
        return str(raw_id)
    raw_eid = entry.get("entry_id")
    if raw_eid is not None:
        return str(raw_eid)
    # Content-based fallback
    title = str(entry.get("title") or "")
    content = str(entry.get("content") or "")
    return _sha256_prefix(title, content)


# ── Public record builder ──────────────────────────────────────────────────────


def build_semantic_kb_records(
    entries: List[dict],
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[dict]:
    """Build stable, semantic-ready records from raw KB entry dicts.

    Each entry is chunked independently.  Each chunk produces one record.

    Parameters
    ----------
    entries : list[dict]
        Raw KB entries.  Each should have at least ``title`` or ``content``.
        Invalid entries (non-dict, or missing both ``title`` and ``content``)
        are silently skipped.
    max_chars : int
        Soft max characters per chunk (before overlap).
    overlap_chars : int
        Overlap window prepended to each chunk after the first.

    Rules
    -----
    - Fully deterministic: same input → identical output.
    - Never raises.
    - Does not mutate input entries.
    - No API calls, no DB reads/writes.

    Returns
    -------
    list[dict]  — may be empty if all entries are invalid.

    Record fields
    -------------
    record_id     : str   — SHA-256 prefix(entry_id, title, chunk_index, chunk)
    entry_id      : str   — stable identifier for the source entry
    chunk_index   : int   — 0-based position within the entry's chunks
    title         : str
    category      : str
    evidence_type : str
    text          : str   — semantic text: "<title>. <chunk>" (or just "<title>"
                            when chunk equals the title, or just "<chunk>" when
                            no title exists)
    source_text   : str   — the raw chunk (no title prefix)
    metadata      : dict  — {title, category, evidence_type, chunk_index,
                             total_chunks, source_fields}
    """
    if not entries:
        return []

    records: List[dict] = []

    for entry in entries:
        # Must be a dict
        if not isinstance(entry, dict):
            continue

        title = str(entry.get("title") or "").strip()
        content = str(entry.get("content") or "").strip()
        category = str(entry.get("category") or "").strip()
        evidence_type = str(entry.get("evidence_type") or "").strip()

        # Skip entries with no useful text at all
        if not title and not content:
            continue

        entry_id = _stable_entry_id(entry)

        # Determine which source fields are present in the original entry
        source_fields = [
            k for k in ("id", "entry_id", "title", "category", "content", "evidence_type")
            if entry.get(k) is not None
        ]

        # Normalise and chunk the content body
        body = normalize_kb_text_for_semantic(content) if content else ""
        if not body:
            # Fall back to title as the body text
            body = title

        chunks = chunk_kb_text(body, max_chars=max_chars, overlap_chars=overlap_chars)

        # Always produce at least one record per valid entry
        if not chunks:
            chunks = [body]

        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks):
            chunk = chunk.strip()

            # Semantic text: prepend title so embedding captures entry identity
            if title:
                text = (f"{title}. {chunk}".strip() if chunk and chunk != title
                        else title)
            else:
                text = chunk

            record_id = _sha256_prefix(
                entry_id,
                title,
                str(idx),
                chunk,
            )

            records.append({
                "record_id": record_id,
                "entry_id": entry_id,
                "chunk_index": idx,
                "title": title,
                "category": category,
                "evidence_type": evidence_type,
                "text": text,
                "source_text": chunk,
                "metadata": {
                    "title": title,
                    "category": category,
                    "evidence_type": evidence_type,
                    "chunk_index": idx,
                    "total_chunks": total_chunks,
                    "source_fields": source_fields,
                },
            })

    return records
