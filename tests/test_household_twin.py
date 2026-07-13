from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from jarvis_home.integrations.home_assistant import HomeAssistantError
from jarvis_home.integrations.home_assistant_ws import HomeAssistantSnapshot
from jarvis_home.services.household_twin import HouseholdTwin


class SnapshotClient:
    def __init__(self, snapshot: HomeAssistantSnapshot):
        self.snapshot = snapshot
        self.error: Exception | None = None

    async def fetch_snapshot(self) -> HomeAssistantSnapshot:
        if self.error:
            raise self.error
        return self.snapshot


def sample_snapshot(captured_at: str = "2026-07-13T10:00:00+00:00") -> HomeAssistantSnapshot:
    return HomeAssistantSnapshot(
        captured_at=captured_at,
        areas=[
            {"area_id": "study", "name": "書斎"},
            {"area_id": "living", "name": "リビング"},
        ],
        devices=[
            {
                "id": "device-lamp",
                "area_id": "study",
                "name": "Desk Lamp",
                "name_by_user": None,
                "manufacturer": "Example",
                "model": "L1",
            },
            {
                "id": "device-sensor",
                "area_id": "living",
                "name": "Environment Sensor",
                "name_by_user": None,
            },
        ],
        entities=[
            {
                "entity_id": "light.study_lamp",
                "device_id": "device-lamp",
                "area_id": None,
                "platform": "hue",
                "disabled_by": None,
                "name": None,
                "original_name": "Study Lamp",
            },
            {
                "entity_id": "sensor.temperature",
                "device_id": "device-sensor",
                "area_id": "study",
                "platform": "mqtt",
                "disabled_by": None,
                "name": "移動温度計",
                "original_name": "Temperature",
            },
        ],
        states=[
            {
                "entity_id": "light.study_lamp",
                "state": "on",
                "last_changed": "2026-07-13T09:59:00+00:00",
                "attributes": {"friendly_name": "書斎ライト", "brightness": 180},
            },
            {
                "entity_id": "sensor.temperature",
                "state": "24.2",
                "last_changed": "2026-07-13T09:58:00+00:00",
                "attributes": {
                    "friendly_name": "温度",
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                },
            },
        ],
    )


def make_twin(tmp_path: Path, snapshot: HomeAssistantSnapshot | None = None) -> tuple[HouseholdTwin, SnapshotClient]:
    client = SnapshotClient(snapshot or sample_snapshot())
    return HouseholdTwin(tmp_path / "twin", client, refresh_interval_seconds=60), client


def test_twin_builds_room_device_point_relationships(tmp_path: Path) -> None:
    twin, _ = make_twin(tmp_path)
    summary = twin.replace_snapshot(sample_snapshot())

    assert summary["areas"] == 2
    assert summary["devices"] == 2
    assert summary["entities"] == 2
    assert summary["sensors"] == 1

    lights = twin.find_entities(room="書斎", domain="light")
    assert [entity["entity_id"] for entity in lights] == ["light.study_lamp"]
    assert lights[0]["device_name"] == "Desk Lamp"

    sensor = twin.explain_entity("sensor.temperature")
    # Explicit entity area wins over the device's area.
    assert sensor["area_name"] == "書斎"
    assert sensor["device_name"] == "Environment Sensor"
    assert sensor["unit"] == "°C"
    assert "書斎" in sensor["explanation"]


def test_replacement_removes_stale_entities_and_keeps_stable_hash(tmp_path: Path) -> None:
    twin, _ = make_twin(tmp_path)
    first = sample_snapshot()
    twin.replace_snapshot(first)
    first_graph = twin.status()["active_graph"]

    same_content_later = replace(first, captured_at="2026-07-13T10:05:00+00:00")
    twin.replace_snapshot(same_content_later)
    assert twin.status()["active_graph"] == first_graph
    assert twin.status()["last_successful_sync"] == "2026-07-13T10:05:00+00:00"

    reduced = HomeAssistantSnapshot(
        captured_at="2026-07-13T10:06:00+00:00",
        areas=first.areas,
        devices=[first.devices[0]],
        entities=[first.entities[0]],
        states=[first.states[0]],
    )
    twin.replace_snapshot(reduced)
    assert twin.summary()["entities"] == 1
    assert twin.find_entities(domain="sensor") == []
    with pytest.raises(KeyError):
        twin.explain_entity("sensor.temperature")


@pytest.mark.asyncio
async def test_sync_failure_preserves_last_good_snapshot(tmp_path: Path) -> None:
    twin, client = make_twin(tmp_path)
    await twin.ensure_fresh()
    active_graph = twin.status()["active_graph"]

    twin.refresh_interval_seconds = -1
    client.error = HomeAssistantError("temporary failure")
    status = await twin.ensure_fresh()

    assert status["ready"] is True
    assert status["active_graph"] == active_graph
    assert status["stale"] is True
    assert status["last_error"] == "temporary failure"
    assert twin.find_entities(domain="light")[0]["entity_id"] == "light.study_lamp"


@pytest.mark.asyncio
async def test_first_sync_failure_fails_closed(tmp_path: Path) -> None:
    twin, client = make_twin(tmp_path)
    client.error = HomeAssistantError("offline")
    with pytest.raises(HomeAssistantError, match="No usable"):
        await twin.ensure_fresh()
