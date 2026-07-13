from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import Settings
from ..db import Database, utcnow
from ..schemas import PendingApproval, RiskLevel, ToolInvocation, UserContext


class ApprovalError(RuntimeError):
    pass


class ApprovalService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def create(
        self,
        user: UserContext,
        invocation: ToolInvocation,
        risk: RiskLevel,
        reason: str,
    ) -> PendingApproval:
        approval_id = uuid.uuid4().hex
        expires = datetime.now(UTC) + timedelta(seconds=self.settings.approval_ttl_seconds)
        self.db.execute(
            """
            INSERT INTO approvals(id, username, tool_name, arguments_json, risk, reason,
                                  conversation_id, status, expires_at, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                approval_id,
                user.username,
                invocation.tool_name,
                json.dumps(invocation.arguments, ensure_ascii=False),
                risk.value,
                reason,
                invocation.conversation_id,
                "pending",
                expires.isoformat(),
                utcnow(),
            ),
        )
        return PendingApproval(
            id=approval_id,
            tool_name=invocation.tool_name,
            arguments=invocation.arguments,
            reason=reason,
            risk=risk,
            expires_at=expires.isoformat(),
            conversation_id=invocation.conversation_id,
        )

    def list_pending(self, username: str) -> list[PendingApproval]:
        now = utcnow()
        self.db.execute(
            "UPDATE approvals SET status='expired', decided_at=? WHERE status='pending' AND expires_at<?",
            (now, now),
        )
        rows = self.db.query_all(
            """
            SELECT * FROM approvals
            WHERE username=? AND status='pending'
            ORDER BY created_at DESC
            """,
            (username,),
        )
        return [self._to_model(row) for row in rows]

    def list_approved_without_result(self) -> list[tuple[str, str, ToolInvocation]]:
        rows = self.db.query_all(
            """
            SELECT id, username, tool_name, arguments_json, conversation_id
            FROM approvals
            WHERE status='approved' AND result_json IS NULL
            ORDER BY decided_at, created_at
            """
        )
        return [
            (
                row["id"],
                row["username"],
                ToolInvocation(
                    tool_name=row["tool_name"],
                    arguments=json.loads(row["arguments_json"]),
                    conversation_id=row["conversation_id"],
                ),
            )
            for row in rows
        ]

    def claim(self, approval_id: str, username: str, approved: bool) -> ToolInvocation | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not row:
                raise ApprovalError("Approval not found")
            data = dict(row)
            if data["username"] != username:
                raise ApprovalError("Approval belongs to another user")
            if data["status"] != "pending":
                raise ApprovalError(f"Approval is already {data['status']}")
            if datetime.fromisoformat(data["expires_at"]) < datetime.now(UTC):
                conn.execute(
                    "UPDATE approvals SET status='expired', decided_at=? WHERE id=?",
                    (utcnow(), approval_id),
                )
                raise ApprovalError("Approval expired")
            status = "approved" if approved else "rejected"
            conn.execute(
                "UPDATE approvals SET status=?, decided_at=? WHERE id=?",
                (status, utcnow(), approval_id),
            )
        if not approved:
            return None
        return ToolInvocation(
            tool_name=data["tool_name"],
            arguments=json.loads(data["arguments_json"]),
            conversation_id=data["conversation_id"],
        )

    def store_result(self, approval_id: str, result: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE approvals SET result_json=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), approval_id),
        )

    @staticmethod
    def _to_model(row: dict[str, Any]) -> PendingApproval:
        return PendingApproval(
            id=row["id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments_json"]),
            reason=row["reason"],
            risk=RiskLevel(row["risk"]),
            expires_at=row["expires_at"],
            conversation_id=row["conversation_id"],
        )
