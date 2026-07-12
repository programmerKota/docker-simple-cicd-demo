from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_home.application import Application
from jarvis_home.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    value = Settings(
        env="test",
        host="127.0.0.1",
        data_dir=tmp_path / "data",
        backup_dir=tmp_path / "backups",
        master_key_file=tmp_path / "master.key",
        session_secret="test-session-secret-that-is-long-enough-123456",  # noqa: S106
        admin_username="admin",
        admin_password="correct-horse-battery-staple",  # noqa: S106
        trusted_hosts="testserver,localhost,127.0.0.1",
        allowed_origins="http://testserver",
        workspace_roots=str(workspace),
        ollama_url="http://127.0.0.1:9",
        home_assistant_url="http://127.0.0.1:9",
    )
    value.ensure_directories()
    return value


@pytest.fixture()
def application(settings: Settings) -> Application:
    return Application(settings)
