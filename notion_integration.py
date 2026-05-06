"""Notion integration: export ticket analyses as rich Notion pages.

Uses the Notion API v1 with a simple Integration Token (no OAuth needed).
Only requires the `requests` library which is already installed.

Setup (takes ~2 minutes):
  1. Go to https://www.notion.so/my-integrations → New integration
  2. Give it a name (e.g. "Freshdesk Analyzer"), select your workspace
  3. Copy the "Internal Integration Secret" token
  4. In Notion, open the page where you want analyses created
  5. Click ••• → Connections → Connect → select your integration
  6. Copy the page ID from the URL (the 32-char hex after the page title)
  7. Paste both in Settings
"""

import logging
import re
import requests

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── Connection test ─────────────────────────────────────────────────────────

def test_notion_connection(token: str, page_id: str = "") -> dict:
    """Validate token and optionally check page access.
    Returns {"ok": True/False, "workspace": ..., "page_title": ..., "error": ...}
    """
    try:
        # Test token by fetching bot info
        resp = requests.get(f"{NOTION_API}/users/me", headers=_headers(token), timeout=10)
        if resp.status_code == 401:
            return {"ok": False, "workspace": "", "page_title": "", "error": "Invalid token. Check your Integration Secret."}
        resp.raise_for_status()
        bot = resp.json()
        workspace = bot.get("name", "Unknown")

        result = {"ok": True, "workspace": workspace, "page_title": "", "error": ""}

        if page_id:
            pid = _clean_page_id(page_id)
            try:
                pr = requests.get(f"{NOTION_API}/pages/{pid}", headers=_headers(token), timeout=10)
                if pr.status_code == 404:
                    result["ok"] = False
                    result["error"] = "Page not found. Make sure you connected the integration to this page (••• → Connections)."
                elif pr.status_code == 400:
                    result["ok"] = False
                    result["error"] = "Invalid page ID format."
                else:
                    pr.raise_for_status()
                    page = pr.json()
                    # Extract title
                    props = page.get("properties", {})
                    for prop in props.values():
                        if prop.get("type") == "title":
                            titles = prop.get("title", [])
                            if titles:
                                result["page_title"] = titles[0].get("plain_text", "")
                            break
                    if not result["page_title"]:
                        result["page_title"] = "Connected"
            except requests.RequestException as e:
                result["ok"] = False
                result["error"] = f"Cannot access page: {e}"

        return result
    except requests.RequestException as e:
        return {"ok": False, "workspace": "", "page_title": "", "error": str(e)}


def _clean_page_id(page_id: str) -> str:
    """Clean and format a Notion page ID (handle URLs and various formats)."""
    # If it's a full URL, extract the ID
    if "notion.so" in page_id or "notion.site" in page_id:
        # Extract last segment (might have query params)
        parts = page_id.rstrip("/").split("/")
        last = parts[-1].split("?")[0].split("#")[0]
        # The ID might be appended to the title with a dash
        if "-" in last:
            page_id = last.split("-")[-1]
        else:
            page_id = last

    # Remove dashes if present
    page_id = page_id.replace("-", "").strip()

    # Format as UUID with dashes
    if len(page_id) == 32:
        return f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"

    return page_id


# ── Rich text helpers ───────────────────────────────────────────────────────

def _rich_text(text: str, bold: bool = False, color: str = "default", code: bool = False) -> dict:
    annotations = {"bold": bold, "italic": False, "strikethrough": False,
                   "underline": False, "code": code, "color": color}
    return {"type": "text", "text": {"content": text[:2000]}, "annotations": annotations}


def _heading(level: int, text: str) -> dict:
    return {
        "object": "block",
        "type": f"heading_{level}",
        f"heading_{level}": {"rich_text": [_rich_text(text, bold=True)]},
    }


def _paragraph(text: str, bold: bool = False, color: str = "default") -> dict:
    # Split long text into chunks (Notion limit: 2000 chars per rich_text)
    chunks = []
    remaining = text
    while remaining:
        chunks.append(_rich_text(remaining[:2000], bold=bold, color=color))
        remaining = remaining[2000:]
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": chunks},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str = "📋", color: str = "blue_background") -> dict:
    chunks = []
    remaining = text
    while remaining:
        chunks.append(_rich_text(remaining[:2000]))
        remaining = remaining[2000:]
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": chunks,
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        },
    }


def _bulleted(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_rich_text(text[:2000])]},
    }


def _table_row(cells: list) -> dict:
    return {
        "type": "table_row",
        "table_row": {
            "cells": [[_rich_text(str(c)[:2000])] for c in cells]
        }
    }


# ── Export analysis to Notion ───────────────────────────────────────────────

