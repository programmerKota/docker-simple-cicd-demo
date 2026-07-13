from __future__ import annotations

import base64
import json
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


def replace_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with suppress(FileNotFoundError):
        temporary.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temporary, flags, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)
    os.replace(temporary, path)
    with suppress(OSError):
        path.chmod(0o600)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_openjarvis_config(root: Path, env: dict[str, str]) -> Path:
    mcp_token = env.get("JARVIS_MCP_TOKEN", "")
    if len(mcp_token) < 32 or mcp_token.startswith("replace-"):
        raise SystemExit("JARVIS_MCP_TOKEN is missing or unsafe")

    model = env.get("JARVIS_OLLAMA_MODEL", "qwen3:8b") or "qwen3:8b"
    mcp_servers = json.dumps(
        [
            {
                "name": "jarvis-home-safety-gateway",
                "url": "http://jarvis-mcp:8790/mcp",
                "token": mcp_token,
                "include_tools": [
                    "home_gateway_status",
                    "home_observe",
                    "home_propose_light_action",
                    "home_list_pending_approvals",
                ],
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    content = f'''[engine]
default = "ollama"

[engine.ollama]
host = "http://host.docker.internal:11434"

[intelligence]
default_model = {toml_string(model)}
fallback_model = ""
temperature = 0.2
max_tokens = 2048

[agent]
default_agent = "orchestrator"
max_turns = 8
context_from_memory = true

[tools.mcp]
enabled = true
servers = {toml_string(mcp_servers)}
'''
    output = root / "runtime" / "openjarvis-config.toml"
    replace_private(output, content)
    return output


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
        mcp_token = secrets.token_urlsafe(48)
        openjarvis_api_key = secrets.token_urlsafe(48)
        dbos_password = secrets.token_urlsafe(32)
        content = example.read_text(encoding="utf-8")
        content = (
            content.replace("replace-session-secret", session_secret)
            .replace("replace-mcp-token", mcp_token)
            .replace("replace-openjarvis-api-key", openjarvis_api_key)
            .replace("replace-dbos-password", dbos_password)
            .replace("replace-admin-password", generated_password)
        )
        write_private(env_file, content.encode())
        print(f"Created {env_file.name}")
    else:
        print(f"Keeping existing {env_file.name}")

    if not key_file.exists():
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)) + b"\n"
        write_private(key_file, key)
        print(f"Created {key_file.name}")
    else:
        print(f"Keeping existing {key_file.name}")

    for directory in ("data", "backups", "plugins", "runtime"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    config_path = render_openjarvis_config(root, read_env(env_file))
    print(f"Rendered {config_path.relative_to(root)}")

    if generated_password:
        print("\nJARVIS Home initial credentials")
        print("Username: admin")
        print(f"Password: {generated_password}")
        print("Store the password now. It cannot be recovered from the database.")
        print("MCP, DBOS, and OpenJarvis secrets were written only to .env.")


if __name__ == "__main__":
    main()
