#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  python -m jarvis_home.cli init
fi
mkdir -p data backups plugins
printf '\nStarting JARVIS Home...\n'
docker compose up -d --build
printf '\nOpen http://localhost:8787\n'
