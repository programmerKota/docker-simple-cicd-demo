from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from ..application import Application
from ..schemas import UserContext
from .deps import current_user, get_application

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> dict[str, str]:
    data = await audio.read()
    if len(data) > 25_000_000:
        raise HTTPException(status_code=413, detail="Audio file too large")
    suffix = "." + (audio.filename.rsplit(".", 1)[-1] if audio.filename and "." in audio.filename else "webm")
    try:
        return {"text": app.voice.transcribe(data, suffix)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/speak")
def speak(
    payload: SpeakRequest,
    app: Application = Depends(get_application),
    _: UserContext = Depends(current_user),
) -> Response:
    try:
        audio = app.voice.speak(payload.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")
