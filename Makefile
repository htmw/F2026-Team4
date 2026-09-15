.DEFAULT_GOAL := help
.PHONY: help install install-py install-web lint lint-py lint-web test test-py test-web run-api run-web

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: install-py install-web ## Install everything (Python + web)

install-py: ## Install Python deps with uv (pins Python 3.11)
	uv sync

install-web: ## Install web deps with npm
	cd web && npm install

lint: lint-py lint-web ## Lint everything

lint-py: ## Ruff lint the Python code
	uv run ruff check .

lint-web: ## Type-check the frontend
	cd web && npm run typecheck

test: test-py test-web ## Run all tests

test-py: ## Run Python tests
	uv run pytest -q

test-web: ## Run frontend tests
	cd web && npm run test

run-api: ## Start the API on http://localhost:8000
	uv run uvicorn api.main:app --reload --port 8000

run-web: ## Start the frontend on http://localhost:5173
	cd web && npm run dev
