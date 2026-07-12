from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from ..db import Database, utcnow


class EventBus:
    def __init__(self, db: Database):
        self.db = db
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, "payload": payload, "created_at": utcnow()}
        self.db.execute(
            "INSERT INTO events(event_type, payload_json, created_at) VALUES(?,?,?)",
            (event_type, json.dumps(payload, ensure_ascii=False), event["created_at"]),
        )
        async with self._lock:
            stale: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    stale.append(queue)
            for queue in stale:
                self._subscribers.discard(queue)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
