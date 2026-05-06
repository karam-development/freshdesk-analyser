"""AI decision schemas for the PM decision layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ── Allowed value sets ────────────────────────────────────────────────────────

DECISION_VALUES = frozenset({
    "refuse_global_change",
    "make_editable",
    "accept_bug",
    "feature_request",
    "explain_workaround",
    "support_guidance",
    "needs_analysis",
    "reuse_existing_pattern",
})

CLASSIFICATION_VALUES = frozenset({
    "bug",
    "feature_request",
    "how_to",
    "client_preference",
    "expected_behaviour",
    "data",
    "sync",
    "needs_analysis",
    "other",
})

COMPLEXITY_VALUES = frozenset({"simple", "medium", "complex", "needs_analysis"})

ANSWER_DEPTH_VALUES = frozenset({"short", "normal", "detailed", "prd"})

DEVELOPMENT_TYPE_VALUES = frozenset({
    "no_dev",
    "bug_fix",
    "small_improvement",
    "feature_request",
    "support_guidance",
    "unclear",
})

LEGAL_STATUS_VALUES = frozenset({
    "mandatory",
    "accounting_required",
    "product_standard",
    "client_preference",
    "optional",
    "unclear",
})

GLOBAL_CHANGE_RISK_VALUES = frozenset({"low", "medium", "high", "unclear"})

REQUIRED_FIELDS = frozenset({
    "decision", "classification", "complexity", "answer_depth", "max_words",
    "needs_prd", "needs_development", "development_type", "recommended_team",
    "legal_status", "should_mention_law", "global_change_risk",
    "recommended_action", "reason", "confidence", "evidence_used",
})


# ── Safe defaults ─────────────────────────────────────────────────────────────

SAFE_DEFAULTS: dict = {
    "decision": "needs_analysis",
    "classification": "needs_analysis",
    "complexity": "needs_analysis",
    "answer_depth": "short",
    "max_words": 250,
    "needs_prd": False,
    "needs_development": False,
    "development_type": "unclear",
    "recommended_team": "",
    "legal_status": "unclear",
    "should_mention_law": False,
    "global_change_risk": "unclear",
    "recommended_action": "needs_analysis",
    "reason": "",
    "confidence": 0.5,
    "evidence_used": [],
}


@dataclass
class PMDecision:
    """Structured PM decision produced by the deterministic gate pipeline.

    All fields have safe defaults so that partial gate results never produce
    an over-confident or under-constrained decision.
    """

    decision: str = "needs_analysis"
    classification: str = "needs_analysis"
    complexity: str = "needs_analysis"
    answer_depth: str = "short"
    max_words: int = 250
    needs_prd: bool = False
    needs_development: bool = False
    development_type: str = "unclear"
    recommended_team: str = ""
    legal_status: str = "unclear"
    should_mention_law: bool = False
    global_change_risk: str = "unclear"
    recommended_action: str = "needs_analysis"
    reason: str = ""
    confidence: float = 0.5
    evidence_used: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "classification": self.classification,
            "complexity": self.complexity,
            "answer_depth": self.answer_depth,
            "max_words": self.max_words,
            "needs_prd": self.needs_prd,
            "needs_development": self.needs_development,
            "development_type": self.development_type,
            "recommended_team": self.recommended_team,
            "legal_status": self.legal_status,
            "should_mention_law": self.should_mention_law,
            "global_change_risk": self.global_change_risk,
            "recommended_action": self.recommended_action,
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence_used": list(self.evidence_used),
        }
