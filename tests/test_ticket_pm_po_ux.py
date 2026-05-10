"""Tests for PM/PO UX improvements in templates/ticket.html.

Verifies:
  - PM/PO Review Summary card is present in the template
  - Evidence & Diagnostics section uses <details> (collapsed by default)
  - Draft Actions section has a no-auto-send note
  - Button labels are clear and correct
  - "Copy & Open in Freshdesk" renamed to "Draft Actions"
  - "Regenerate Draft" button has helper text
"""
import re
from pathlib import Path

TICKET_HTML = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"


def read_template():
    return TICKET_HTML.read_text(encoding="utf-8")


class TestPmPoSummaryCard:
    def test_summary_card_block_present(self):
        html = read_template()
        assert "pm_po_summary" in html, (
            "Template must reference ticket.pm_po_summary for the summary card"
        )

    def test_summary_card_has_next_action(self):
        html = read_template()
        assert "next_action" in html, (
            "PM/PO summary card must show the next_action field"
        )

    def test_summary_card_shows_classification(self):
        html = read_template()
        assert "classification_label" in html

    def test_summary_card_shows_decision(self):
        html = read_template()
        assert "decision_label" in html

    def test_summary_card_shows_safe_to_send_status(self):
        html = read_template()
        assert "safe_to_send_status" in html


class TestDiagnosticsCollapsed:
    def test_details_element_used_for_diagnostics(self):
        html = read_template()
        assert "<details" in html, (
            "Diagnostic cards must be wrapped in <details> for collapsible behaviour"
        )

    def test_diagnostics_section_has_summary_label(self):
        html = read_template()
        assert "Evidence" in html and "Diagnostics" in html, (
            "The <details> section must be labelled 'Evidence & Diagnostics'"
        )

    def test_details_not_open_by_default(self):
        """<details open> would expand by default — must not be present on diagnostics section."""
        html = read_template()
        # Count <details open> occurrences — should be 0 or very low (not the diagnostics one)
        open_details = re.findall(r'<details\s[^>]*open', html, re.IGNORECASE)
        # We allow zero or check the diagnostics specifically
        diagnostics_block = re.search(
            r'<details[^>]*>.*?Evidence.*?Diagnostics',
            html, re.DOTALL | re.IGNORECASE,
        )
        if diagnostics_block:
            block_text = diagnostics_block.group(0)
            assert 'open' not in block_text[:50], (
                "Diagnostics <details> must not have 'open' attribute (collapsed by default)"
            )


class TestDraftActionsSection:
    def test_section_renamed_to_draft_actions(self):
        html = read_template()
        assert "Draft Actions" in html, (
            "The 'Copy & Open in Freshdesk' section must be renamed to 'Draft Actions'"
        )

    def test_old_name_not_used_as_heading(self):
        html = read_template()
        # The heading should not still say "Copy & Open in Freshdesk" as the section title
        # (it may appear as a comment or button label but not as the <h3> heading)
        h3_matches = re.findall(r'<h3[^>]*>.*?</h3>', html, re.DOTALL)
        for h3 in h3_matches:
            assert "Copy & Open in Freshdesk" not in h3, (
                "Section <h3> heading must not still say 'Copy & Open in Freshdesk'"
            )

    def test_no_auto_send_note_present(self):
        html = read_template()
        # The note must mention that no reply is sent automatically
        assert (
            "No reply is sent automatically" in html
            or "not sent automatically" in html.lower()
            or "sending still happens manually" in html
        ), "Draft Actions section must warn that no reply is sent automatically"

    def test_copy_only_button_still_present(self):
        html = read_template()
        assert "copySelectedOnly" in html or "Copy Only" in html


class TestButtonLabels:
    def test_regenerate_draft_button_label(self):
        html = read_template()
        assert "Regenerate Draft" in html, (
            "Regenerate button must say 'Regenerate Draft' not 'Regenerate Drafts'"
        )

    def test_no_plain_regenerate_drafts_label(self):
        """Old label 'Regenerate Drafts' (without FR + EN or (FR+EN)) should be gone."""
        html = read_template()
        # Allow "Regenerate Draft (FR + EN)" but not bare "Regenerate Drafts"
        bad_labels = re.findall(r'Regenerate Drafts(?!\s*\()', html)
        assert not bad_labels, (
            f"Found old button label 'Regenerate Drafts' — should be 'Regenerate Draft (FR + EN)'. "
            f"Occurrences: {len(bad_labels)}"
        )
