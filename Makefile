.PHONY: install check dev build-frontend build clean-build test lint test-matrix help

install: ## Install dependencies and pre-commit hooks
	@echo "Creating environment with uv"
	@uv sync --group dev
	@uv run pre-commit install

check: ## Run lock, lint, and type checks
	@echo "Checking lock file consistency"
	@uv lock --check
	@echo "Running pre-commit"
	@uv run pre-commit run -a --show-diff-on-failure
	@echo "Running static type checks"
	@uv run pyright

dev:
	cd frontend && npm run dev &
	uv run uvicorn meshcore_dashboard.main:app --reload --port 8000

build-frontend:
	cd frontend && npm run build

build: clean-build ## Build the Python package
	@uvx --from build pyproject-build --installer uv

clean-build: ## Remove build artifacts
	@uv run python -c "import os, shutil; shutil.rmtree('dist') if os.path.exists('dist') else None"

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run pytest tests/ -v

lint:
	uv run ruff format .
	uv run ruff check .

test-matrix: ## Run the local Python version matrix with tox-uv
	@uv run tox

help:
	@uv run python -c "import re; \
[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
