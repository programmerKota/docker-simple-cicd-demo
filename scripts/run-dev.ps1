$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
if (-not (Test-Path ".env")) { jarvis init }
jarvis serve --host 127.0.0.1 --port 8787 --reload
