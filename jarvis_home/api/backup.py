from __future__ import annotations

from fastapi import APIRouter, Depends

from ..application import Application
from ..schemas import UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("")
def list_backups(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.backups.list()


@router.post("")
def create_backup(
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict:
    result = app.backups.create()
    app.audit.record(user.username, "backup.create", result["path"], "success")
    return result
