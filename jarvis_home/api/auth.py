from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..application import Application
from ..schemas import LoginRequest, LoginResponse, UserContext
from ..security import AuthError
from .deps import current_user, get_application

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, app: Application = Depends(get_application)) -> LoginResponse:
    identity = request.client.host if request.client else "unknown"
    try:
        app.rate_limiter.check(identity)
        user = app.security.authenticate(payload.username, payload.password)
    except AuthError as exc:
        app.rate_limiter.fail(identity)
        app.audit.record(payload.username, "auth.login", "session", "failure", {"source": identity})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    app.rate_limiter.success(identity)
    app.audit.record(user.username, "auth.login", "session", "success", {"source": identity})
    return LoginResponse(
        token=app.security.issue_token(user),
        expires_in=app.settings.session_ttl_seconds,
    )


@router.get("/me")
def me(user: UserContext = Depends(current_user)) -> dict[str, str]:
    return user.model_dump()
