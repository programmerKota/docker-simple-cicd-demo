$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    python -m jarvis_home.cli init
}
New-Item -ItemType Directory -Force -Path "data", "backups", "plugins" | Out-Null
Write-Host "Starting JARVIS Home..." -ForegroundColor Cyan
docker compose up -d --build
Write-Host "Open http://localhost:8787" -ForegroundColor Green
