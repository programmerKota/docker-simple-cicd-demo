from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..application import Application
from ..schemas import ApprovalDecision, ToolResult, UserContext
from ..services.approvals import ApprovalError
from .deps import current_user, get_application

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> list[dict]:
    return [item.model_dump() for item in app.approvals.list_pending(user.username)]


@router.post("/{approval_id}", response_model=ToolResult)
async def decide(
    approval_id: str,
    payload: ApprovalDecision,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> ToolResult:
    try:
        invocation = app.approvals.claim(approval_id, user.username, payload.approved)
    except ApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if invocation is None:
        app.audit.record(user.username, "approval.decide", approval_id, "rejected")
        await app.events.publish("approval.rejected", {"id": approval_id})
        return ToolResult(ok=False, error="Action rejected")
    result = await app.registry.invoke(invocation, user, bypass_policy=True)
    app.approvals.store_result(approval_id, result.model_dump())
    app.audit.record(
        user.username,
        "approval.decide",
        approval_id,
        "executed" if result.ok else "error",
        {"tool": invocation.tool_name},
    )
    if invocation.conversation_id:
        app.conversations.add_message(
            invocation.conversation_id,
            "tool",
            str(result.content if result.ok else result.error),
            {"tool_name": invocation.tool_name, "approved": True},
        )
    await app.events.publish(
        "approval.executed",
        {"id": approval_id, "tool": invocation.tool_name, "ok": result.ok},
    )
    return result
