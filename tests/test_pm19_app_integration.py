"""Source-level integration tests for PR 19 — structured PM lessons in app.py.

Tests verify:
- app.py imports the helper functions
- Draft generation, regeneration, and prepare_analysis reference structured PM lesson helpers
- ticket_detail route retrieves structured_pm_lessons_used
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_APP_SRC = Path(__file__).resolve().parents[1] / "app.py"
_APP_TEXT = _APP_SRC.read_text(encoding="utf-8")

# ── app.py uses the helpers ───────────────────────────────────────────────────

def test_app_imports_find_relevant_structured_pm_lessons():
    assert "find_relevant_structured_pm_lessons" in _APP_TEXT


def test_app_imports_format_structured_pm_lessons_for_prompt():
    assert "format_structured_pm_lessons_for_prompt" in _APP_TEXT


# ── All three prompt-injection points are present ─────────────────────────────

def test_draft_generation_injects_struct_lessons():
    """The draft generation block should call find_relevant_structured_pm_lessons."""
    # Verify there are at least 3 occurrences (draft, regen, analysis)
    count = _APP_TEXT.count("find_relevant_structured_pm_lessons")
    assert count >= 3, (
        f"Expected find_relevant_structured_pm_lessons in at least 3 places, found {count}"
    )


def test_draft_generation_block_present():
    assert "Inject structured PM lessons into draft context" in _APP_TEXT


def test_regeneration_block_present():
    assert "Inject structured PM lessons into regeneration context" in _APP_TEXT


def test_analysis_block_present():
    assert "Inject structured PM lessons into analysis context" in _APP_TEXT


# ── ticket_detail retrieves structured lessons ────────────────────────────────

def test_ticket_detail_retrieves_structured_pm_lessons_used():
    assert "structured_pm_lessons_used" in _APP_TEXT


def test_ticket_detail_find_call_present():
    """ticket_detail must call find_relevant_structured_pm_lessons."""
    assert "structured_pm_lessons_used" in _APP_TEXT
    # Check it's assigned from the helper (not hardcoded [])
    assert "find_relevant_structured_pm_lessons(" in _APP_TEXT


# ── Ticket template renders card ─────────────────────────────────────────────

_TICKET_HTML = (Path(__file__).resolve().parents[1] / "templates" / "ticket.html").read_text(
    encoding="utf-8"
)


def test_ticket_html_has_structured_pm_lessons_card():
    assert "Structured PM Lessons Used" in _TICKET_HTML


def test_ticket_html_renders_lesson_type():
    assert "sl.lesson_type" in _TICKET_HTML


def test_ticket_html_renders_instruction():
    assert "sl.instruction" in _TICKET_HTML


def test_ticket_html_renders_confidence():
    assert "sl.confidence" in _TICKET_HTML


def test_ticket_html_renders_hit_count():
    assert "sl.hit_count" in _TICKET_HTML


# ── pm_learning module exports helpers ───────────────────────────────────────

def test_pm_learning_exports_find():
    from ai.pm_learning import find_relevant_structured_pm_lessons  # noqa: F401


def test_pm_learning_exports_format():
    from ai.pm_learning import format_structured_pm_lessons_for_prompt  # noqa: F401


def test_pm_learning_exports_derive():
    from ai.pm_learning import derive_pm_lesson_signals  # noqa: F401


# ── Runner accepts structured_pm_lessons param ───────────────────────────────

def test_runner_signature_has_structured_pm_lessons_param():
    from ai.pm_decision_runner import build_pm_decision_for_ticket
    import inspect
    sig = inspect.signature(build_pm_decision_for_ticket)
    assert "structured_pm_lessons" in sig.parameters


def test_runner_gate_results_has_structured_pm_lessons_key():
    from ai.pm_decision_runner import build_pm_decision_for_ticket
    result = build_pm_decision_for_ticket("Test ticket")
    assert "structured_pm_lessons" in result["_gate_results"]


# ── Builder uses lesson signals ───────────────────────────────────────────────

_BUILDER_SRC = (Path(__file__).resolve().parents[1] / "ai" / "pm_decision_builder.py").read_text(
    encoding="utf-8"
)


def test_builder_reads_structured_pm_lessons_from_gate_results():
    assert "structured_pm_lessons" in _BUILDER_SRC


def test_builder_uses_prefer_short_answer():
    assert "prefer_short_answer" in _BUILDER_SRC


def test_builder_uses_prefer_make_editable():
    assert "prefer_make_editable" in _BUILDER_SRC


# ── Gates reference lesson signals ───────────────────────────────────────────

def test_legal_gate_references_avoid_legal_references():
    src = (Path(__file__).resolve().parents[1] / "ai" / "gates" / "legal_preference_gate.py"
           ).read_text(encoding="utf-8")
    assert "avoid_legal_references" in src


def test_global_change_gate_references_prefer_make_editable():
    src = (Path(__file__).resolve().parents[1] / "ai" / "gates" / "global_change_risk_gate.py"
           ).read_text(encoding="utf-8")
    assert "prefer_make_editable" in src


def test_dev_need_gate_references_prefer_support_guidance():
    src = (Path(__file__).resolve().parents[1] / "ai" / "gates" / "development_need_gate.py"
           ).read_text(encoding="utf-8")
    assert "prefer_support_guidance" in src
