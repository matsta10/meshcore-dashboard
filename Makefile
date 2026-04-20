.PHONY: dev build-frontend test lint

dev:
	cd frontend && npm run dev &
	uv run uvicorn meshcore_dashboard.main:app --reload --port 8000

build-frontend:
	cd frontend && npm run build

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run pytest tests/ -v

lint:
	uv run ruff format .
	uv run ruff check .