def export_analysis_to_notion(token: str, parent_page_id: str, ticket: dict) -> str:
    """Create a rich Notion page with the full ticket analysis. Returns the page URL."""
    pid = _clean_page_id(parent_page_id)

    subject = ticket.get("subject", "Ticket")[:80]
    fid = ticket.get("freshdesk_id", "") or ticket.get("ticket_id", "")
    status = ticket.get("status", "N/A")
    classification = ticket.get("classification", "N/A")
    risk = ticket.get("risk_level", "N/A")
    rice = ticket.get("rice_score", 0)
    po_decision = ticket.get("po_decision", "N/A")

    # Status emoji
    status_emoji = {"Open": "🟡", "In Progress": "🔵", "Pending Approval": "🟠",
                    "Resolved": "🟢", "Closed": "✅"}.get(status, "⚪")
    risk_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(str(risk).lower(), "⚪")

    # Build page children (blocks)
    children = []

    # Metadata callout
    meta_lines = [
        f"Requester: {ticket.get('requester_name', 'N/A')} ({ticket.get('requester_email', '')})",
        f"Status: {status_emoji} {status}  |  Risk: {risk_emoji} {risk}  |  RICE: {rice}",
        f"Classification: {classification}  |  PO Decision: {po_decision}",
        f"Template: {ticket.get('template_name', 'N/A')}  |  Workflow: {ticket.get('workflow_name', 'N/A')}",
        f"Created: {ticket.get('created_at', 'N/A')}  |  Resolved: {ticket.get('resolved_at', 'N/A')}",
    ]
    children.append(_callout("\n".join(meta_lines), emoji="📋", color="blue_background"))
    children.append(_divider())

    # AI Analysis
    analysis = ticket.get("analysis_text", "") or ticket.get("analysis", "")
    if analysis:
        children.append(_heading(2, "AI Analysis"))
        for para in analysis.split("\n"):
            para = para.strip()
            if para:
                # Check if it's a sub-heading (starts with **...**)
                if para.startswith("**") and para.endswith("**"):
                    children.append(_heading(3, para.strip("* ")))
                elif para.startswith("- ") or para.startswith("• "):
                    children.append(_bulleted(para.lstrip("-• ").strip()))
                else:
                    children.append(_paragraph(para))
        children.append(_divider())

    # Summary
    summary = ticket.get("summary", "")
    if summary:
        children.append(_heading(2, "Summary"))
        children.append(_callout(summary, emoji="💡", color="yellow_background"))
        children.append(_divider())

    # Draft Responses
    for lang_code, lang_name, emoji in [("_fr", "French", "🇫🇷"), ("_en", "English", "🇬🇧")]:
        draft = ticket.get(f"draft_response{lang_code}", "")
        if draft:
            children.append(_heading(2, f"Draft Response ({lang_name}) {emoji}"))
            for para in draft.split("\n"):
                if para.strip():
                    children.append(_paragraph(para.strip()))
            children.append(_divider())

    # RICE Score
    if rice:
        children.append(_heading(2, "RICE Score Breakdown"))
        rice_items = [
            ("Reach", ticket.get("rice_reach", "N/A")),
            ("Impact", ticket.get("rice_impact", "N/A")),
            ("Confidence", ticket.get("rice_confidence", "N/A")),
            ("Effort", ticket.get("rice_effort", "N/A")),
            ("Total Score", rice),
        ]
        for label, val in rice_items:
            children.append(_bulleted(f"{label}: {val}"))

        rice_details = ticket.get("rice_details", "")
        if rice_details:
            children.append(_paragraph(""))
            for line in rice_details.split("\n"):
                if line.strip():
                    children.append(_paragraph(line.strip()))

    # PRD / Deep Analysis
    prd_raw = ticket.get("prd_content", "")
    if prd_raw:
        children.append(_divider())
        children.append(_heading(2, "Deep Analysis"))

        # Try to parse as structured JSON first
        prd = {}
        try:
            import json
            prd = json.loads(prd_raw) if isinstance(prd_raw, str) else prd_raw
        except (json.JSONDecodeError, TypeError):
            prd = {}

        if isinstance(prd, dict) and (prd.get("current_behaviour_context") or prd.get("requested_functional_change")):
            # Structured PRD — render each section
            if prd.get("intro_sentence"):
                children.append(_callout(prd["intro_sentence"], "📋"))

            # Helper to render text with bullet detection
            def _render_text_block(text):
                blocks = []
                for para in text.split("\n"):
                    para = para.strip()
                    if para.startswith("* ") or para.startswith("- "):
                        blocks.append(_bulleted(para.lstrip("*- ").strip()))
                    elif para:
                        blocks.append(_paragraph(para))
                return blocks

            if prd.get("current_behaviour_context"):
                children.append(_heading(3, "Current Behaviour — Context"))
                children.extend(_render_text_block(prd["current_behaviour_context"]))

            if prd.get("current_behaviour_problems"):
                children.append(_heading(3, "Current Behaviour — Problems"))
                children.extend(_render_text_block(prd["current_behaviour_problems"]))

            # Main section: Requested Functional Change (or fallback to new_behaviour)
            func_change = prd.get("requested_functional_change") or prd.get("new_behaviour")
            if func_change:
                children.append(_heading(3, "Requested Functional Change"))
                children.extend(_render_text_block(func_change))

            if prd.get("visibility_rules") and prd["visibility_rules"] != "N/A":
                children.append(_heading(3, "Visibility Rules"))
                children.extend(_render_text_block(prd["visibility_rules"]))

            if prd.get("reference_pattern") and prd["reference_pattern"] != "N/A":
                children.append(_heading(3, "Reference Pattern"))
                children.append(_paragraph(prd["reference_pattern"]))

            # Proposed wording — new structured format
            has_wording = any(prd.get(k) and prd[k] != "N/A" for k in
                           ["proposed_wording_current_fr", "proposed_wording_new_fr", "proposed_wording"])
            if has_wording:
                children.append(_heading(3, "Proposed Wording"))
                for key, label in [
                    ("proposed_wording_current_fr", "Current FR"),
                    ("proposed_wording_current_en", "Current EN"),
                    ("proposed_wording_new_fr", "New FR"),
                    ("proposed_wording_new_en", "New EN"),
                ]:
                    val = prd.get(key, "")
                    if val and val != "N/A":
                        children.append(_paragraph(f"{label}: {val}"))
                # Fallback for old single-field format
                if prd.get("proposed_wording") and not prd.get("proposed_wording_current_fr"):
                    children.extend(_render_text_block(prd["proposed_wording"]))

            if prd.get("test_scenarios") and isinstance(prd["test_scenarios"], list):
                children.append(_heading(3, "Test Scenarios"))
                for i, s in enumerate(prd["test_scenarios"], 1):
                    children.append(_bulleted(f"{i}. {s.get('scenario', '')} — Input: {s.get('input', '')} → Expected: {s.get('expected', '')}"))

            meta_parts = []
            if prd.get("complexity_assessment"):
                meta_parts.append(f"Complexity: {prd['complexity_assessment']}")
            if prd.get("legal_reference") and prd["legal_reference"] != "N/A":
                meta_parts.append(f"Legal: {prd['legal_reference']}")
            if prd.get("period_logic"):
                meta_parts.append(f"Period logic: {prd['period_logic']}")
            if meta_parts:
                children.append(_callout(" | ".join(meta_parts), "ℹ️"))
        else:
            # Fallback: raw text (old format)
            text = prd_raw if isinstance(prd_raw, str) else str(prd_raw)
            for para in text.split("\n"):
                para = para.strip()
                if para:
                    if para.startswith("# "):
                        children.append(_heading(2, para.lstrip("# ")))
                    elif para.startswith("## "):
                        children.append(_heading(3, para.lstrip("# ")))
                    elif para.startswith("- ") or para.startswith("• "):
                        children.append(_bulleted(para.lstrip("-• ").strip()))
                    else:
                        children.append(_paragraph(para))

    # Notion API limit: max 100 blocks per request
    # Split into batches if needed
    page_url = _create_page_with_blocks(token, pid, f"#{fid} — {subject}", status_emoji, children)
    return page_url


def _create_page_with_blocks(token: str, parent_id: str, title: str, icon_emoji: str, children: list) -> str:
    """Create a Notion page and append blocks (handles >100 block limit)."""
    # Create the page with first batch of children (max 100)
    first_batch = children[:100]

    body = {
        "parent": {"page_id": parent_id},
        "icon": {"type": "emoji", "emoji": icon_emoji},
        "properties": {
            "title": [{"type": "text", "text": {"content": title[:2000]}}]
        },
        "children": first_batch,
    }

    resp = requests.post(f"{NOTION_API}/pages", headers=_headers(token), json=body, timeout=30)
    resp.raise_for_status()
    page = resp.json()
    page_id = page["id"]
    page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    # Append remaining blocks in batches of 100
    remaining = children[100:]
    while remaining:
        batch = remaining[:100]
        remaining = remaining[100:]
        append_body = {"children": batch}
        ar = requests.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=_headers(token), json=append_body, timeout=30
        )
        ar.raise_for_status()

    return page_url
