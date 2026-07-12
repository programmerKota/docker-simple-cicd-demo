$ErrorActionPreference = "Stop"

if (Get-Command python -ErrorAction SilentlyContinue) {
    python scripts/bootstrap_config.py
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 scripts/bootstrap_config.py
}
else {
    docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.12-slim python scripts/bootstrap_config.py
}

Write-Host "Starting JARVIS Home..." -ForegroundColor Cyan
docker compose up -d --build
Write-Host "Open http://localhost:8787" -ForegroundColor Green
