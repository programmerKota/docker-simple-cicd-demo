from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jarvis_home.config import Settings
from jarvis_home.main import create_app
from jarvis_home.schemas import RiskLevel, ToolInvocation, UserContext

DATABASE_URL = os.environ.get("TEST_DBOS_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DBOS_DATABASE_URL is not configured")


class FakeHomeAssistant:
    def __init__(self) -> None:
        self.state = "on"
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def health(self) -> dict[str, Any]:
        return {"ok": True}

    async def list_states(self, domain: str | None = None) -> list[dict[str, Any]]:
        return [await self.get_state("light.study")]

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        return {
            "entity_id": entity_id,
            "state": self.state,
            "attributes": {"friendly_name": "Study"},
        }

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        assert domain == "light"
        assert service in {"turn_on", "turn_off"}
        entity_id = str((target or {}).get("entity_id"))
        self.calls.append((domain, service, {"entity_id": entity_id, **(service_data or {})}))
        self.state = "on" if service == "turn_on" else "off"
        return [await self.get_state(entity_id)]


def integration_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        env="test",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "backups",
        master_key_file=tmp_path / "master.key",
        session_secret="integration-session-secret-that-is-long-enough-123456",  # noqa: S106
        admin_username="admin",
        admin_password="integration-password",  # noqa: S106
        trusted_hosts="testserver,localhost,127.0.0.1",
        allowed_origins="http://testserver",
        dbos_database_url=DATABASE_URL,
        state_witness_attempts=3,
        state_witness_interval_seconds=0.1,
        ollama_url="http://127.0.0.1:9",
        home_assistant_url="http://127.0.0.1:9",
    )
    settings.ensure_directories()
    return settings


def test_approved_light_action_is_durable_verified_and_not_replayed(tmp_path: Path) -> None:
    app = create_app(integration_settings(tmp_path))
    jarvis = app.state.jarvis
    fake_home = FakeHomeAssistant()
    jarvis.get_home_assistant_client = lambda: fake_home

    pending = jarvis.approvals.create(
        UserContext(username="admin", role="owner"),
        ToolInvocation(
            tool_name="home.call_service",
            arguments={
                "domain": "light",
                "service": "turn_off",
                "service_data": {},
                "target": {"entity_id": "light.study"},
            },
        ),
        RiskLevel.MEDIUM,
        "integration test",
    )

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "integration-password"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        approved = client.post(
            f"/api/approvals/{pending.id}",
            headers=headers,
            json={"approved": True},
        )
        assert approved.status_code == 200
        body = approved.json()
        assert body["ok"] is True
        assert body["metadata"]["durable"] is True
        assert body["metadata"]["state_verified"] is True
        assert body["metadata"]["workflow_id"] == f"approval:{pending.id}"
        assert body["content"]["state_witness"]["observed"]["state"] == "off"
        assert len(fake_home.calls) == 1

        duplicate = client.post(
            f"/api/approvals/{pending.id}",
            headers=headers,
            json={"approved": True},
        )
        assert duplicate.status_code == 409
        assert len(fake_home.calls) == 1
