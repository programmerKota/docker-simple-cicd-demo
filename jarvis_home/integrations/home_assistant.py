from __future__ import annotations

from typing import Any

import httpx


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def health(self) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "error": "Home Assistant token is not configured"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/", headers=self.headers)
                response.raise_for_status()
                return {"ok": True, "message": response.json().get("message", "API reachable")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def list_states(self, domain: str | None = None) -> list[dict[str, Any]]:
        self._require_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/states", headers=self.headers)
            response.raise_for_status()
            states = response.json()
            if domain:
                prefix = f"{domain}."
                states = [item for item in states if str(item.get("entity_id", "")).startswith(prefix)]
            return [self._compact_state(item) for item in states]

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        self._require_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/states/{entity_id}", headers=self.headers)
            if response.status_code == 404:
                raise HomeAssistantError(f"Unknown Home Assistant entity: {entity_id}")
            response.raise_for_status()
            return self._compact_state(response.json())

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_token()
        payload = dict(service_data or {})
        if target:
            # Home Assistant REST expects target selectors (for example entity_id)
            # as service_data fields rather than a nested WebSocket-style envelope.
            payload.update(target)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return [self._compact_state(item) for item in data if isinstance(item, dict)]

    def _require_token(self) -> None:
        if not self.token:
            raise HomeAssistantError("Home Assistant token is not configured")

    @staticmethod
    def _compact_state(item: dict[str, Any]) -> dict[str, Any]:
        attributes = item.get("attributes") or {}
        allowed_attributes = {
            key: value
            for key, value in attributes.items()
            if key
            in {
                "friendly_name",
                "unit_of_measurement",
                "device_class",
                "temperature",
                "current_temperature",
                "hvac_action",
                "brightness",
                "media_title",
                "media_artist",
                "battery_level",
            }
        }
        return {
            "entity_id": item.get("entity_id"),
            "state": item.get("state"),
            "attributes": allowed_attributes,
            "last_changed": item.get("last_changed"),
        }
