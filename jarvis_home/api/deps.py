from __future__ import annotations

from typing import cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..application import Application
from ..schemas import UserContext
from ..security import AuthError

bearer = HTTPBearer(auto_error=False)


def get_application(request: Request) -> Application:
    return cast(Application, request.app.state.jarvis)


def current_user(
    app: Application = Depends(get_application),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UserContext:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return app.security.verify_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
