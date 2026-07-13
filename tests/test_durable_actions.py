from __future__ import annotations

from typing import Any

import pytest

from jarvis_home.schemas import RiskLevel, ToolInvocation, UserContext
from jarvis_home.services.durable_actions import DurableActionService, parse_light_action


def light_invocation(service: str = "turn_off", **service_data: Any) -> ToolInvocation:
    return ToolInvocation(
        tool_name="home.call_service",
        arguments={
            "domain": "light",
            "service": service,
            "service_data": service_data,
            "target": {"entity_id": "light.study"},
        },
    )


def test_parse_idempotent_light_action() -> None:
    action = parse_light_action(light_invocation("turn_on", brightness_pct=40))
    assert action is not None
    assert action.entity_id == "light.study"
    assert action.desired_state == "on"
    assert action.brightness_pct == 40


def test_parse_rejects_non_idempotent_toggle() -> None:
    with pytest.raises(ValueError, match="idempotent"):
        parse_light_action(light_invocation("toggle"))


def test_parse_rejects_multiple_entities() -> None:
    invocation = light_invocation()
    invocation.arguments["target"] = {"entity_id": "light.study,light.living_room"}
    with pytest.raises(ValueError, match="single valid"):
        parse_light_action(invocation)


def test_parse_rejects_unreviewed_service_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        parse_light_action(light_invocation("turn_on", transition=10))


@pytest.mark.asyncio
async def test_disabled_durable_layer_preserves_existing_nonphysical_actions(application) -> None:
    service = DurableActionService(application)
    assert service.enabled is False
    result = await service.execute_approved(
        "approval-test",
        ToolInvocation(tool_name="memory.remember", arguments={"content": "kept compatible"}),
        UserContext(username="admin", role="owner"),
    )
    assert result.ok
    assert result.metadata["durable"] is False
    assert application.memory.search("kept compatible")


def test_approved_action_is_recoverable_until_result_is_stored(application) -> None:
    pending = application.approvals.create(
        UserContext(username="admin", role="owner"),
        light_invocation(),
        risk=RiskLevel.MEDIUM,
        reason="test",
    )
    claimed = application.approvals.claim(pending.id, "admin", True)
    assert claimed is not None
    recoverable = application.approvals.list_approved_without_result()
    assert [item[0] for item in recoverable] == [pending.id]
    application.approvals.store_result(pending.id, {"ok": True})
    assert application.approvals.list_approved_without_result() == []
