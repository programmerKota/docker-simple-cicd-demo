#!/usr/bin/env sh
set -eu

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/bootstrap_config.py
elif command -v python >/dev/null 2>&1; then
  python scripts/bootstrap_config.py
else
  docker run --rm -v "$(pwd):/workspace" -w /workspace python:3.12-slim \
    python scripts/bootstrap_config.py
fi

printf '\nStarting JARVIS Home...\n'
docker compose up -d --build
printf '\nOpen http://localhost:8787\n'
