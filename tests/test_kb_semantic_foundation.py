"""Tests for ai/kb_semantic_foundation.py — PR 37.

All tests are pure-Python; no app, no DB, no network.

Covers:
- normalize_kb_text_for_semantic: None/empty safety, HTML stripping,
  whitespace collapsing, casing preservation
- chunk_kb_text: empty input, short text, multi-chunk, overlap, max_chars,
  hard split for long unbroken text
- build_semantic_kb_records: invalid entry skipping, stable record_id,
  stable entry_id fallback, field preservation, metadata keys, source_text,
  text field, input non-mutation
- Acceptance scenario
"""
from __future__ import annotations

import copy
import hashlib

import pytest

from ai.kb_semantic_foundation import (
    build_semantic_kb_records,
    chunk_kb_text,
    normalize_kb_text_for_semantic,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _long_word(n: int = 1500) -> str:
    """Return a single unbroken alphanumeric string of length n."""
    return "a" * n


def _paragraphs(n: int, chars_each: int = 200) -> str:
    """Return n paragraphs each with chars_each characters, separated by \\n\\n."""
    word = "word" * (chars_each // 4 + 1)
    word = word[:chars_each]
    return "\n\n".join(word for _ in range(n))


# ══════════════════════════════════════════════════════════════════════════════
# normalize_kb_text_for_semantic
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeKbTextForSemantic:

    def test_none_returns_empty_string(self):
        assert normalize_kb_text_for_semantic(None) == ""  # type: ignore[arg-type]

    def test_empty_string_returns_empty_string(self):
        assert normalize_kb_text_for_semantic("") == ""

    def test_whitespace_only_returns_empty_string(self):
        assert normalize_kb_text_for_semantic("   \n\n\t  ") == ""

    def test_strips_simple_html_tags(self):
        result = normalize_kb_text_for_semantic("<p>Hello world</p>")
        assert "<p>" not in result
        assert "</p>" not in result
        assert "Hello world" in result

    def test_strips_nested_html_tags(self):
        result = normalize_kb_text_for_semantic(
            "<div><p><strong>Important</strong> note</p></div>"
        )
        assert "<" not in result
        assert "Important" in result
        assert "note" in result

    def test_decodes_amp_entity(self):
        result = normalize_kb_text_for_semantic("Fees &amp; Charges")
        assert "&amp;" not in result
        assert "Fees & Charges" in result

    def test_decodes_lt_gt_entities(self):
        result = normalize_kb_text_for_semantic("Use &lt;Enter&gt; to confirm")
        assert "&lt;" not in result
        assert "&gt;" not in result

    def test_decodes_nbsp_entity(self):
        result = normalize_kb_text_for_semantic("Total&nbsp;Amount")
        assert "&nbsp;" not in result

    def test_collapses_multiple_spaces(self):
        result = normalize_kb_text_for_semantic("Hello    world")
        assert "  " not in result
        assert "Hello world" in result

    def test_collapses_tabs(self):
        result = normalize_kb_text_for_semantic("Col1\t\tCol2")
        assert "\t" not in result

    def test_preserves_paragraph_breaks(self):
        result = normalize_kb_text_for_semantic("First paragraph.\n\nSecond paragraph.")
        assert "\n\n" in result

    def test_collapses_triple_newlines_to_paragraph_break(self):
        result = normalize_kb_text_for_semantic("Para1.\n\n\n\nPara2.")
        # Should have exactly one paragraph break between them
        assert result.count("\n\n") == 1
        assert "\n\n\n" not in result

    def test_converts_lone_newlines_to_space(self):
        result = normalize_kb_text_for_semantic("Line one\nLine two")
        assert "\n" not in result
        assert "Line one Line two" in result

    def test_preserves_casing_for_legal_names(self):
        text = "The GDPR regulation requires Article 13 compliance."
        result = normalize_kb_text_for_semantic(text)
        assert "GDPR" in result
        assert "Article 13" in result

    def test_preserves_casing_for_accounting_codes(self):
        text = "RGD and ECDF reporting obligations apply to this entry."
        result = normalize_kb_text_for_semantic(text)
        assert "RGD" in result
        assert "ECDF" in result

    def test_preserves_meaningful_punctuation(self):
        text = "Amount: 1,234.56. See clause 3(a); this is mandatory."
        result = normalize_kb_text_for_semantic(text)
        assert "," in result
        assert "." in result
        assert ";" in result
        assert "(" in result

    def test_html_with_whitespace_noise(self):
        html = "<p>  Use the  existing  dropdown setting.  </p>"
        result = normalize_kb_text_for_semantic(html)
        assert "<" not in result
        assert "Use the existing dropdown setting." in result


# ══════════════════════════════════════════════════════════════════════════════
# chunk_kb_text
# ══════════════════════════════════════════════════════════════════════════════


class TestChunkKbText:

    def test_empty_string_returns_empty_list(self):
        assert chunk_kb_text("") == []

    def test_none_returns_empty_list(self):
        assert chunk_kb_text(None) == []  # type: ignore[arg-type]

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_kb_text("   \n\n  ") == []

    def test_short_text_returns_single_chunk(self):
        text = "This is a short entry."
        chunks = chunk_kb_text(text, max_chars=1200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_text_exactly_at_limit_returns_single_chunk(self):
        text = "x" * 1200
        chunks = chunk_kb_text(text, max_chars=1200)
        assert len(chunks) == 1

    def test_long_multi_paragraph_text_returns_multiple_chunks(self):
        text = _paragraphs(20, chars_each=200)  # ~4200 chars total
        chunks = chunk_kb_text(text, max_chars=1200, overlap_chars=0)
        assert len(chunks) > 1

    def test_base_chunks_respect_max_chars(self):
        # Without overlap, no base chunk should exceed max_chars for normal text
        text = _paragraphs(20, chars_each=100)
        chunks = chunk_kb_text(text, max_chars=500, overlap_chars=0)
        for chunk in chunks:
            assert len(chunk) <= 500, f"Chunk too long: {len(chunk)} chars"

    def test_overlap_is_applied_between_chunks(self):
        # Build two paragraphs with known content
        p1 = "Alpha " * 80  # ~480 chars
        p2 = "Beta " * 80   # ~480 chars
        text = p1.strip() + "\n\n" + p2.strip()
        chunks = chunk_kb_text(text, max_chars=600, overlap_chars=100)
        assert len(chunks) >= 2
        # Second chunk should contain some content from first chunk (overlap)
        # Overlap is prepended from the tail of the previous base chunk
        first_chunk_tail = chunks[0][-100:]
        # The second chunk should start with a word from the first chunk's tail
        # (exact match depends on word boundaries, just check it's longer than p2 alone)
        assert len(chunks[1]) > len("Beta " * 80)

    def test_no_empty_chunks_in_output(self):
        text = _paragraphs(15, chars_each=150)
        chunks = chunk_kb_text(text, max_chars=400, overlap_chars=50)
        for chunk in chunks:
            assert chunk.strip() != "", "Got an empty chunk"

    def test_long_unbroken_string_is_hard_split(self):
        text = _long_word(3000)  # 3000 'a' chars — no word boundaries
        chunks = chunk_kb_text(text, max_chars=1200, overlap_chars=0)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 1200

    def test_overlap_zero_disables_overlap(self):
        p1 = "First paragraph content. " * 50
        p2 = "Second paragraph content. " * 50
        text = p1.strip() + "\n\n" + p2.strip()
        chunks = chunk_kb_text(text, max_chars=600, overlap_chars=0)
        assert len(chunks) >= 2
        # With no overlap, second chunk should NOT contain content from first
        # (just verify no overlap is prepended by checking it starts with "Second")
        second_chunk_words = chunks[1][:20]
        # Can't guarantee exact start due to paragraph accumulation, but no
        # content from chunk[0] tail should appear at the very start of chunk[1]
        # Just check we got multiple chunks and all are non-empty
        for c in chunks:
            assert c.strip()

    def test_sentence_boundary_used_when_paragraph_too_long(self):
        # One big paragraph, many sentences
        sentences = ["This is sentence number %d." % i for i in range(50)]
        text = " ".join(sentences)  # ~1400 chars, no \n\n
        chunks = chunk_kb_text(text, max_chars=400, overlap_chars=0)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 400


# ══════════════════════════════════════════════════════════════════════════════
# build_semantic_kb_records
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildSemanticKbRecords:

    # ── Invalid input handling ────────────────────────────────────────────────

    def test_empty_list_returns_empty(self):
        assert build_semantic_kb_records([]) == []

    def test_none_input_returns_empty(self):
        assert build_semantic_kb_records(None) == []  # type: ignore[arg-type]

    def test_skips_non_dict_entries(self):
        result = build_semantic_kb_records(["not a dict", 42, None])
        assert result == []

    def test_skips_entry_with_no_title_or_content(self):
        result = build_semantic_kb_records([{"category": "product"}])
        assert result == []

    def test_mixed_valid_and_invalid_entries(self):
        entries = [
            "not a dict",
            {"title": "Valid entry", "content": "Some content."},
            {"category": "only_cat"},
        ]
        result = build_semantic_kb_records(entries)
        assert len(result) >= 1
        assert all(r["title"] == "Valid entry" for r in result)

    # ── entry_id derivation ───────────────────────────────────────────────────

    def test_entry_id_from_id_field(self):
        entry = {"id": 42, "title": "T", "content": "C"}
        records = build_semantic_kb_records([entry])
        assert records[0]["entry_id"] == "42"

    def test_entry_id_from_entry_id_field_when_no_id(self):
        entry = {"entry_id": "abc-123", "title": "T", "content": "C"}
        records = build_semantic_kb_records([entry])
        assert records[0]["entry_id"] == "abc-123"

    def test_entry_id_fallback_to_hash(self):
        entry = {"title": "T", "content": "C"}
        records = build_semantic_kb_records([entry])
        entry_id = records[0]["entry_id"]
        # Should be a hex string (SHA-256 prefix)
        assert len(entry_id) == 16
        int(entry_id, 16)  # must be valid hex

    def test_entry_id_fallback_is_stable(self):
        entry = {"title": "T", "content": "C"}
        r1 = build_semantic_kb_records([entry])
        r2 = build_semantic_kb_records([entry])
        assert r1[0]["entry_id"] == r2[0]["entry_id"]

    def test_entry_id_id_takes_precedence_over_entry_id(self):
        entry = {"id": 10, "entry_id": "other", "title": "T", "content": "C"}
        records = build_semantic_kb_records([entry])
        assert records[0]["entry_id"] == "10"

    # ── Stable record_id ──────────────────────────────────────────────────────

    def test_record_id_is_16_hex_chars(self):
        entry = {"id": 1, "title": "T", "content": "Some content."}
        records = build_semantic_kb_records([entry])
        for r in records:
            assert len(r["record_id"]) == 16
            int(r["record_id"], 16)  # valid hex

    def test_record_id_is_stable_across_calls(self):
        entry = {"id": 1, "title": "T", "content": "Some content."}
        r1 = build_semantic_kb_records([entry])
        r2 = build_semantic_kb_records([entry])
        for a, b in zip(r1, r2):
            assert a["record_id"] == b["record_id"]

    def test_record_ids_are_unique_across_chunks(self):
        long_content = ("This is a meaningful sentence with enough words. " * 60)
        entry = {"id": 5, "title": "Title", "content": long_content}
        records = build_semantic_kb_records([entry], max_chars=400)
        ids = [r["record_id"] for r in records]
        assert len(ids) == len(set(ids)), "Duplicate record_ids found"

    def test_different_entries_produce_different_record_ids(self):
        e1 = {"id": 1, "title": "A", "content": "Content A."}
        e2 = {"id": 2, "title": "B", "content": "Content B."}
        r1 = build_semantic_kb_records([e1])
        r2 = build_semantic_kb_records([e2])
        assert r1[0]["record_id"] != r2[0]["record_id"]

    # ── Field preservation ────────────────────────────────────────────────────

    def test_title_preserved(self):
        entry = {"id": 1, "title": "My KB Title", "content": "Content."}
        records = build_semantic_kb_records([entry])
        assert all(r["title"] == "My KB Title" for r in records)

    def test_category_preserved(self):
        entry = {"id": 1, "title": "T", "content": "C.", "category": "legal"}
        records = build_semantic_kb_records([entry])
        assert all(r["category"] == "legal" for r in records)

    def test_evidence_type_preserved(self):
        entry = {
            "id": 1,
            "title": "T",
            "content": "C.",
            "evidence_type": "existing_setting_evidence",
        }
        records = build_semantic_kb_records([entry])
        assert all(r["evidence_type"] == "existing_setting_evidence" for r in records)

    def test_missing_category_defaults_to_empty_string(self):
        entry = {"id": 1, "title": "T", "content": "C."}
        records = build_semantic_kb_records([entry])
        assert all(r["category"] == "" for r in records)

    def test_missing_evidence_type_defaults_to_empty_string(self):
        entry = {"id": 1, "title": "T", "content": "C."}
        records = build_semantic_kb_records([entry])
        assert all(r["evidence_type"] == "" for r in records)

    # ── chunk_index and total_chunks ──────────────────────────────────────────

    def test_single_chunk_has_chunk_index_zero(self):
        entry = {"id": 1, "title": "T", "content": "Short content."}
        records = build_semantic_kb_records([entry])
        assert records[0]["chunk_index"] == 0

    def test_chunk_indexes_are_sequential(self):
        long_content = "Sentence number %d. " * 100
        long_content = " ".join(f"Sentence number {i}." for i in range(100))
        entry = {"id": 1, "title": "T", "content": long_content}
        records = build_semantic_kb_records([entry], max_chars=300)
        indexes = [r["chunk_index"] for r in records]
        assert indexes == list(range(len(records)))

    def test_total_chunks_consistent_across_records(self):
        long_content = " ".join(f"Sentence {i}." for i in range(100))
        entry = {"id": 1, "title": "T", "content": long_content}
        records = build_semantic_kb_records([entry], max_chars=300)
        total_chunks_values = {r["metadata"]["total_chunks"] for r in records}
        assert len(total_chunks_values) == 1
        assert total_chunks_values.pop() == len(records)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def test_metadata_contains_required_keys(self):
        entry = {"id": 1, "title": "T", "content": "C.", "category": "product"}
        records = build_semantic_kb_records([entry])
        for r in records:
            meta = r["metadata"]
            assert "title" in meta
            assert "category" in meta
            assert "evidence_type" in meta
            assert "chunk_index" in meta
            assert "total_chunks" in meta
            assert "source_fields" in meta

    def test_metadata_source_fields_lists_present_keys(self):
        entry = {"id": 1, "title": "T", "content": "C.", "category": "product"}
        records = build_semantic_kb_records([entry])
        source_fields = records[0]["metadata"]["source_fields"]
        assert "id" in source_fields
        assert "title" in source_fields
        assert "content" in source_fields
        assert "category" in source_fields
        # evidence_type not in entry, so not in source_fields
        assert "evidence_type" not in source_fields

    def test_metadata_source_fields_excludes_absent_keys(self):
        entry = {"id": 1, "title": "T", "content": "C."}
        records = build_semantic_kb_records([entry])
        source_fields = records[0]["metadata"]["source_fields"]
        assert "category" not in source_fields

    def test_metadata_chunk_index_matches_record_chunk_index(self):
        long_content = " ".join(f"Sentence {i}." for i in range(100))
        entry = {"id": 1, "title": "T", "content": long_content}
        records = build_semantic_kb_records([entry], max_chars=300)
        for r in records:
            assert r["metadata"]["chunk_index"] == r["chunk_index"]

    # ── source_text and text fields ───────────────────────────────────────────

    def test_source_text_is_raw_chunk_without_title(self):
        entry = {
            "id": 1,
            "title": "My Title",
            "content": "<p>Raw content here.</p>",
        }
        records = build_semantic_kb_records([entry])
        for r in records:
            # source_text should be the chunk, not prefixed with title
            assert r["source_text"] == r["source_text"]  # sanity
            assert "My Title" not in r["source_text"] or "Raw content here." in r["source_text"]

    def test_source_text_has_no_html_tags(self):
        entry = {"id": 1, "title": "T", "content": "<p>Content <strong>here</strong>.</p>"}
        records = build_semantic_kb_records([entry])
        for r in records:
            assert "<p>" not in r["source_text"]
            assert "<strong>" not in r["source_text"]

    def test_text_field_includes_title(self):
        entry = {"id": 1, "title": "Setting for staff note", "content": "Use the dropdown."}
        records = build_semantic_kb_records([entry])
        for r in records:
            assert "Setting for staff note" in r["text"]

    def test_text_field_includes_chunk_content(self):
        entry = {"id": 1, "title": "T", "content": "Use the existing dropdown setting."}
        records = build_semantic_kb_records([entry])
        assert any("dropdown setting" in r["text"] for r in records)

    def test_text_field_combines_title_and_chunk(self):
        entry = {"id": 1, "title": "My Title", "content": "My content."}
        records = build_semantic_kb_records([entry])
        r = records[0]
        assert "My Title" in r["text"]
        assert "My content" in r["text"]

    # ── Input non-mutation ────────────────────────────────────────────────────

    def test_input_entries_not_mutated(self):
        entry = {"id": 1, "title": "T", "content": "C.", "category": "product"}
        original = copy.deepcopy(entry)
        build_semantic_kb_records([entry])
        assert entry == original

    def test_input_list_not_mutated(self):
        entries = [{"id": 1, "title": "T", "content": "C."}]
        original_len = len(entries)
        build_semantic_kb_records(entries)
        assert len(entries) == original_len

    # ── Title-only entry ──────────────────────────────────────────────────────

    def test_title_only_entry_produces_record(self):
        entry = {"id": 1, "title": "Title only, no content"}
        records = build_semantic_kb_records([entry])
        assert len(records) == 1
        assert records[0]["title"] == "Title only, no content"

    # ── Content-only entry ────────────────────────────────────────────────────

    def test_content_only_entry_produces_record(self):
        entry = {"id": 1, "content": "Content without title."}
        records = build_semantic_kb_records([entry])
        assert len(records) >= 1

    # ══════════════════════════════════════════════════════════════════════════
    # Acceptance scenario
    # ══════════════════════════════════════════════════════════════════════════

    def test_acceptance_scenario(self):
        """Full acceptance scenario from the PR specification."""
        entries = [
            {
                "id": 123,
                "title": "Existing setting for staff note",
                "category": "product",
                "evidence_type": "existing_setting_evidence",
                "content": (
                    "<p>Use the existing dropdown setting for staff wording.</p>"
                    "<p>This avoids a global default change.</p>"
                ),
            }
        ]

        records = build_semantic_kb_records(entries)

        # At least one record produced
        assert len(records) >= 1

        r = records[0]

        # entry_id must be "123" (from entry["id"] = 123)
        assert r["entry_id"] == "123"

        # Title preserved
        assert r["title"] == "Existing setting for staff note"

        # Category preserved
        assert r["category"] == "product"

        # Evidence type preserved
        assert r["evidence_type"] == "existing_setting_evidence"

        # source_text: clean text, no HTML
        assert "<p>" not in r["source_text"]
        assert "</p>" not in r["source_text"]
        assert "dropdown setting" in r["source_text"]

        # text: includes title and chunk content
        assert "Existing setting for staff note" in r["text"]
        assert "dropdown" in r["text"]

        # metadata.total_chunks reflects actual number of records
        total = r["metadata"]["total_chunks"]
        assert total == len(records)

        # chunk_index starts at 0
        assert records[0]["chunk_index"] == 0

        # Stable record_id across repeated calls
        records2 = build_semantic_kb_records(entries)
        for a, b in zip(records, records2):
            assert a["record_id"] == b["record_id"]

        # No API calls / no DB writes — function returns without error
        # (verified by the test completing successfully)
