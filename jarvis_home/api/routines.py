from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..application import Application
from ..schemas import RoutineCreate, UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/routines", tags=["routines"])


@router.get("")
def list_routines(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.routines.list()


@router.post("")
def create_routine(
    payload: RoutineCreate,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict:
    try:
        routine = app.routines.create(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    app.audit.record(user.username, "routine.create", routine["id"], "success")
    return routine


@router.post("/{routine_id}/run")
async def run_routine(
    routine_id: str,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict:
    try:
        return await app.routines.run(routine_id, user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Routine not found") from exc


@router.delete("/{routine_id}")
def delete_routine(
    routine_id: str,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict[str, bool]:
    try:
        app.routines.get(routine_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Routine not found") from exc
    app.routines.delete(routine_id)
    app.audit.record(user.username, "routine.delete", routine_id, "success")
    return {"ok": True}
