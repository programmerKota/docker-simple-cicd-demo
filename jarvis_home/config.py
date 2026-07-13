from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JARVIS_",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = 8787
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8790, ge=1, le=65535)
    mcp_token: str = ""
    data_dir: Path = Path("./data")
    backup_dir: Path = Path("./backups")
    master_key_file: Path = Path("./master.key")
    session_secret: str = "development-only-change-me-please"  # noqa: S105
    admin_username: str = "admin"
    admin_password: str = "admin"  # noqa: S105
    allowed_origins: str = "http://localhost:8787,http://127.0.0.1:8787"
    trusted_hosts: str = "localhost,127.0.0.1"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    home_assistant_url: str = "http://homeassistant.local:8123"
    home_assistant_token: str = ""
    enable_shell: bool = False
    shell_allowlist: str = "python,python3,pwsh,powershell,git"
    workspace_roots: str = ""
    enable_plugins: bool = False
    enabled_plugins: str = ""
    piper_command: str = ""
    whisper_model: str = "small"
    log_level: str = "INFO"
    max_request_bytes: int = 2_000_000
    max_agent_steps: int = Field(default=6, ge=1, le=12)
    session_ttl_seconds: int = Field(default=43_200, ge=300, le=604_800)
    approval_ttl_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("session_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 24:
            raise ValueError("JARVIS_SESSION_SECRET must be at least 24 characters")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jarvis.db"

    @property
    def origin_list(self) -> list[str]:
        return [v.strip() for v in self.allowed_origins.split(",") if v.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [v.strip() for v in self.trusted_hosts.split(",") if v.strip()]

    @property
    def workspace_root_list(self) -> list[Path]:
        return [Path(v.strip()).expanduser().resolve() for v in self.workspace_roots.split(",") if v.strip()]

    @property
    def shell_allowlist_set(self) -> set[str]:
        return {v.strip().lower() for v in self.shell_allowlist.split(",") if v.strip()}

    @property
    def enabled_plugin_set(self) -> set[str]:
        return {v.strip() for v in self.enabled_plugins.split(",") if v.strip()}

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.master_key_file.parent.mkdir(parents=True, exist_ok=True)

    def validate_production(self) -> list[str]:
        errors: list[str] = []
        if self.env != "production":
            return errors
        if self.admin_password in {"admin", "change-this-now", "replace-this-now"}:
            errors.append("JARVIS_ADMIN_PASSWORD is still a default value")
        if "development-only" in self.session_secret or "replace-with" in self.session_secret:
            errors.append("JARVIS_SESSION_SECRET is still a default value")
        if "*" in self.origin_list:
            errors.append("Wildcard CORS origins are forbidden in production")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
