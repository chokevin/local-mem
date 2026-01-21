.PHONY: install dev test test-cov test-e2e lint format typecheck clean run cli help setup docker-build docker-up docker-down docker-logs docker-clean

# Default target
help:
	@echo "Local Memory MCP Server - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup       Create venv and install dev dependencies (recommended)"
	@echo "  make install     Install production dependencies"
	@echo "  make dev         Install development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run         Run the MCP server"
	@echo "  make cli         Run the CLI (use ARGS='list' for commands)"
	@echo ""
	@echo "Testing:"
	@echo "  make test        Run all tests"
	@echo "  make test-cov    Run tests with coverage report"
	@echo "  make test-v      Run tests with verbose output"
	@echo "  make test-e2e    Run Playwright E2E tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint        Run linter (ruff)"
	@echo "  make format      Format code (ruff)"
	@echo "  make typecheck   Run type checker (mypy)"
	@echo "  make check       Run all checks (lint + typecheck + test)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean       Remove build artifacts and caches"

# Setup with uv (recommended)
setup:
	uv venv
	uv pip install -e ".[dev]"
	@echo ""
	@echo "Setup complete! Activate with: source .venv/bin/activate"

# Installation (using uv)
install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

# Default profile
PROFILE ?= test

# Running
run:
	MEM_PROFILE=$(PROFILE) uv run python -m src.server

ui:
	uv run python -m src.web --force

cli:
	uv run python -m src.cli --profile $(PROFILE) $(ARGS)

# Testing
test:
	uv run pytest

test-cov:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

test-v:
	uv run pytest -v

test-e2e:
	@echo "Installing Playwright browsers if needed..."
	uv run playwright install chromium --with-deps 2>/dev/null || uv run playwright install chromium
	@echo "Running E2E tests..."
	uv run pytest tests/e2e/ -v

# Code quality
lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

check: lint typecheck test

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Docker commands
docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "✓ local-mem is running at http://localhost:8080"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-clean:
	docker compose down --rmi local -v

