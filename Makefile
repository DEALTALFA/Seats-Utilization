.PHONY: help install lint fmt typecheck test check run build up down smoke clean

PYTHON ?= python
IMAGE  ?= seat-utilization:dev

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install the package with dev extras
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Ruff lint + format check
	ruff check .
	ruff format --check .

fmt: ## Apply Ruff formatting and autofixes
	ruff check --fix .
	ruff format .

typecheck: ## Mypy over the app package
	mypy app


run: ## Serve locally with reload
	uvicorn app.main:app --reload --port 8000

build: ## Build the container image
	docker build -t $(IMAGE) .

up: ## Start the stack with hot-reload
	docker compose up --build

down: ## Stop the stack
	docker compose down -v

smoke: ## Hit /health against a running container
	curl -fsS http://localhost:8000/health

clean: ## Remove caches and coverage output
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
