from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]

from ..db import Database, utcnow
from ..schemas import RoutineCreate, ToolInvocation, UserContext
from ..tool_registry import ToolRegistry
from .events import EventBus


class RoutineService:
    def __init__(self, db: Database, registry: ToolRegistry, events: EventBus):
        self.db = db
        self.registry = registry
        self.events = events
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def create(self, routine: RoutineCreate) -> dict[str, Any]:
        routine_id = uuid.uuid4().hex
        now = utcnow()
        next_run = self._next_run(routine.cron) if routine.enabled and routine.cron else None
        self.db.execute(
            """
            INSERT INTO routines(id, name, description, cron, enabled, steps_json,
                                 next_run_at, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                routine_id,
                routine.name,
                routine.description,
                routine.cron,
                int(routine.enabled),
                json.dumps([step.model_dump() for step in routine.steps], ensure_ascii=False),
                next_run,
                now,
                now,
            ),
        )
        return self.get(routine_id)

    def get(self, routine_id: str) -> dict[str, Any]:
        row = self.db.query_one("SELECT * FROM routines WHERE id=?", (routine_id,))
        if not row:
            raise KeyError(routine_id)
        return self._inflate(row)

    def list(self) -> list[dict[str, Any]]:
        return [self._inflate(row) for row in self.db.query_all("SELECT * FROM routines ORDER BY name")]

    def delete(self, routine_id: str) -> None:
        self.db.execute("DELETE FROM routines WHERE id=?", (routine_id,))

    async def run(self, routine_id: str, user: UserContext) -> dict[str, Any]:
        routine = self.get(routine_id)
        results: list[dict[str, Any]] = []
        await self.events.publish("routine.started", {"id": routine_id, "name": routine["name"]})
        for index, step in enumerate(routine["steps"]):
            result = await self.registry.invoke(
                ToolInvocation(tool_name=step["tool"], arguments=step.get("arguments", {})),
                user,
            )
            results.append({"index": index, "tool": step["tool"], **result.model_dump()})
            if not result.ok and not step.get("continue_on_error", False):
                break
        now = utcnow()
        next_run = self._next_run(routine["cron"]) if routine["enabled"] and routine["cron"] else None
        self.db.execute(
            "UPDATE routines SET last_run_at=?, next_run_at=?, updated_at=? WHERE id=?",
            (now, next_run, now, routine_id),
        )
        payload = {"id": routine_id, "name": routine["name"], "results": results}
        await self.events.publish("routine.finished", payload)
        return payload

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._scheduler_loop(), name="jarvis-routine-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _scheduler_loop(self) -> None:
        owner = UserContext(username="scheduler", role="owner", source="scheduler")
        while not self._stop.is_set():
            now = utcnow()
            due = self.db.query_all(
                """
                SELECT id FROM routines
                WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=?
                ORDER BY next_run_at LIMIT 10
                """,
                (now,),
            )
            for row in due:
                try:
                    await self.run(row["id"], owner)
                except Exception as exc:
                    await self.events.publish("routine.error", {"id": row["id"], "error": str(exc)})
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=20)
            except TimeoutError:
                continue

    @staticmethod
    def _next_run(expression: str | None) -> str | None:
        if not expression:
            return None
        if not croniter.is_valid(expression):
            raise ValueError("Invalid cron expression")
        next_time: datetime = croniter(expression, datetime.now(UTC)).get_next(datetime)
        return next_time.isoformat()

    @staticmethod
    def _inflate(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["enabled"] = bool(row["enabled"])
        row["steps"] = json.loads(row.pop("steps_json"))
        return row
