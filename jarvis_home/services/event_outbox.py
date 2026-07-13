from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

import nats
from nats.aio.client import Client as NATS
from nats.js.errors import NotFoundError

from ..config import Settings
from ..db import Database, utcnow

logger = logging.getLogger(__name__)


class EventOutbox:
    """Durable local source of truth for events destined for JetStream."""

    def __init__(self, db: Database):
        self.db = db

    def append(self, event_id: str, subject: str, payload: dict[str, Any]) -> bool:
        if not event_id.strip():
            raise ValueError("event_id is required")
        if not subject.startswith("home."):
            raise ValueError("Only versioned home.* subjects are accepted")
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO event_outbox(
                    event_id, subject, payload_json, created_at
                ) VALUES(?,?,?,?)
                """,
                (event_id, subject, json.dumps(payload, ensure_ascii=False, sort_keys=True), utcnow()),
            )
            return cursor.rowcount == 1

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            """
            SELECT event_id, subject, payload_json, created_at, publish_attempts
            FROM event_outbox
            WHERE published_at IS NULL
            ORDER BY created_at, event_id
            LIMIT ?
            """,
            (min(max(limit, 1), 1000),),
        )
        for row in rows:
            row["payload"] = json.loads(row.pop("payload_json"))
        return rows

    def mark_published(self, event_id: str, stream_sequence: int) -> None:
        self.db.execute(
            """
            UPDATE event_outbox
            SET published_at=?, stream_sequence=?, last_error=NULL,
                publish_attempts=publish_attempts+1
            WHERE event_id=? AND published_at IS NULL
            """,
            (utcnow(), stream_sequence, event_id),
        )

    def mark_failed(self, event_id: str, error: str) -> None:
        self.db.execute(
            """
            UPDATE event_outbox
            SET publish_attempts=publish_attempts+1, last_error=?
            WHERE event_id=? AND published_at IS NULL
            """,
            (error[:2000], event_id),
        )

    def stats(self) -> dict[str, int]:
        row = self.db.query_one(
            """
            SELECT
                SUM(CASE WHEN published_at IS NULL THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN published_at IS NOT NULL THEN 1 ELSE 0 END) AS published
            FROM event_outbox
            """
        ) or {"pending": 0, "published": 0}
        return {"pending": int(row["pending"] or 0), "published": int(row["published"] or 0)}


class JetStreamRelay:
    """Best-effort relay backed by a durable SQLite outbox.

    NATS availability never determines whether a physical action is accepted or
    completed. Events are committed locally first and retried until JetStream
    acknowledges them. The event ID is sent as Nats-Msg-Id for server-side
    duplicate suppression.
    """

    def __init__(self, settings: Settings, outbox: EventOutbox):
        self.settings = settings
        self.outbox = outbox
        self._nc: NATS | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ready = False
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.event_stream_enabled

    async def start(self) -> None:
        if not self.enabled or (self._task and not self._task.done()):
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="jarvis-event-outbox-relay")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._nc and not self._nc.is_closed:
            with suppress(Exception):
                await self._nc.drain()
        self._nc = None
        self._ready = False

    async def flush_once(self) -> int:
        if not self.enabled:
            return 0
        await self._ensure_connection()
        if self._nc is None:
            return 0
        js = self._nc.jetstream()
        published = 0
        for event in self.outbox.pending(self.settings.nats_batch_size):
            try:
                payload = json.dumps(
                    {
                        "event_id": event["event_id"],
                        "subject": event["subject"],
                        "created_at": event["created_at"],
                        "data": event["payload"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                ack = await js.publish(
                    event["subject"],
                    payload,
                    stream=self.settings.nats_stream,
                    headers={"Nats-Msg-Id": event["event_id"]},
                    timeout=self.settings.nats_publish_timeout_seconds,
                )
                self.outbox.mark_published(event["event_id"], int(ack.seq))
                published += 1
            except Exception as exc:
                self.outbox.mark_failed(event["event_id"], str(exc))
                self._last_error = str(exc)
                self._ready = False
                await self._close_connection()
                break
        return published

    async def status(self) -> dict[str, Any]:
        stats = self.outbox.stats()
        return {
            "enabled": self.enabled,
            "ready": self._ready,
            "pending": stats["pending"],
            "published": stats["published"],
            "last_error": self._last_error,
        }

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.flush_once()
            except Exception as exc:
                self._last_error = str(exc)
                self._ready = False
                logger.warning("JetStream relay unavailable: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.nats_flush_interval_seconds
                )
            except TimeoutError:
                continue

    async def _ensure_connection(self) -> None:
        if self._nc and self._nc.is_connected:
            return
        await self._close_connection()
        self._nc = await nats.connect(
            servers=[self.settings.nats_url],
            token=self.settings.nats_token,
            name="jarvis-home-event-relay",
            connect_timeout=self.settings.nats_connect_timeout_seconds,
            allow_reconnect=True,
            max_reconnect_attempts=-1,
            reconnect_time_wait=1,
        )
        js = self._nc.jetstream()
        try:
            await js.stream_info(self.settings.nats_stream)
        except NotFoundError:
            await js.add_stream(
                name=self.settings.nats_stream,
                subjects=["home.>"],
                duplicate_window=self.settings.nats_duplicate_window_seconds,
            )
        self._ready = True
        self._last_error = None

    async def _close_connection(self) -> None:
        if self._nc and not self._nc.is_closed:
            with suppress(Exception):
                await self._nc.close()
        self._nc = None
