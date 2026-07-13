from __future__ import annotations

import os
from pathlib import Path

import nats
import pytest

from jarvis_home.config import Settings
from jarvis_home.db import Database
from jarvis_home.services.event_outbox import EventOutbox, JetStreamRelay

NATS_URL = os.environ.get("TEST_NATS_URL", "")
NATS_TOKEN = os.environ.get("TEST_NATS_TOKEN", "")
pytestmark = pytest.mark.skipif(not NATS_URL, reason="TEST_NATS_URL is not configured")


def integration_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        env="test",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "backups",
        master_key_file=tmp_path / "master.key",
        session_secret="integration-session-secret-that-is-long-enough-123456",  # noqa: S106
        admin_password="integration-password",  # noqa: S106
        nats_url=NATS_URL,
        nats_token=NATS_TOKEN,
        nats_stream="JARVIS_TEST_EVENTS",
        nats_connect_timeout_seconds=5,
        nats_publish_timeout_seconds=5,
    )
    settings.ensure_directories()
    return settings


@pytest.mark.asyncio
async def test_outbox_replays_after_restart_without_duplicating_stream_message(tmp_path: Path) -> None:
    settings = integration_settings(tmp_path)
    db = Database(settings.database_path)
    db.initialize()
    outbox = EventOutbox(db)
    relay = JetStreamRelay(settings, outbox)

    event_id = "approval:integration:completed"
    assert outbox.append(
        event_id,
        "home.action.completed.v1",
        {"workflow_id": "approval:integration", "state_verified": True},
    )
    assert await relay.flush_once() == 1
    assert outbox.stats() == {"pending": 0, "published": 1}

    # Simulate a local crash after the server acknowledged the event but before
    # local acknowledgement state was durable. The same event ID is replayed.
    db.execute(
        "UPDATE event_outbox SET published_at=NULL, stream_sequence=NULL WHERE event_id=?",
        (event_id,),
    )
    assert await relay.flush_once() == 1
    assert outbox.stats() == {"pending": 0, "published": 1}

    nc = await nats.connect(servers=[NATS_URL], token=NATS_TOKEN)
    try:
        info = await nc.jetstream().stream_info(settings.nats_stream)
        assert info.state.messages == 1
    finally:
        await nc.close()
        await relay.stop()
