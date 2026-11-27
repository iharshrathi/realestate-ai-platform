.DEFAULT_GOAL := help
PY ?= python
BACKEND := backend
FRONTEND := frontend

.PHONY: help install install-backend install-frontend train data seed run-api run-web test test-backend test-frontend lint format docs up down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install backend deps (use a virtualenv)
	cd $(BACKEND) && $(PY) -m pip install -r requirements-dev.txt

install-frontend: ## Install frontend deps
	cd $(FRONTEND) && npm ci

train: ## Train the lead-scoring model on synthetic data
	cd $(BACKEND) && $(PY) -m scripts.train_model

data: ## Regenerate the synthetic CSV in ./data
	cd $(BACKEND) && $(PY) -m scripts.generate_data

seed: ## Create tables and load synthetic demo data (resets nothing; use `seed-reset` to wipe)
	cd $(BACKEND) && $(PY) -m scripts.seed

seed-reset: ## Drop all data and re-seed
	cd $(BACKEND) && $(PY) -m scripts.seed --reset

run-api: ## Run the API with auto-reload on :8000
	cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000

run-web: ## Run the frontend dev server on :5173
	cd $(FRONTEND) && npm run dev

test: test-backend test-frontend ## Run all tests

test-backend:
	cd $(BACKEND) && $(PY) -m pytest

test-frontend:
	cd $(FRONTEND) && npm test

lint: ## Lint and check formatting
	cd $(BACKEND) && $(PY) -m ruff check . && $(PY) -m ruff format --check .

format: ## Auto-format and fix lint
	cd $(BACKEND) && $(PY) -m ruff check --fix . && $(PY) -m ruff format .

up: ## Start everything with Docker Compose
	docker compose up --build

down: ## Stop Docker Compose
	docker compose down
