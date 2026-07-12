from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..application import Application
from ..schemas import UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def recent_audit(
    limit: int = Query(default=100, ge=1, le=1000),
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.audit.list_recent(limit)


@router.get("/verify")
def verify_audit(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> dict:
    ok, broken_at = app.audit.verify_chain()
    return {"ok": ok, "broken_at": broken_at}
