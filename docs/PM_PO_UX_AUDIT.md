# PM/PO Ticket Review UX Audit

**Date:** 2026-05-10
**Scope:** `templates/ticket.html` — all visible cards, buttons, and sections
**Goal:** Identify what is useful for daily PM/PO use vs. what is diagnostic/debug-only

---

## Current State: 17 top-level sections

A PM/PO opening a ticket currently sees 17 sections before reaching the draft editor. Most are diagnostic. This creates cognitive overload and no clear "what do I do next?" signal.

---

## Full UX Audit Table

| UI element | Current location | User value | Problem | Keep visible? | Move to Advanced/Diagnostics? | Change needed |
|---|---|---|---|---|---|---|
| Ticket header (subject, ticket ID, Freshdesk link) | Top | High | — | Yes | No | — |
| Jira dropdown | Header toolbar | Medium | Rarely used during daily review | Yes | No | Keep — low noise |
| Export dropdown | Header toolbar | Low | Debug / docs only | Maybe | Yes | Move to Advanced menu |
| Prepare Analysis dropdown | Header toolbar | High | Used to trigger analysis | Yes | No | Rename to "Run Analysis" |
| Download Document dropdown | Header toolbar | Low | Occasional | Maybe | No | Keep as-is |
| **Ticket Info card** | Top of main grid | Medium | Good reference, not primary | Secondary | No | Move below PM/PO Summary |
| **AI Analysis card** | Top of main grid | Medium | Classification + RICE visible | Secondary | No | Move below PM/PO Summary |
| **PM Decision card** | Mid-page | High | Core product signal — too verbose | Yes | Move detail to Evidence | Show in PM/PO Summary; collapse full card |
| **Support Explanation Guidance card** | Mid-page | Low daily | Only relevant for guidance cases | No | Yes (Evidence & Diagnostics) | Collapse by default |
| **Safe to Send Review card** | Mid-page | High | Critical safety signal | Summary only visible | Partial | Show status in PM/PO Summary; full detail collapsed |
| **PM Guard Review card** | Mid-page | Low daily | Debug / regeneration trigger | No | Yes (Evidence & Diagnostics) | Collapse; keep Regenerate button accessible |
| **Existing Solution Review card** | Mid-page | Medium | Useful if solution found | No | Yes (Evidence & Diagnostics) | Collapse by default |
| **KB Evidence Quality card** | Mid-page | Low | Diagnostic | No | Yes | Collapse |
| **Relevant KB Evidence card** | Mid-page | Low daily | Diagnostic | No | Yes | Collapse |
| **KB Evidence Snapshots by Flow card** | Mid-page | Very low | Audit/debug | No | Yes | Collapse |
| **KB Snapshot Diff Summary card** | Mid-page | Very low | Audit/debug | No | Yes | Collapse |
| **Structured PM Lessons Used card** | Mid-page | Low daily | Debug / learning loop audit | No | Yes | Collapse |
| **RICE Prioritization section** | Mid-page | Medium | Useful for feature_request/bug | Secondary | Yes (Evidence) | Collapse unless classification = feature_request |
| **PO Decision panel** | Late-page | Critical | Too far down the page | Yes | No | Promote to top-2 position |
| **Draft Response section** | Late-page | Critical | Core action area | Yes | No | Keep prominent; clean button labels |
| Generate Decline Response button | Draft section | High | Clear | Yes | No | Rename to "Generate Decline Response (FR + EN)" |
| Regenerate Decline Response button | Draft section | Medium | Duplicate feel | Yes | No | Add helper: "Overwrites existing response" |
| Generate Draft Responses button | Draft section | High | Clear | Yes | No | Rename to "Generate Draft (FR + EN)" |
| Regenerate Drafts button | Draft section | Medium | Duplicate feel | Yes | No | Rename to "Regenerate Draft with PM Constraints" |
| "Regenerate with PM constraints" (PM Guard section) | PM Guard card | Medium | Overlaps with Draft section | Yes | Partial | Keep button; add note explaining difference |
| Copy clean draft button | Draft editor toolbar | High | Not obvious | Yes | No | Rename: "Copy Clean Draft (no markers)" |
| **Copy & Open in Freshdesk section** | Below draft | High | Core action area | Yes | No | Rename to "Draft Actions"; add no-auto-send note |
| Open in Freshdesk with Note button | Copy section | High | Slightly confusing label | Yes | No | Add tooltip: "Copies draft and opens Freshdesk" |
| Copy & Open button | Copy section | Medium | Overlaps with above | Yes | No | Keep; clarify it's clipboard + browser open |
| Copy Only button | Copy section | Medium | Clear | Yes | No | — |
| **AI Assistant section** | Bottom | High | Generic name + vague placeholder | Yes | No | Rename to "Ask about this ticket"; add quick prompts |
| AI chat input placeholder | AI section | Low | "Ask the AI to adjust…" is too vague | Yes | No | Better placeholder + quick prompt chips |

