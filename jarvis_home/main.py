from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api import approvals, audit, auth, backup, chat, home, memory, routines, system, voice
from .application import Application
from .config import Settings, get_settings


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        request_id = uuid.uuid4().hex

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), geolocation=(), payment=()"),
                    (
                        b"content-security-policy",
                        (
                            b"default-src 'self'; script-src 'self'; style-src 'self'; "
                            b"img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
                            b"object-src 'none'; frame-ancestors 'none'"
                        ),
                    ),
                ]
                message.setdefault("headers", []).extend(extra)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    errors = settings.validate_production()
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))

    jarvis = Application(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await jarvis.routines.start()
        jarvis.audit.record("system", "application.start", "jarvis", "success")
        try:
            yield
        finally:
            await jarvis.routines.stop()
            jarvis.audit.record("system", "application.stop", "jarvis", "success")

    app = FastAPI(
        title="JARVIS Home",
        version="1.0.0",
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.jarvis = jarvis
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.add_middleware(RequestSecurityMiddleware, max_bytes=settings.max_request_bytes)

    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(system.router)
    app.include_router(approvals.router)
    app.include_router(memory.router)
    app.include_router(routines.router)
    app.include_router(audit.router)
    app.include_router(home.router)
    app.include_router(backup.router)
    app.include_router(voice.router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
app = create_app()
