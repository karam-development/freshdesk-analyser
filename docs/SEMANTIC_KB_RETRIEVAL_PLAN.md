# Semantic KB Retrieval Plan

This document describes the phased plan to evolve the Knowledge Base retrieval system
from deterministic keyword matching to hybrid semantic / vector retrieval — without
breaking existing behaviour at any stage.

> **Status (PR 38):** Semantic RAG is implemented and available behind a feature flag.
> It is **OFF by default**.  The keyword retrieval path is unchanged.
> Enable only after configuring the embedding provider and API key in Settings.

---

## Current state — deterministic keyword retrieval

**File:** `ai/kb_retrieval.py`

The current retrieval system uses a scoring model based on keyword matching:

- Keywords are extracted from the ticket subject, summary, template name, and
  workflow name.
- Each KB entry is scored by matching those keywords against the entry's title,
  category, and content (with different point weights for each field).
- Evidence-type context boosts and legal-context penalties are applied.
- Only entries reaching a minimum score (`min_score = 3`) are returned.
- Results are ordered by score descending, then entry ID ascending.
- The top-N entries (default 8) are returned.

**Properties:**
- Fully deterministic: same ticket inputs → same ranked list every call.
- No external API calls; no network I/O.
- No LLM calls.
- Pure SQLite reads + Python scoring.

This retrieval behaviour is stable and will **not** be changed by PR 37.

---

## PR 37 — Chunking + metadata foundation (this PR)

**File added:** `ai/kb_semantic_foundation.py`

**Goal:** Lay the groundwork for future semantic indexing without changing
production retrieval.

What PR 37 adds:

1. **`normalize_kb_text_for_semantic(text)`** — strip HTML, collapse whitespace,
   preserve casing and punctuation.  Casing is preserved because legal entity names
   (GDPR, RGD, ECDF, etc.) and accounting terms are case-sensitive.

2. **`chunk_kb_text(text, max_chars=1200, overlap_chars=150)`** — split text into
   overlapping chunks, preferring paragraph then sentence then word boundaries.
   Hard-split only as a last resort.

3. **`build_semantic_kb_records(entries, ...)`** — produce stable, deterministic
   chunk records with full provenance metadata.  Record IDs are SHA-256 hashes
   of (entry_id, title, chunk_index, chunk_text) so they are reproducible and
   content-addressable.

4. **`prepare_kb_entries_for_semantic(entries)`** (in `ai/kb_retrieval.py`) — thin
   bridge helper; does not change `retrieve_relevant_kb_entries`.

**What PR 37 does NOT do:**
- No embedding API calls.
- No vector database.
- No changes to current retrieval ranking.
- No DB schema changes.
- No LLM calls.
- No Freshdesk / OpenAI / Anthropic calls.

---

## PR 38 — Semantic RAG behind feature flag ✅ DONE

**Files added/changed:**
- `ai/kb_embeddings.py` — embedding cache helpers (OpenAI provider)
- `ai/kb_semantic_search.py` — cosine similarity, semantic search, evidence formatting
- `ai/kb_retrieval.py` — `retrieve_hybrid_kb_entries` (keyword + semantic merge)
- `app.py` — `kb_embedding_cache` DB table, `_augment_kb_with_semantic` helper, wired at 3 retrieval points
- `templates/ticket.html` — source badge (semantic / hybrid) in KB Evidence card

**Feature flag settings** (all default to off/safe values):

| Setting | Default | Description |
|---------|---------|-------------|
| `semantic_rag_enabled` | `false` | Master switch. Must be `true` to activate |
| `semantic_rag_provider` | same as `llm_provider` | Embedding provider |
| `semantic_embedding_model` | `text-embedding-3-small` | Embedding model |
| `semantic_rag_top_k` | `5` | Max semantic results per query |
| `semantic_rag_min_score` | `0.65` | Minimum cosine similarity (0–1) |

**When `semantic_rag_enabled=false` (default):**
- `_augment_kb_with_semantic` returns keyword results immediately.
- No embedding API calls are made.
- No DB reads/writes to `kb_embedding_cache`.
- Behaviour is identical to pre-PR-38.

