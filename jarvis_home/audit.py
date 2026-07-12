from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import Database, utcnow
from .security import redact


class AuditLog:
    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> str:
        previous = self.db.query_one("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")
        previous_hash = previous["entry_hash"] if previous else "GENESIS"
        timestamp = utcnow()
        safe_details = redact(details or {})
        canonical = json.dumps(
            {
                "timestamp": timestamp,
                "actor": actor,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "details": safe_details,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.db.execute(
            """
            INSERT INTO audit_log(timestamp, actor, action, resource, outcome,
                                  details_json, previous_hash, entry_hash)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                timestamp,
                actor,
                action,
                resource,
                outcome,
                json.dumps(safe_details, ensure_ascii=False),
                previous_hash,
                entry_hash,
            ),
        )
        return entry_hash

    def verify_chain(self) -> tuple[bool, int | None]:
        rows = self.db.query_all("SELECT * FROM audit_log ORDER BY id")
        previous_hash = "GENESIS"
        for row in rows:
            canonical = json.dumps(
                {
                    "timestamp": row["timestamp"],
                    "actor": row["actor"],
                    "action": row["action"],
                    "resource": row["resource"],
                    "outcome": row["outcome"],
                    "details": json.loads(row["details_json"]),
                    "previous_hash": previous_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or row["entry_hash"] != expected:
                return False, int(row["id"])
            previous_hash = row["entry_hash"]
        return True, None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query_all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        for row in rows:
            row["details"] = json.loads(row.pop("details_json"))
        return rows
