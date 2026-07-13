from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class PolicyUnavailable(RuntimeError):
    pass


class PolicyDenied(PermissionError):
    pass


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    require_approval: bool
    reason: str
    policy_version: str = "unknown"


class OPAClient:
    """Small fail-closed client for the JARVIS Home policy decision point."""

    def __init__(
        self,
        base_url: str,
        decision_path: str = "jarvis/home/decision",
        timeout: float = 3.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.decision_path = decision_path.strip("/")
        self.timeout = timeout

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health?bundles=true")
                response.raise_for_status()
                return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def decide(self, policy_input: dict[str, Any]) -> PolicyDecision:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/data/{self.decision_path}",
                    json={"input": policy_input},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise PolicyUnavailable(f"Policy service unavailable: {exc}") from exc

        result = payload.get("result")
        if not isinstance(result, dict):
            raise PolicyUnavailable("Policy service returned no structured decision")
        decision = PolicyDecision(
            allow=bool(result.get("allow", False)),
            require_approval=bool(result.get("require_approval", True)),
            reason=str(result.get("reason") or "No policy reason supplied"),
            policy_version=str(result.get("policy_version") or "unknown"),
        )
        if not decision.allow:
            raise PolicyDenied(decision.reason)
        return decision
