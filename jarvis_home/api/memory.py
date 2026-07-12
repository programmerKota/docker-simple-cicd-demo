from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..application import Application
from ..schemas import MemoryCreate, UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def search_memory(
    q: str = Query(default="", max_length=1000),
    limit: int = Query(default=20, ge=1, le=100),
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.memory.search(q, limit)


@router.post("")
def create_memory(
    payload: MemoryCreate,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict:
    result = app.memory.remember(payload.content, payload.kind, payload.importance, payload.tags)
    app.audit.record(user.username, "memory.create", str(result["id"]), "success")
    return result


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict[str, bool]:
    try:
        app.memory.get(memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    app.memory.delete(memory_id)
    app.audit.record(user.username, "memory.delete", str(memory_id), "success")
    return {"ok": True}
