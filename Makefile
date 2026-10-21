.DEFAULT_GOAL := help
.PHONY: help install install-py install-web lint lint-py lint-web test test-py test-web run-api run-web train evaluate ingest snapshot-rome data-spike routing-spike

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

train: ## Train the ranking model -> models/ranker.txt
	uv run python -m ranker.train

evaluate: ## Evaluate the ranker vs baselines (NDCG@k)
	uv run python -m ranker.evaluate

CITY ?= Lisbon, Portugal
ROME_BBOX := 41.87,12.43,41.94,12.53
OSRM_FOOT ?= https://routing.openstreetmap.de/routed-foot

ingest: ## Ingest one city into data/out: make ingest CITY="Porto, Portugal"
	uv run python -m ingest "$(CITY)"

snapshot-rome: ## Rebuild the committed Rome snapshot in data/cities/rome
	uv run python -m ingest "Rome, Italy" --bbox $(ROME_BBOX) --slug rome \
		--alias Roma --alias "Roma, Italia" \
		--out data/cities --curation data/curation/rome.json --matrix-top 0

data-spike: ## Hours and price coverage for four cities -> docs/data-spike.md
	uv run python -m ingest.spike "Rome, Italy@$(ROME_BBOX)" "Lisbon, Portugal" \
		"Porto, Portugal" "Tbilisi, Georgia"

routing-spike: ## Haversine vs OSRM foot routing for Rome -> docs/routing-spike.md
	uv run python -m ingest.routing_spike Rome --osrm-url $(OSRM_FOOT)
