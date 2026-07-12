from __future__ import annotations

import pytest

from jarvis_home.schemas import ToolInvocation, UserContext


@pytest.mark.asyncio
async def test_medium_risk_creates_approval(application):
    result = await application.registry.invoke(
        ToolInvocation(
            tool_name="filesystem.write",
            arguments={"path": "x.txt", "content": "hello"},
        ),
        UserContext(username="admin"),
    )
    assert not result.ok
    assert result.metadata["decision"] == "approval"
    pending = application.approvals.list_pending("admin")
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_approved_action_executes(application):
    first = await application.registry.invoke(
        ToolInvocation(
            tool_name="filesystem.write",
            arguments={"path": "x.txt", "content": "hello"},
        ),
        UserContext(username="admin"),
    )
    approval_id = first.metadata["approval"]["id"]
    invocation = application.approvals.claim(approval_id, "admin", True)
    assert invocation is not None
    result = await application.registry.invoke(invocation, UserContext(username="admin"), bypass_policy=True)
    assert result.ok
    assert application.sandbox.read_text("x.txt") == "hello"
