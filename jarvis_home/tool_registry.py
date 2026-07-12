from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .audit import AuditLog
from .policy import PolicyEngine
from .schemas import (
    ActionDecision,
    RiskLevel,
    ToolInvocation,
    ToolResult,
    UserContext,
)
from .services.approvals import ApprovalService
from .services.events import EventBus

ToolHandler = Callable[..., Any | Awaitable[Any]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: RiskLevel
    handler: ToolHandler

    def ollama_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(
        self,
        policy: PolicyEngine,
        approvals: ApprovalService,
        audit: AuditLog,
        events: EventBus,
    ):
        self.policy = policy
        self.approvals = approvals
        self.audit = audit
        self.events = events
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Duplicate tool: {definition.name}")
        self._tools[definition.name] = definition

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.ollama_schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def invoke(
        self,
        invocation: ToolInvocation,
        user: UserContext,
        *,
        bypass_policy: bool = False,
    ) -> ToolResult:
        definition = self._tools.get(invocation.tool_name)
        if not definition:
            self.audit.record(
                user.username,
                "tool.invoke",
                invocation.tool_name,
                "denied",
                {"reason": "unknown tool"},
            )
            return ToolResult(ok=False, error=f"Unknown tool: {invocation.tool_name}")

        if not bypass_policy:
            policy = self.policy.evaluate(user, invocation.tool_name, invocation.arguments, definition.risk)
            if policy.decision == ActionDecision.DENY:
                self.audit.record(
                    user.username,
                    "tool.invoke",
                    invocation.tool_name,
                    "denied",
                    {"reason": policy.reason, "arguments": invocation.arguments},
                )
                return ToolResult(
                    ok=False,
                    error=policy.reason,
                    metadata={"decision": "deny", "risk": policy.risk.value},
                )
            if policy.decision == ActionDecision.APPROVAL:
                pending = self.approvals.create(user, invocation, policy.risk, policy.reason)
                self.audit.record(
                    user.username,
                    "tool.invoke",
                    invocation.tool_name,
                    "approval_required",
                    {"approval_id": pending.id, "arguments": invocation.arguments},
                )
                await self.events.publish("approval.created", pending.model_dump())
                return ToolResult(
                    ok=False,
                    error="Approval required",
                    metadata={"decision": "approval", "approval": pending.model_dump()},
                )

        try:
            result = definition.handler(**invocation.arguments)
            if inspect.isawaitable(result):
                result = await result
            self.audit.record(
                user.username,
                "tool.invoke",
                invocation.tool_name,
                "success",
                {"arguments": invocation.arguments},
            )
            await self.events.publish(
                "tool.executed",
                {"tool": invocation.tool_name, "actor": user.username, "ok": True},
            )
            return ToolResult(ok=True, content=result)
        except Exception as exc:
            self.audit.record(
                user.username,
                "tool.invoke",
                invocation.tool_name,
                "error",
                {"arguments": invocation.arguments, "error": str(exc)},
            )
            await self.events.publish(
                "tool.executed",
                {
                    "tool": invocation.tool_name,
                    "actor": user.username,
                    "ok": False,
                    "error": str(exc),
                },
            )
            return ToolResult(ok=False, error=str(exc))
