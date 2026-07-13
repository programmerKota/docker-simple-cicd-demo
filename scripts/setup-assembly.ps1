$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

if (Get-Command python -ErrorAction SilentlyContinue) {
    python scripts/bootstrap_config.py
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 scripts/bootstrap_config.py
}
else {
    docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.12-slim python scripts/bootstrap_config.py
}

if (-not (Select-String -Path ".env" -Pattern '^JARVIS_HOME_ASSISTANT_TOKEN=.+$' -Quiet)) {
    Write-Warning "Home Assistant token is not configured. The stack will start, but home reads/actions remain unavailable."
}

Write-Host "Building the pinned JARVIS assembly..." -ForegroundColor Cyan
docker compose -f deploy/assembly/docker-compose.yml up -d --build

docker compose -f deploy/assembly/docker-compose.yml ps
Write-Host "JARVIS Home control: http://localhost:8787" -ForegroundColor Green
Write-Host "OpenJarvis:          http://localhost:8000" -ForegroundColor Green
