from __future__ import annotations

from fastapi import APIRouter, Depends

from ..application import Application
from ..schemas import ChatRequest, ChatResponse, UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> ChatResponse:
    return await app.agent.chat(payload, user)


@router.get("/conversations")
def conversations(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.conversations.list()


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: str,
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[dict]:
    return app.conversations.history(conversation_id, limit=200)
