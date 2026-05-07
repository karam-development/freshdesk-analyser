"""App-level source checks for PM analysis flow wiring (PR 15)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _source() -> str:
    return APP_PATH.read_text()


# ── build_pm_analysis_prompt_block wiring ────────────────────────────────────

def test_app_imports_build_pm_analysis_prompt_block():
    assert "build_pm_analysis_prompt_block" in _source(), \
        "app.py must use build_pm_analysis_prompt_block"


def test_app_imports_build_pm_analysis_prompt_block_from_correct_module():
    assert "pm_analysis_context" in _source(), \
        "app.py must import from ai.pm_analysis_context"


# ── apply_pm_analysis_guard wiring ───────────────────────────────────────────

def test_app_imports_apply_pm_analysis_guard():
    assert "apply_pm_analysis_guard" in _source(), \
        "app.py must use apply_pm_analysis_guard"


def test_app_imports_apply_pm_analysis_guard_from_correct_module():
    assert "pm_analysis_guard" in _source(), \
        "app.py must import from ai.pm_analysis_guard"


# ── pm_decision_json persistence ─────────────────────────────────────────────

def test_app_writes_pm_decision_json():
    assert "pm_decision_json" in _source(), \
        "app.py must reference pm_decision_json"


def test_app_uses_load_pm_decision_from_ticket_in_analysis_flow():
    source = _source()
    assert "load_pm_decision_from_ticket" in source, \
        "app.py must use load_pm_decision_from_ticket in the analysis flow"


# ── Draft PM prompt block not removed ────────────────────────────────────────

def test_app_still_uses_build_pm_prompt_block_for_drafts():
    assert "build_pm_prompt_block" in _source(), \
        "app.py must still use build_pm_prompt_block for draft generation"


# ── Analysis guard persists to qa_issues ─────────────────────────────────────

def test_app_uses_merge_pm_guard_warnings_in_analysis_flow():
    assert "merge_pm_guard_warnings_into_qa_issues" in _source(), \
        "app.py must use merge_pm_guard_warnings_into_qa_issues"


# ── prepare_analysis route exists ────────────────────────────────────────────

def test_prepare_analysis_route_exists():
    assert "prepare-analysis" in _source(), \
        "app.py must define the /prepare-analysis route"


def test_prepare_analysis_uses_pm_analysis_block():
    source = _source()
    assert "_pm_analysis_block" in source, \
        "prepare_analysis must build and inject _pm_analysis_block"


def test_prepare_analysis_injects_block_into_enhanced_kb():
    source = _source()
    # The injection pattern: enhanced_kb = _pm_analysis_block + "\n\n" + enhanced_kb
    assert "_pm_analysis_block" in source and "enhanced_kb" in source, \
        "prepare_analysis must inject pm_analysis_block into enhanced_kb"


# ── Analysis guard wired in prepare_analysis ─────────────────────────────────

def test_prepare_analysis_calls_apply_pm_analysis_guard():
    source = _source()
    assert "apply_pm_analysis_guard" in source


def test_prepare_analysis_persists_analysis_warnings():
    source = _source()
    assert "_analysis_warnings" in source, \
        "prepare_analysis must collect _analysis_warnings from the guard"


# ── Acceptance: pm_analysis_context module is importable ─────────────────────

def test_pm_analysis_context_module_importable():
    from ai.pm_analysis_context import build_pm_analysis_prompt_block
    assert callable(build_pm_analysis_prompt_block)


def test_pm_analysis_guard_module_importable():
    from ai.pm_analysis_guard import apply_pm_analysis_guard
    assert callable(apply_pm_analysis_guard)


def test_pm_analysis_instructions_module_importable():
    from ai.pm_analysis_instructions import (
        get_pm_analysis_mode,
        build_pm_analysis_instructions,
    )
    assert callable(get_pm_analysis_mode)
    assert callable(build_pm_analysis_instructions)
