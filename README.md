# JARVIS Home

A local-first household AI that connects an Ollama model to Home Assistant, private memory, routines, approved PC actions, voice adapters, and a tamper-evident audit trail.

This is not a demo shell around a chatbot. The language model is deliberately separated from the execution layer:

```text
User / microphone / dashboard
              │
              ▼
       Ollama agent loop
              │ proposes typed tool calls
              ▼
       Deterministic policy engine
        ├─ allow low-risk reads
        ├─ require one-time approval
        └─ deny critical core actions
              │
              ▼
 Home Assistant / memory / routines / files / shell
              │
              ▼
   hash-chained audit log + event stream
```

## What works

- Japanese or English chat through a local Ollama server.
- Ollama function calling with a bounded multi-step agent loop.
- Home Assistant entity discovery, state reads, and service calls.
- Explicit approval cards for physical changes, file writes, routines, and shell commands.
- Dynamic risk escalation for locks, alarms, covers, cameras, and trackers.
- Encrypted Home Assistant token storage using a machine-local Fernet master key.
- Argon2 password authentication and expiring signed sessions.
- SQLite long-term memory with FTS5 and a Japanese substring fallback.
- Scheduled, multi-step routines using cron expressions.
- Filesystem access restricted to configured roots with symlink/path escape protection.
- Shell execution disabled by default, `shell=False`, executable allowlist, restricted environment, and timeout.
- Atomic SQLite backups without bundling the encryption key.
- Tamper-evident SHA-256 audit log chain.
- Local voice input through optional `faster-whisper`; local speech output through Piper.
- Responsive browser dashboard for phone and desktop.
- Docker non-root execution, read-only root filesystem, dropped Linux capabilities, security headers, CORS and host restrictions.
- CLI, tests, static analysis, dependency audit, and GitHub Actions.

## Fastest installation: Docker

Prerequisites:

- Docker Desktop or Docker Engine with Compose.
- Ollama installed on the host.
- Home Assistant when real household devices will be controlled.

### Windows PowerShell

```powershell
./scripts/setup.ps1
```

### Linux or macOS

```bash
./scripts/setup.sh
```

The setup command creates:

- `.env` with a random session secret and random initial password;
- `master.key` with restrictive file permissions where supported;
- persistent `data/` and `backups/` directories.

Open `http://localhost:8787` and log in with the password printed once during setup.

## Native installation

Python 3.11–3.13 is supported.

```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

python -m pip install -e '.[dev]'
jarvis init
jarvis serve --host 127.0.0.1 --port 8787
```

## Ollama

Use a model that supports tool calling. The default is `qwen3:8b` and can be changed in the dashboard.

```bash
ollama pull qwen3:8b
ollama serve
```

When JARVIS runs in Docker, the default Ollama URL is `http://host.docker.internal:11434`. Native installations normally use `http://127.0.0.1:11434`.

## Home Assistant

1. Open the Home Assistant profile page.
2. Create a long-lived access token.
3. In JARVIS, open **設定 → Home Assistant**.
4. Enter the local URL and token.
5. Use the **ホーム** page to inspect available entity IDs.
6. Create routines or issue natural-language commands.

The token is encrypted before it is stored in SQLite. It is redacted from audit details and API responses.

## Example commands

```text
リビングの照明の状態を確認して
全部の climate エンティティを一覧にして
「勉強開始時は机の照明をつける」と覚えて
就寝ルーチンを実行して
このワークスペース内から「処理骨格」を検索して
システム状態を確認して
```

State-changing commands create an approval card. Approval is one-time, expires automatically, and is bound to the exact tool name and arguments displayed.

## Voice

Local transcription:

```bash
python -m pip install -e '.[voice]'
```

Set `JARVIS_WHISPER_MODEL=small` or another faster-whisper model. The microphone button records in the browser and sends audio only to the local JARVIS endpoint.

For speech output, install Piper and set `JARVIS_PIPER_COMMAND` to a command that reads UTF-8 text from stdin and writes WAV bytes to stdout. Hardware-specific examples are in `docs/OPERATIONS.md`.

## PC access

Set comma-separated absolute paths in `JARVIS_WORKSPACE_ROOTS`. Nothing outside those roots is visible to the file tools.

```env
JARVIS_WORKSPACE_ROOTS=C:\Users\kotaA\Documents\Projects,C:\Users\kotaA\Documents\法律
```

Shell execution remains disabled unless all three conditions are met:

1. `JARVIS_ENABLE_SHELL=true`;
2. the executable is listed in `JARVIS_SHELL_ALLOWLIST`;
3. the user approves the exact command.

## Administration

```bash
jarvis doctor
jarvis backup
jarvis serve
```

Run the quality gates:

```bash
ruff check .
mypy jarvis_home
pytest
pip-audit --skip-editable
```

## Scope boundary

The software is complete within its declared boundary: orchestration, policy, approvals, integrations, storage, UI, operations, tests, and extension mechanisms are implemented. A physical house still requires device-specific onboarding in Home Assistant, accurate entity names, microphones/speakers where desired, and network placement chosen by the owner. JARVIS does not pretend to operate hardware that has not been connected.

Do not expose port 8787 directly to the public internet. Use a private LAN, VPN such as Tailscale/WireGuard, or a hardened reverse proxy with independent authentication.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security and threat model](docs/SECURITY.md)
- [Operations and recovery](docs/OPERATIONS.md)
- [Extension guide](docs/EXTENDING.md)
- [Hardware deployment](docs/HARDWARE.md)

Licensed under Apache-2.0.
