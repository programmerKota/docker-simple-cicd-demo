from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .event_outbox import EventOutbox, JetStreamRelay

if TYPE_CHECKING:
    from ..application import Application

_OUTBOX_ATTRIBUTE = "_event_outbox"
_RELAY_ATTRIBUTE = "_jetstream_relay"


def get_event_outbox(application: Application) -> EventOutbox:
    existing = getattr(application, _OUTBOX_ATTRIBUTE, None)
    if existing is not None:
        return cast(EventOutbox, existing)
    outbox = EventOutbox(application.db)
    setattr(application, _OUTBOX_ATTRIBUTE, outbox)
    return outbox


def get_event_relay(application: Application) -> JetStreamRelay:
    existing = getattr(application, _RELAY_ATTRIBUTE, None)
    if existing is not None:
        return cast(JetStreamRelay, existing)
    relay = JetStreamRelay(application.settings, get_event_outbox(application))
    setattr(application, _RELAY_ATTRIBUTE, relay)
    return relay
