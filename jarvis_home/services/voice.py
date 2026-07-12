from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..config import Settings


class VoiceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any | None = None

    def transcribe(self, audio_bytes: bytes, suffix: str = ".webm") -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install the voice extra: pip install 'jarvis-home[voice]'") from exc
        if self._model is None:
            self._model = WhisperModel(self.settings.whisper_model, compute_type="int8")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio_bytes)
            path = Path(handle.name)
        try:
            model = self._model
            if model is None:
                raise RuntimeError("Whisper model initialization failed")
            segments, _ = model.transcribe(str(path), vad_filter=True)
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            path.unlink(missing_ok=True)

    def speak(self, text: str) -> bytes:
        if not self.settings.piper_command:
            raise RuntimeError("JARVIS_PIPER_COMMAND is not configured")
        argv = shlex.split(self.settings.piper_command)
        result = subprocess.run(  # noqa: S603
            argv,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout
