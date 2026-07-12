from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings
from .db import Database, utcnow
from .schemas import UserContext


class AuthError(Exception):
    pass


class SecurityManager:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.passwords = PasswordHasher()
        self.serializer = URLSafeTimedSerializer(settings.session_secret, salt="jarvis-session-v1")

    def bootstrap_admin(self) -> None:
        row = self.db.query_one("SELECT username FROM users WHERE username=?", (self.settings.admin_username,))
        if row:
            return
        now = utcnow()
        self.db.execute(
            "INSERT INTO users(username, password_hash, role, created_at, updated_at) VALUES(?,?,?,?,?)",
            (
                self.settings.admin_username,
                self.passwords.hash(self.settings.admin_password),
                "owner",
                now,
                now,
            ),
        )

    def authenticate(self, username: str, password: str) -> UserContext:
        row = self.db.query_one(
            "SELECT username, password_hash, role FROM users WHERE username=?",
            (username,),
        )
        if not row:
            raise AuthError("Invalid credentials")
        try:
            self.passwords.verify(row["password_hash"], password)
        except Exception as exc:
            raise AuthError("Invalid credentials") from exc
        if self.passwords.check_needs_rehash(row["password_hash"]):
            self.db.execute(
                "UPDATE users SET password_hash=?, updated_at=? WHERE username=?",
                (self.passwords.hash(password), utcnow(), username),
            )
        return UserContext(username=row["username"], role=row["role"])

    def issue_token(self, user: UserContext) -> str:
        return self.serializer.dumps({"sub": user.username, "role": user.role, "iat": utcnow()})

    def verify_token(self, token: str) -> UserContext:
        try:
            payload = self.serializer.loads(token, max_age=self.settings.session_ttl_seconds)
        except SignatureExpired as exc:
            raise AuthError("Session expired") from exc
        except BadSignature as exc:
            raise AuthError("Invalid session") from exc
        return UserContext(username=str(payload["sub"]), role=str(payload.get("role", "owner")))


class SecretStore:
    def __init__(self, db: Database, key_path: Path):
        self.db = db
        self.key_path = key_path
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            Fernet(key)
            return key
        key = Fernet.generate_key()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(self.key_path, flags, 0o600)
        try:
            os.write(fd, key + b"\n")
        finally:
            os.close(fd)
        return key

    def set(self, key: str, value: str) -> None:
        encrypted = self._fernet.encrypt(value.encode("utf-8"))
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO secrets(key, ciphertext, updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET ciphertext=excluded.ciphertext,
                    updated_at=excluded.updated_at
                """,
                (key, encrypted, utcnow()),
            )

    def get(self, key: str, default: str = "") -> str:
        row = self.db.query_one("SELECT ciphertext FROM secrets WHERE key=?", (key,))
        if not row:
            return default
        try:
            return self._fernet.decrypt(row["ciphertext"]).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(f"Cannot decrypt secret {key!r}; master key mismatch") from exc

    def delete(self, key: str) -> None:
        self.db.execute("DELETE FROM secrets WHERE key=?", (key,))


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def check(self, identity: str) -> None:
        now = datetime.now(UTC).timestamp()
        recent = [t for t in self._failures.get(identity, []) if now - t < self.window_seconds]
        self._failures[identity] = recent
        if len(recent) >= self.attempts:
            raise AuthError("Too many login attempts. Try again later.")

    def fail(self, identity: str) -> None:
        self._failures.setdefault(identity, []).append(datetime.now(UTC).timestamp())

    def success(self, identity: str) -> None:
        self._failures.pop(identity, None)


def redact(value: Any) -> Any:
    secret_words = {"token", "password", "secret", "authorization", "api_key", "apikey"}
    if isinstance(value, dict):
        return {key: "***REDACTED***" if key.lower() in secret_words else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
