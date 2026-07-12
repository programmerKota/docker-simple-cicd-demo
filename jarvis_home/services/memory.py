from __future__ import annotations

import json
from typing import Any

from ..db import Database, utcnow


def _fts_query(text: str) -> str:
    terms = [part.strip('"*()') for part in text.replace("'", " ").split() if part.strip()]
    return " OR ".join(f'"{term}"' for term in terms[:12])


class MemoryService:
    def __init__(self, db: Database):
        self.db = db

    def remember(
        self,
        content: str,
        kind: str = "note",
        importance: int = 5,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        now = utcnow()
        memory_id = self.db.execute(
            """
            INSERT INTO memories(content, kind, importance, tags_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (
                content.strip(),
                kind,
                max(1, min(10, int(importance))),
                json.dumps(tags or [], ensure_ascii=False),
                now,
                now,
            ),
        )
        return self.get(memory_id)

    def get(self, memory_id: int) -> dict[str, Any]:
        row = self.db.query_one("SELECT * FROM memories WHERE id=?", (memory_id,))
        if not row:
            raise KeyError(memory_id)
        row["tags"] = json.loads(row.pop("tags_json"))
        return row

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            rows = self.db.query_all(
                "SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,),
            )
        else:
            fts = _fts_query(query)
            if not fts:
                return []
            rows = self.db.query_all(
                """
                SELECT m.*, bm25(memories_fts) AS rank
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.rowid
                WHERE memories_fts MATCH ?
                ORDER BY rank, m.importance DESC
                LIMIT ?
                """,
                (fts, limit),
            )
            # unicode61 does not segment Japanese reliably. Preserve FTS ranking for
            # languages with spaces, then use a deterministic substring fallback.
            if not rows:
                rows = self.db.query_all(
                    """
                    SELECT * FROM memories
                    WHERE content LIKE ? OR tags_json LIKE ?
                    ORDER BY importance DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", limit),
                )
        for row in rows:
            row["tags"] = json.loads(row.pop("tags_json"))
        return rows

    def delete(self, memory_id: int) -> None:
        self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))

    def build_context(self, query: str, limit: int = 6) -> str:
        memories = self.search(query, limit=limit)
        if not memories:
            return ""
        return "\n".join(f"- [{item['kind']}; importance={item['importance']}] {item['content']}" for item in memories)
