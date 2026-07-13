from __future__ import annotations

import json
from collections import deque

import pytest

from jarvis_home.integrations.home_assistant import HomeAssistantError
from jarvis_home.integrations.home_assistant_ws import HomeAssistantWebSocketClient


class FakeWebSocket:
    def __init__(self, responses: list[dict]):
        self.responses = deque(json.dumps(item) for item in responses)
        self.sent: list[dict] = []

    async def recv(self) -> str:
        return self.responses.popleft()

    async def send(self, value: str) -> None:
        self.sent.append(json.loads(value))


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket):
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def test_websocket_url_preserves_reverse_proxy_base_path() -> None:
    client = HomeAssistantWebSocketClient("https://example.test/home/", "token")
    assert client.websocket_url == "wss://example.test/home/api/websocket"


def test_websocket_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="Credentials"):
        HomeAssistantWebSocketClient("http://user:pass@example.test", "token")


@pytest.mark.asyncio
async def test_snapshot_uses_one_authenticated_registry_session(monkeypatch) -> None:
    websocket = FakeWebSocket(
        [
            {"type": "auth_required", "ha_version": "2026.7.0"},
            {"type": "auth_ok", "ha_version": "2026.7.0"},
            {"id": 1, "type": "result", "success": True, "result": [{"area_id": "study"}]},
            {"id": 2, "type": "result", "success": True, "result": [{"id": "device-1"}]},
            {
                "id": 3,
                "type": "result",
                "success": True,
                "result": [{"entity_id": "light.study"}],
            },
            {
                "id": 4,
                "type": "result",
                "success": True,
                "result": [{"entity_id": "light.study", "state": "on"}],
            },
        ]
    )
    monkeypatch.setattr(
        "jarvis_home.integrations.home_assistant_ws.connect",
        lambda *args, **kwargs: FakeConnection(websocket),
    )
    client = HomeAssistantWebSocketClient("http://homeassistant.local:8123", "secret-token")

    snapshot = await client.fetch_snapshot()

    assert snapshot.areas == [{"area_id": "study"}]
    assert snapshot.devices == [{"id": "device-1"}]
    assert snapshot.entities == [{"entity_id": "light.study"}]
    assert snapshot.states == [{"entity_id": "light.study", "state": "on"}]
    assert websocket.sent == [
        {"type": "auth", "access_token": "secret-token"},
        {"id": 1, "type": "config/area_registry/list"},
        {"id": 2, "type": "config/device_registry/list"},
        {"id": 3, "type": "config/entity_registry/list"},
        {"id": 4, "type": "get_states"},
    ]


@pytest.mark.asyncio
async def test_authentication_failure_does_not_expose_token(monkeypatch) -> None:
    websocket = FakeWebSocket(
        [
            {"type": "auth_required"},
            {"type": "auth_invalid", "message": "Invalid access token secret-token"},
        ]
    )
    monkeypatch.setattr(
        "jarvis_home.integrations.home_assistant_ws.connect",
        lambda *args, **kwargs: FakeConnection(websocket),
    )
    client = HomeAssistantWebSocketClient("http://homeassistant.local:8123", "secret-token")

    with pytest.raises(HomeAssistantError) as caught:
        await client.fetch_snapshot()
    assert "secret-token" not in str(caught.value)
