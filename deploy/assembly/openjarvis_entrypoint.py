from __future__ import annotations

import json
import os
import stat
from pathlib import Path


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Required environment variable is missing: {name}")
    return value


def toml_string(value: str) -> str:
    # JSON string escaping is valid for TOML basic strings for this constrained input.
    return json.dumps(value, ensure_ascii=False)


def main() -> None:
    home = Path(os.environ.get("OPENJARVIS_HOME", "/var/lib/openjarvis"))
    config_path = Path(os.environ.get("OPENJARVIS_CONFIG", home / "config.toml"))
    home.mkdir(parents=True, exist_ok=True)

    mcp_token = required("JARVIS_MCP_TOKEN")
    mcp_url = os.environ.get("JARVIS_MCP_URL", "http://jarvis-mcp:8790/mcp").strip()
    ollama_host = os.environ.get("OPENJARVIS_OLLAMA_HOST", "http://host.docker.internal:11434").strip()
    model = os.environ.get("OPENJARVIS_MODEL", "qwen3:8b").strip()
    mcp_servers = json.dumps(
        [
            {
                "name": "jarvis-home-safety-gateway",
                "url": mcp_url,
                "token": mcp_token,
                "include_tools": [
                    "home_gateway_status",
                    "home_observe",
                    "home_propose_light_action",
                    "home_list_pending_approvals",
                ],
            }
        ],
        separators=(",", ":"),
    )

    config = f"""[engine]
default = "ollama"

[engine.ollama]
host = {toml_string(ollama_host)}

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
"""
    config_path.write_text(config, encoding="utf-8")
    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    os.execvp(
        "jarvis",
        [
            "jarvis",
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--engine",
            "ollama",
            "--model",
            model,
            "--agent",
            "orchestrator",
        ],
    )


if __name__ == "__main__":
    main()
