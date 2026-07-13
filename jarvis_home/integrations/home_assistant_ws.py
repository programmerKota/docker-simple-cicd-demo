from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .home_assistant import HomeAssistantError


@dataclass(frozen=True)
class HomeAssistantSnapshot:
    captured_at: str
    areas: list[dict[str, Any]]
    devices: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    states: list[dict[str, Any]]


class HomeAssistantWebSocketClient:
    """Fetch a consistent-enough registry snapshot over one authenticated session.

    Home Assistant does not expose a multi-registry transaction. Keeping all
    commands on one short-lived connection minimizes drift, and the twin layer
    publishes the snapshot only after every command succeeds.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        open_timeout: float = 10.0,
        command_timeout: float = 20.0,
        max_message_bytes: int = 8_000_000,
    ):
        self.websocket_url = self._to_websocket_url(base_url)
        self.token = token
        self.open_timeout = open_timeout
        self.command_timeout = command_timeout
        self.max_message_bytes = max_message_bytes

    async def fetch_snapshot(self) -> HomeAssistantSnapshot:
        if not self.token:
            raise HomeAssistantError("Home Assistant token is not configured")
        try:
            async with connect(
                self.websocket_url,
                open_timeout=self.open_timeout,
                close_timeout=5,
                max_size=self.max_message_bytes,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                required = await self._receive_json(websocket)
                if required.get("type") != "auth_required":
                    raise HomeAssistantError("Unexpected Home Assistant WebSocket handshake")
                await websocket.send(json.dumps({"type": "auth", "access_token": self.token}))
                authentication = await self._receive_json(websocket)
                if authentication.get("type") != "auth_ok":
                    raise HomeAssistantError("Home Assistant WebSocket authentication failed")

                message_id = 1
                areas = await self._command(websocket, message_id, "config/area_registry/list")
                message_id += 1
                devices = await self._command(websocket, message_id, "config/device_registry/list")
                message_id += 1
                entities = await self._command(websocket, message_id, "config/entity_registry/list")
                message_id += 1
                states = await self._command(websocket, message_id, "get_states")
        except HomeAssistantError:
            raise
        except (OSError, TimeoutError, WebSocketException, json.JSONDecodeError) as exc:
            raise HomeAssistantError("Home Assistant WebSocket snapshot failed") from exc

        return HomeAssistantSnapshot(
            captured_at=datetime.now(UTC).isoformat(),
            areas=self._require_object_list(areas, "area registry"),
            devices=self._require_object_list(devices, "device registry"),
            entities=self._require_object_list(entities, "entity registry"),
            states=self._require_object_list(states, "states"),
        )

    async def _command(self, websocket: Any, message_id: int, command_type: str) -> Any:
        await websocket.send(json.dumps({"id": message_id, "type": command_type}))
        while True:
            response = await self._receive_json(websocket)
            if response.get("id") != message_id:
                continue
            if response.get("type") != "result" or response.get("success") is not True:
                raise HomeAssistantError(f"Home Assistant command failed: {command_type}")
            return response.get("result")

    async def _receive_json(self, websocket: Any) -> dict[str, Any]:
        raw = await asyncio.wait_for(websocket.recv(), timeout=self.command_timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise HomeAssistantError("Invalid Home Assistant WebSocket message")
        return payload

    @staticmethod
    def _require_object_list(value: Any, name: str) -> list[dict[str, Any]]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise HomeAssistantError(f"Invalid Home Assistant {name} response")
        return value

    @staticmethod
    def _to_websocket_url(base_url: str) -> str:
        parsed = urlsplit(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Home Assistant URL must use http or https")
        if parsed.username or parsed.password:
            raise ValueError("Credentials must not be embedded in Home Assistant URL")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        base_path = parsed.path.rstrip("/")
        return urlunsplit((scheme, parsed.netloc, f"{base_path}/api/websocket", "", ""))
