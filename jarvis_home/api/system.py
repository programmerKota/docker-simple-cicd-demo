from __future__ import annotations

import json
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..application import Application
from ..schemas import IntegrationSettingsUpdate, UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api", tags=["system"])


def _validate_local_service_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="URL must use http or https")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Credentials must not be embedded in URLs")
    return value.rstrip("/")


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.get("/status")
async def status(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> dict:
    return await app.status()


@router.get("/settings/integrations")
def integration_settings(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> dict:
    return {
        "ollama_url": app.db.get_setting("ollama_url", app.settings.ollama_url),
        "ollama_model": app.db.get_setting("ollama_model", app.settings.ollama_model),
        "home_assistant_url": app.db.get_setting("home_assistant_url", app.settings.home_assistant_url),
        "home_assistant_token_configured": bool(app.secrets.get("home_assistant_token", "")),
    }


@router.put("/settings/integrations")
def update_integration_settings(
    payload: IntegrationSettingsUpdate,
    app: Application = Depends(get_application),
    user: UserContext = Depends(current_user),
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "ollama_url" in changes and changes["ollama_url"] is not None:
        app.db.set_setting("ollama_url", _validate_local_service_url(changes["ollama_url"]))
    if "ollama_model" in changes and changes["ollama_model"] is not None:
        model = changes["ollama_model"].strip()
        if not model or len(model) > 200:
            raise HTTPException(status_code=422, detail="Invalid model name")
        app.db.set_setting("ollama_model", model)
    if "home_assistant_url" in changes and changes["home_assistant_url"] is not None:
        app.db.set_setting("home_assistant_url", _validate_local_service_url(changes["home_assistant_url"]))
    if "home_assistant_token" in changes and changes["home_assistant_token"] is not None:
        token = changes["home_assistant_token"].strip()
        if token:
            app.secrets.set("home_assistant_token", token)
        else:
            app.secrets.delete("home_assistant_token")
    app.refresh_agent_clients()
    app.audit.record(user.username, "settings.update", "integrations", "success", {"keys": list(changes)})
    return integration_settings(app, user)


@router.get("/tools")
def tools(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> list[str]:
    return app.registry.names()


@router.get("/events")
async def events(
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        async for event in app.events.subscribe():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
