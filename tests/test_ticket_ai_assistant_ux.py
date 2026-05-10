"""Tests for AI Assistant UX improvements in templates/ticket.html.

Verifies:
  - Section renamed from "AI Assistant" to "Ask about this ticket"
  - Quick prompt chips are present
  - Placeholder text is descriptive
  - setAIChatPrompt JS helper is defined
  - Old generic heading "AI Assistant" is not used as the primary section title
"""
import re
from pathlib import Path

TICKET_HTML = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"

REQUIRED_QUICK_PROMPTS = [
    "Explain why this is expected behaviour",
    "Write a shorter client-ready response",
    "What should Support do next?",
    "What evidence supports this decision?",
    "Is this a bug or client preference?",
]


def read_template():
    return TICKET_HTML.read_text(encoding="utf-8")


class TestAiAssistantRename:
    def test_section_has_new_heading(self):
        html = read_template()
        assert "Ask about this ticket" in html, (
            "AI Assistant section must be renamed to 'Ask about this ticket'"
        )

    def test_old_h3_heading_removed(self):
        """The <h3> heading must not say 'AI Assistant' anymore."""
        html = read_template()
        h3_blocks = re.findall(r'<h3[^>]*>.*?</h3>', html, re.DOTALL)
        for block in h3_blocks:
            # Strip tags for clean text comparison
            text = re.sub(r'<[^>]+>', '', block).strip()
            assert text != "AI Assistant", (
                "Found <h3>AI Assistant</h3> — section must be renamed"
            )

    def test_comment_updated(self):
        """HTML comment should reference the new name, not the old."""
        html = read_template()
        # The section comment should say ASK ABOUT THIS TICKET or similar
        assert "<!-- ASK ABOUT THIS TICKET -->" in html or "Ask about this ticket" in html


class TestQuickPromptChips:
    def test_all_required_prompts_present(self):
        html = read_template()
        for prompt in REQUIRED_QUICK_PROMPTS:
            assert prompt in html, (
                f"Quick prompt chip missing: '{prompt}'"
            )

    def test_prompts_use_set_ai_chat_prompt(self):
        html = read_template()
        assert "setAIChatPrompt" in html, (
            "Quick prompt chips must call setAIChatPrompt() JS function"
        )

    def test_set_ai_chat_prompt_defined(self):
        html = read_template()
        assert "function setAIChatPrompt" in html, (
            "setAIChatPrompt must be defined as a JS function in the template"
        )


class TestPlaceholderText:
    def test_placeholder_is_descriptive(self):
        html = read_template()
        # Old vague placeholder
        old_placeholder = "Ask the AI to adjust, explain, or reword..."
        assert old_placeholder not in html, (
            "Old vague placeholder must be replaced with a more descriptive one"
        )

    def test_new_placeholder_mentions_context(self):
        html = read_template()
        # New placeholder should mention ticket/draft/decision context
        placeholder_matches = re.findall(r'placeholder="([^"]+)"', html)
        ai_placeholder = [p for p in placeholder_matches if "ticket" in p.lower() or "draft" in p.lower() or "pm decision" in p.lower()]
        assert ai_placeholder, (
            "AI chat input placeholder must mention ticket, draft, or PM decision context"
        )


class TestSubheading:
    def test_subheading_is_descriptive(self):
        html = read_template()
        # Old subheading
        old_sub = "Ask questions, request changes, or add context"
        # New subheading should be more specific
        assert "Refine the draft" in html or "explanations" in html or old_sub not in html, (
            "AI section subheading should be updated to describe specific use cases"
        )
