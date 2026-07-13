# Assembly v2 runbook

This branch is an integration lane. `main` remains the rollback target until every promotion gate passes.

## Prerequisites

- Docker Desktop or Docker Engine with Compose.
- Ollama running on the host.
- A tool-capable local model, initially `qwen3:8b`.
- Home Assistant reachable from the Docker host.
- A Home Assistant long-lived access token dedicated to JARVIS Home.

Do not use an administrator token shared with other applications. Expose only the entities needed for the current capability set.

## Configure

Generate independent random secrets:

```powershell
python scripts/bootstrap_config.py
```

Edit `.env` and set:

```env
JARVIS_HOME_ASSISTANT_URL=http://homeassistant.local:8123
JARVIS_HOME_ASSISTANT_TOKEN=<dedicated-token>
JARVIS_OLLAMA_MODEL=qwen3:8b
```

The generated MCP token is shared only between OpenJarvis and the private MCP gateway. The MCP service has no host port mapping.

## Start

Windows:

```powershell
.\scripts\setup-assembly.ps1
```

Linux/macOS:

```bash
sh scripts/setup-assembly.sh
```

Interfaces:

- JARVIS Home owner UI: `http://localhost:8787`
- OpenJarvis: `http://localhost:8000`
- OPA and MCP: Docker-internal only

## Verify the first path

1. Sign in to JARVIS Home and confirm Home Assistant, policy, and audit status.
2. In OpenJarvis ask: `書斎の照明の状態を確認して`.
3. Confirm a read succeeds without an approval.
4. Ask: `書斎の照明を消して`.
5. Confirm OpenJarvis reports that approval is required rather than claiming success.
6. Open JARVIS Home and inspect the exact entity, service, and arguments.
7. Reject the action first; confirm no Home Assistant call occurs.
8. Repeat and approve; inspect the audit trail.

The current slice still uses the v1 approval execution path. It must not be promoted to `main` until post-action state verification and a durable DBOS workflow are added.

## Stop and roll back

```bash
docker compose -f deploy/assembly/docker-compose.yml down
```

The original `main` deployment is unaffected. To discard all assembly state:

```bash
docker compose -f deploy/assembly/docker-compose.yml down -v
```

This removes assembly volumes. It does not delete the Git branch or modify Home Assistant.

## Diagnostics

```bash
docker compose -f deploy/assembly/docker-compose.yml ps
docker compose -f deploy/assembly/docker-compose.yml logs --tail=200 jarvis-mcp
docker compose -f deploy/assembly/docker-compose.yml logs --tail=200 opa
docker compose -f deploy/assembly/docker-compose.yml logs --tail=200 openjarvis
```

Never paste `.env`, `master.key`, Home Assistant tokens, MCP tokens, or OpenJarvis API keys into issues or chat logs.
