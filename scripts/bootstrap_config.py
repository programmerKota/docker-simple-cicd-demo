from __future__ import annotations

import base64
import os
import secrets
from contextlib import suppress
from pathlib import Path


def write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
    with suppress(OSError):
        path.chmod(0o600)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    example = root / ".env.example"
    env_file = root / ".env"
    key_file = root / "master.key"
    generated_password: str | None = None

    if not example.exists():
        raise SystemExit(f"Missing template: {example}")

    if not env_file.exists():
        generated_password = secrets.token_urlsafe(18)
        session_secret = secrets.token_urlsafe(48)
        content = example.read_text(encoding="utf-8")
        content = content.replace(
            "replace-with-at-least-32-random-characters", session_secret
        ).replace("replace-this-now", generated_password)
        write_private(env_file, content.encode("utf-8"))
        print(f"Created {env_file.name}")
    else:
        print(f"Keeping existing {env_file.name}")

    if not key_file.exists():
        # Fernet keys are 32 random bytes encoded with URL-safe base64.
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)) + b"\n"
        write_private(key_file, key)
        print(f"Created {key_file.name}")
    else:
        print(f"Keeping existing {key_file.name}")

    for directory in ("data", "backups", "plugins"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    if generated_password:
        print("\nJARVIS Home initial credentials")
        print("Username: admin")
        print(f"Password: {generated_password}")
        print("Store the password now. It cannot be recovered from the database.")


if __name__ == "__main__":
    main()
