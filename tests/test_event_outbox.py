from __future__ import annotations

import pytest

from jarvis_home.services.event_outbox import EventOutbox


def test_outbox_append_is_idempotent(application) -> None:
    outbox = EventOutbox(application.db)
    payload = {"workflow_id": "approval:1", "state": "off"}

    assert outbox.append("approval:1:completed", "home.action.completed.v1", payload) is True
    assert outbox.append("approval:1:completed", "home.action.completed.v1", payload) is False

    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0]["event_id"] == "approval:1:completed"
    assert pending[0]["payload"] == payload


def test_outbox_tracks_failure_then_publication(application) -> None:
    outbox = EventOutbox(application.db)
    outbox.append("event-1", "home.plan.authorized.v1", {"x": 1})
    outbox.mark_failed("event-1", "temporary failure")

    pending = outbox.pending()
    assert pending[0]["publish_attempts"] == 1
    assert outbox.stats() == {"pending": 1, "published": 0}

    outbox.mark_published("event-1", 42)
    assert outbox.pending() == []
    assert outbox.stats() == {"pending": 0, "published": 1}


def test_outbox_rejects_non_household_subject(application) -> None:
    outbox = EventOutbox(application.db)
    with pytest.raises(ValueError, match="home"):
        outbox.append("event-1", "random.subject", {})
