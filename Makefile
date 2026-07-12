.PHONY: install dev test lint audit run docker backup
install:
	python -m venv .venv
	. .venv/bin/activate && pip install -e '.[dev]'
dev:
	uvicorn jarvis_home.main:app --reload --host 127.0.0.1 --port 8787
test:
	pytest --cov=jarvis_home --cov-report=term-missing
lint:
	ruff check .
	mypy jarvis_home
run:
	uvicorn jarvis_home.main:app --host 0.0.0.0 --port 8787
docker:
	docker compose up -d --build
backup:
	jarvis backup
audit:
	pip-audit