**When `semantic_rag_enabled=true`:**
- KB entries are chunked via `build_semantic_kb_records`.
- Embeddings are generated on first use and cached in `kb_embedding_cache`.
- Ticket query is embedded and scored by cosine similarity.
- Semantic matches above `min_score` are merged with keyword results.
- Entries in both sets get `source="hybrid"`; semantic-only get `source="semantic"`.
- Source badge shown in KB Evidence card.
- Any failure falls back to keyword-only silently.

**Cost notice:** Enabling semantic RAG will incur embedding API calls.
The `text-embedding-3-small` model is billed per token by OpenAI.
Embeddings are cached to minimise repeat costs.

## PR 38 (original plan) — Embedding generation and cache design — SUPERSEDED

**Goal:** Design and implement embedding generation for the chunk records produced
by PR 37.

Planned scope:
- Add an optional `generate_kb_embeddings(records)` helper.
- Design a caching strategy so embeddings are not recomputed on every request.
- Choose a storage format for embedding cache (e.g. a separate SQLite table or
  flat file).
- Keep embedding generation entirely offline / on-demand — never called during
  a live ticket request unless explicitly opted in.
- Define the vector dimensionality and model choice (deferred to PR 38).

**What PR 38 will NOT do:**
- Will not replace deterministic retrieval.
- Will not add auto-triggering of embedding generation.

---

## PR 39 — Semantic retrieval experimental mode (future)

**Goal:** Implement a semantic similarity search path that runs alongside
(not instead of) the existing keyword retrieval, behind an explicit flag.

Planned scope:
- Add `retrieve_relevant_kb_entries_semantic(db, ticket, ...)` as a new function.
- Use cosine similarity against cached embeddings.
- Gate behind an `ENABLE_SEMANTIC_RETRIEVAL=true` environment variable.
- Log which path was used for each retrieval call.
- Provide side-by-side comparison mode (keyword results vs semantic results).

**What PR 39 will NOT do:**
- Will not remove or modify `retrieve_relevant_kb_entries`.
- Will not silently swap the retrieval path.
- Will not write to Freshdesk.

---

## PR 40 — Hybrid keyword + semantic retrieval with feature flag (future)

**Goal:** Merge the two retrieval paths into a configurable hybrid that combines
keyword scores and semantic similarity scores.

Planned scope:
- Implement a `retrieve_kb_hybrid(db, ticket, ..., mode="keyword")` function.
- `mode` options: `"keyword"` (default, current behaviour), `"semantic"`,
  `"hybrid"` (weighted combination).
- Expose the mode setting via the Settings page.
- Default to `"keyword"` so existing behaviour is unchanged unless the operator
  explicitly enables a different mode.
- Provide an A/B comparison view in the ticket detail UI (experimental panel,
  hidden unless feature flag is on).

**What PR 40 will NOT do:**
- Will not make semantic or hybrid mode the default.
- Will not auto-switch based on KB size or ticket content.

---

## Safety rules

These rules apply across all PRs in this plan and cannot be relaxed without
an explicit, reviewed decision:

1. **No external calls during chunking or normalisation.**
   `kb_semantic_foundation.py` is a pure-Python module.  It must never import
   or call any external service, LLM, or Freshdesk API.

2. **No automatic replacement of deterministic retrieval.**
   The keyword-based path in `ai/kb_retrieval.py` must remain the default at all
   times.  Any semantic or hybrid path must be explicitly opted in by the operator.

3. **Source evidence must remain visible.**
   Every semantic record preserves `entry_id`, `source_text`, `title`, and full
   `metadata`.  The UI must always be able to trace a result back to its source
   KB entry.

4. **Legal and accounting evidence requires conservative handling.**
   - Do not lowercase legal / accounting text (entity names and regulation codes
     are case-sensitive).
   - Do not discard punctuation (dates, amounts, and legal references depend on it).
   - Legal entries must never be surfaced for non-legal tickets without the explicit
     evidence-type penalty that exists in the current keyword scorer.

5. **No DB schema changes without a migration plan.**
   If embedding storage requires a new table, that change must be accompanied by a
   migration script and a rollback path.

6. **No auto-send.**
   None of the retrieval changes affect the draft generation or sending pipeline.
   AI drafts remain suggestions only; human review is required before any reply
   is sent via Freshdesk.

---

*See also: [`docs/LIVE_DEMO_SMOKE_TEST.md`](LIVE_DEMO_SMOKE_TEST.md) ·
[`docs/PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md)*
