# Operations and recovery

## First boot checklist

1. Run `jarvis init` or the platform setup script.
2. Save the generated initial password.
3. Start Ollama and pull a tool-capable model.
4. Start JARVIS and sign in.
5. Configure Home Assistant URL and token.
6. Verify **Ollama**, **Home Assistant**, and **Audit Chain** are green.
7. Configure workspace roots only when file access is needed.
8. Test a harmless light action and confirm the approval path.
9. Create a backup.
10. Copy `master.key` to a separate encrypted location.

## Configuration changes

Integration URLs and the Home Assistant token can be changed in the dashboard. Runtime settings are stored in SQLite; secrets are encrypted. Environment variables remain the bootstrap defaults.

Settings that affect process-level security—workspace roots, shell enablement, plugin enablement, host binding, CORS, and trusted hosts—require `.env` changes and a restart.

## Backup

```bash
jarvis backup
```

The ZIP contains a consistent `jarvis.db` and a manifest. It deliberately excludes `master.key`.

Verify a backup:

```bash
sha256sum backups/jarvis-backup-*.zip
unzip -l backups/jarvis-backup-*.zip
```

## Restore

1. Stop JARVIS.
2. Copy the current `data/` directory somewhere safe.
3. Extract `jarvis.db` from the selected ZIP into `data/jarvis.db`.
4. Restore the matching `master.key` separately.
5. Set owner-only file permissions where supported.
6. Start JARVIS.
7. Run `jarvis doctor` and check `/api/audit/verify` in the dashboard.

A database restored without its original master key remains usable except encrypted secrets; those must be deleted/re-entered.

## Logs

Docker:

```bash
docker compose logs -f --tail=200 jarvis
```

The application deliberately avoids logging request bodies, credentials, message content, and tokens. Operational errors include request IDs for correlation.

## Updating

```bash
git pull
docker compose build --pull
docker compose up -d
```

Before updating:

```bash
jarvis backup
```

After updating:

```bash
jarvis doctor
pytest
```

## Ollama troubleshooting

- Native: use `http://127.0.0.1:11434`.
- Docker Desktop: use `http://host.docker.internal:11434`.
- Linux Docker: Compose adds `host.docker.internal:host-gateway`.
- Confirm with `curl http://127.0.0.1:11434/api/tags` on the host.
- Ensure the chosen model appears in the response and supports tools.
- Large models may need a longer first response while loaded into VRAM/RAM.

## Home Assistant troubleshooting

- Confirm the URL includes port 8123 unless a reverse proxy is used.
- Regenerate the token after any suspected exposure.
- Verify the token with `GET /api/` and the `Authorization: Bearer` header.
- Inspect actual entity IDs on the JARVIS Home page.
- Home Assistant REST service calls expect fields such as `entity_id` in service data.
- Keep entity names stable or update routines after renaming.

## Local voice

Install the extra:

```bash
pip install -e '.[voice]'
```

`faster-whisper` downloads the selected model on first use. For a CPU-only installation, `small` with int8 compute is the default compromise.

Piper command shape:

```env
JARVIS_PIPER_COMMAND=piper --model /models/ja_JP-model.onnx --output-raw
```

The command must accept text on stdin and emit WAV bytes on stdout. Piper packaging differs by operating system; validate the command independently before enabling it.

## Remote access

Preferred order:

1. Local LAN only.
2. Tailscale or WireGuard.
3. Reverse proxy with TLS plus independent authentication and IP restrictions.
4. Never direct router port forwarding to JARVIS.

When accessed through a stable hostname, add it to `JARVIS_TRUSTED_HOSTS` and its full origin to `JARVIS_ALLOWED_ORIGINS`.

## Incident response

1. Stop JARVIS and disconnect remote access.
2. Revoke the Home Assistant token.
3. Rotate the JARVIS password and session secret.
4. Preserve logs, DB, and the last known audit hash.
5. Verify the audit chain and inspect recent approvals/tool calls.
6. Disable shell and plugins.
7. Restore from a known-good backup if integrity is uncertain.
8. Patch the host, dependencies, and Home Assistant before reconnecting.
