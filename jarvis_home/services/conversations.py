from __future__ import annotations

import json
import uuid
from typing import Any

from ..db import Database, utcnow


class ConversationService:
    def __init__(self, db: Database):
        self.db = db

    def ensure(self, conversation_id: str | None, first_message: str = "") -> str:
        if conversation_id:
            row = self.db.query_one("SELECT id FROM conversations WHERE id=?", (conversation_id,))
            if row:
                return conversation_id
        conversation_id = uuid.uuid4().hex
        now = utcnow()
        title = first_message.strip().replace("\n", " ")[:80]
        self.db.execute(
            "INSERT INTO conversations(id, title, created_at, updated_at) VALUES(?,?,?,?)",
            (conversation_id, title, now, now),
        )
        return conversation_id

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO messages(conversation_id, role, content, metadata_json, created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now, conversation_id),
            )

    def history(self, conversation_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            """
            SELECT role, content, metadata_json, created_at
            FROM messages WHERE conversation_id=?
            ORDER BY id DESC LIMIT ?
            """,
            (conversation_id, limit),
        )
        rows.reverse()
        for row in rows:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        return rows

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.query_all(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
