#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/bootstrap_config.py
elif command -v python >/dev/null 2>&1; then
  python scripts/bootstrap_config.py
else
  docker run --rm -v "$(pwd):/workspace" -w /workspace python:3.12-slim \
    python scripts/bootstrap_config.py
fi

if ! grep -Eq '^JARVIS_HOME_ASSISTANT_TOKEN=.+$' .env; then
  printf '%s\n' 'WARNING: Home Assistant token is not configured. Home reads/actions remain unavailable.' >&2
fi

printf '%s\n' 'Building the pinned JARVIS assembly...'
docker compose --env-file .env -f deploy/assembly/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/assembly/docker-compose.yml ps
printf '%s\n' 'JARVIS Home control: http://localhost:8787'
printf '%s\n' 'OpenJarvis:          http://localhost:8000'
