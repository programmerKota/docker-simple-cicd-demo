from __future__ import annotations

import pytest

from jarvis_home.mcp_gateway import BearerTokenGate, HomeGateway


@pytest.mark.asyncio
async def test_mcp_light_action_creates_owner_approval_without_execution(application):
    gateway = HomeGateway(application)

    result = await gateway.propose_light_action(
        entity_id="light.living_room",
        action="turn_off",
    )

    assert result["ok"] is False
    assert result["error"] == "Approval required"
    assert result["metadata"]["decision"] == "approval"
    pending = application.approvals.list_pending(application.settings.admin_username)
    assert len(pending) == 1
    assert pending[0].tool_name == "home.call_service"
    assert pending[0].arguments["target"] == {"entity_id": "light.living_room"}


@pytest.mark.asyncio
async def test_mcp_gateway_rejects_non_light_write_capability(application):
    gateway = HomeGateway(application)

    with pytest.raises(ValueError, match="Only light entities"):
        await gateway.propose_light_action(
            entity_id="lock.front_door",
            action="turn_off",
        )


@pytest.mark.asyncio
async def test_mcp_gateway_validates_brightness(application):
    gateway = HomeGateway(application)

    with pytest.raises(ValueError, match="between 1 and 100"):
        await gateway.propose_light_action(
            entity_id="light.study",
            action="turn_on",
            brightness_pct=101,
        )


def test_mcp_bearer_gate_fails_closed_for_short_token():
    async def app(scope, receive, send):  # pragma: no cover - constructor fails first
        return None

    with pytest.raises(RuntimeError, match="at least 32"):
        BearerTokenGate(app, "too-short")
