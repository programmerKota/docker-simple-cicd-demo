from __future__ import annotations

from jarvis_home.policy import PolicyEngine
from jarvis_home.schemas import ActionDecision, RiskLevel, UserContext


def test_low_risk_allowed():
    result = PolicyEngine().evaluate(UserContext(username="u"), "memory.search", {}, RiskLevel.LOW)
    assert result.decision == ActionDecision.ALLOW


def test_light_control_requires_approval():
    result = PolicyEngine().evaluate(
        UserContext(username="u"),
        "home.call_service",
        {"domain": "light", "service": "turn_off"},
        RiskLevel.MEDIUM,
    )
    assert result.decision == ActionDecision.APPROVAL


def test_unlock_is_high_risk():
    result = PolicyEngine().evaluate(
        UserContext(username="u"),
        "home.call_service",
        {"domain": "lock", "service": "unlock"},
        RiskLevel.MEDIUM,
    )
    assert result.risk == RiskLevel.HIGH
    assert result.decision == ActionDecision.APPROVAL


def test_critical_denied():
    result = PolicyEngine().evaluate(UserContext(username="u"), "x", {}, RiskLevel.CRITICAL)
    assert result.decision == ActionDecision.DENY
