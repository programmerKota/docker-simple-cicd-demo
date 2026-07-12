from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import ActionDecision, RiskLevel, UserContext


@dataclass(frozen=True)
class PolicyResult:
    decision: ActionDecision
    reason: str
    risk: RiskLevel


class PolicyEngine:
    """Deterministic guardrail between the language model and real-world actions."""

    def evaluate(
        self,
        user: UserContext,
        tool_name: str,
        arguments: dict[str, Any],
        declared_risk: RiskLevel,
    ) -> PolicyResult:
        risk = self._dynamic_risk(tool_name, arguments, declared_risk)
        if user.role != "owner" and risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return PolicyResult(ActionDecision.DENY, "Owner role required", risk)
        if risk == RiskLevel.CRITICAL:
            return PolicyResult(
                ActionDecision.DENY,
                "Critical actions are denied by the core policy and require a custom audited plugin",
                risk,
            )
        if risk == RiskLevel.HIGH:
            return PolicyResult(ActionDecision.APPROVAL, "Explicit approval required", risk)
        if risk == RiskLevel.MEDIUM:
            return PolicyResult(ActionDecision.APPROVAL, "Confirmation required", risk)
        return PolicyResult(ActionDecision.ALLOW, "Low-risk action", risk)

    def _dynamic_risk(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        declared: RiskLevel,
    ) -> RiskLevel:
        if tool_name == "home.call_service":
            domain = str(arguments.get("domain", "")).lower()
            service = str(arguments.get("service", "")).lower()
            if domain in {"lock", "alarm_control_panel", "cover"}:
                return RiskLevel.HIGH
            if domain in {"camera", "person", "device_tracker"}:
                return RiskLevel.MEDIUM
            if service in {"unlock", "disarm", "open_cover"}:
                return RiskLevel.HIGH
            if domain in {"light", "fan", "media_player", "climate", "switch"}:
                return max(declared, RiskLevel.MEDIUM, key=self._rank)
        if tool_name == "shell.run":
            return RiskLevel.HIGH
        if tool_name == "filesystem.write":
            return RiskLevel.MEDIUM
        return declared

    @staticmethod
    def _rank(risk: RiskLevel) -> int:
        return {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }[risk]
