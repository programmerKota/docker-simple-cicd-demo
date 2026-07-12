from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..application import Application
from ..schemas import UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("/entities")
async def entities(
    domain: str | None = Query(default=None, max_length=100),
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return await app.get_home_assistant_client().list_states(domain)


@router.get("/entities/{entity_id}")
async def entity(
    entity_id: str,
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> dict:
    return await app.get_home_assistant_client().get_state(entity_id)