---

## Priority Problems

### 1. No immediate "what do I do" signal
The PM/PO must scroll through 8–10 cards before reaching the PO Decision and Draft sections. First screen should answer: classification, PM decision, next action, safe-to-send status.

### 2. Hardcoded misleading wording
- "No development action is expected." — hardcoded in Support Explanation Guidance card, not conditional on actual PM decision.
- "This ticket is a support/guidance case." — hardcoded, not conditional.
- "The PM/PO must approve…" guidance text is always shown even after approval.

### 3. Diagnostic cards dominating the primary view
7 cards (PM Guard, KB Evidence, KB Snapshots, KB Diff, PM Lessons, Existing Solution, KB Quality) are diagnostic and should be collapsed.

### 4. Button confusion
- "Regenerate Drafts" vs "Regenerate with PM constraints" are two different actions but look similar.
- "Open in Freshdesk with Note" vs "Copy & Open" do almost the same thing.
- No "nothing sends automatically" note anywhere near the copy buttons.

### 5. AI assistant feels generic
- Name: "AI Assistant" — too generic.
- Placeholder: "Ask the AI to adjust, explain, or reword…" — doesn't ground the user.
- No quick-prompt examples for the most common PM/PO questions.

---

## Proposed New Structure

### Always visible (primary view):
1. **PM/PO Review Summary** ← NEW (classification, decision, dev needed, existing solution, safe-to-send status, next action)
2. **PO Decision** (promoted to top-2)
3. **Draft Response** (editor + generate buttons)
4. **Draft Actions** (renamed Copy section, with no-auto-send note)
5. **Ask about this ticket** (renamed AI assistant + quick prompts)
6. **Ticket Info** + **AI Analysis** (reference cards)

### Collapsed by default — Evidence & Diagnostics:
- PM Decision (full)
- Support Explanation Guidance
- Safe to Send Review (detailed)
- PM Guard Review
- Existing Solution Review
- KB Evidence Quality
- Relevant KB Evidence
- KB Evidence Snapshots by Flow
- KB Snapshot Diff Summary
- Structured PM Lessons Used

### Collapsed by default — Advanced / Debug:
- RICE Prioritization

---

## Deferred Items

- RICE section could be shown inline for feature_request/bug tickets only (conditional). Deferred.
- PM Guard regeneration button could be moved to Draft Actions area. Deferred — keeps working in current location.
- Copy section checklist (section selection) is JavaScript-heavy; label changes only in this PR.
- Freshdesk webhook / auto-open behaviour: label changes only, no logic changes.

---

## Fix Status in This PR

| Problem | Fix | Status |
|---|---|---|
| No PM/PO summary | Add PM/PO Review Summary card | Done |
| PO Decision buried | Promote to top-2 in primary view | Done |
| Diagnostic overload | Wrap in collapsible `<details>` sections | Done |
| Hardcoded misleading wording | Made conditional on PMDecision values | Done |
| Button label confusion | Clearer labels + helper text | Done |
| No-auto-send missing | Added note to Draft Actions section | Done |
| Generic AI assistant | Renamed + quick prompts added | Done |
| Agent status dishonesty | Updated catalog status values | Done |
