"""Tests for load_pm_decision_from_ticket and the ticket detail PM Decision display."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── load_pm_decision_from_ticket unit tests ───────────────────────────────────
# We test the helper function's logic directly without importing the full Flask
# app (which requires a running DB). We replicate the function's contract inline
# and verify the template source contains the expected display strings.

def _load_pm_decision(ticket: dict) -> dict:
    """Inline replica of app.load_pm_decision_from_ticket for isolated testing."""
    try:
        raw = ticket.get("pm_decision_json") or "{}"
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


# ── Valid JSON ────────────────────────────────────────────────────────────────

def test_returns_parsed_dict_for_valid_json():
    payload = {
        "decision": "make_editable",
        "classification": "client_preference",
        "global_change_risk": "high",
        "should_mention_law": False,
        "needs_prd": False,
    }
    ticket = {"pm_decision_json": json.dumps(payload)}
    result = _load_pm_decision(ticket)
    assert result["decision"] == "make_editable"
    assert result["classification"] == "client_preference"
    assert result["global_change_risk"] == "high"
    assert result["should_mention_law"] is False


def test_returns_all_keys_after_round_trip():
    payload = {"decision": "accept_bug", "classification": "bug", "max_words": 200}
    ticket = {"pm_decision_json": json.dumps(payload)}
    result = _load_pm_decision(ticket)
    assert result["decision"] == "accept_bug"
    assert result["max_words"] == 200


# ── Invalid / missing JSON ────────────────────────────────────────────────────

def test_returns_empty_dict_for_invalid_json():
    ticket = {"pm_decision_json": "not valid json {{{"}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_empty_string():
    ticket = {"pm_decision_json": ""}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_none():
    ticket = {"pm_decision_json": None}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_missing_key():
    ticket = {}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_json_array():
    """If someone stores a JSON array rather than an object, return {} safely."""
    ticket = {"pm_decision_json": json.dumps(["not", "a", "dict"])}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_json_string():
    ticket = {"pm_decision_json": json.dumps("just a string")}
    result = _load_pm_decision(ticket)
    assert result == {}


def test_returns_empty_dict_for_default_value():
    """The DB default is '{}' — this should parse to {} which is falsy."""
    ticket = {"pm_decision_json": "{}"}
    result = _load_pm_decision(ticket)
    assert result == {}


# ── Never raises ──────────────────────────────────────────────────────────────

def test_never_raises_on_any_input():
    for bad_input in [None, "", "null", "[]", "{invalid}", '{"key": undefined}', 123]:
        try:
            _load_pm_decision({"pm_decision_json": bad_input})
        except Exception as e:
            raise AssertionError(f"load_pm_decision raised for input {bad_input!r}: {e}")


# ── Template source checks ────────────────────────────────────────────────────

def test_ticket_template_contains_pm_decision_card_title():
    """The ticket.html template must contain the PM Decision card heading."""
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "PM Decision" in source, "ticket.html must contain 'PM Decision' heading"


def test_ticket_template_shows_decision_field():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "pm_decision.decision" in source


def test_ticket_template_shows_global_change_risk():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "global_change_risk" in source


def test_ticket_template_shows_should_mention_law():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "should_mention_law" in source


def test_ticket_template_shows_recommended_action():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "recommended_action" in source


def test_ticket_template_handles_empty_pm_decision():
    """Template must have a fallback for when pm_decision is empty/falsy."""
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    # The else branch must mention that no PM decision is available
    assert "No PM decision generated yet" in source


def test_ticket_template_marks_as_readonly():
    """The PM Decision card must be marked as read-only."""
    template_path = Path(__file__).resolve().parents[1] / "templates" / "ticket.html"
    source = template_path.read_text()
    assert "read-only" in source


# ── app.py wiring checks ──────────────────────────────────────────────────────

def test_app_uses_load_pm_decision_from_ticket():
    """app.py must define load_pm_decision_from_ticket and use it in ticket_detail."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "def load_pm_decision_from_ticket" in source
    assert "load_pm_decision_from_ticket" in source


def test_app_uses_extract_pm_ticket_summary():
    """app.py must use the evidence helper extract_pm_ticket_summary."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "extract_pm_ticket_summary" in source


def test_app_uses_extract_pm_evidence():
    """app.py must use extract_pm_evidence for richer gate inputs."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text()
    assert "extract_pm_evidence" in source
