.PHONY: install dev test test-cov lint format typecheck clean run cli help setup

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
	uv run python -m src.web

cli:
	uv run python -m src.cli --profile $(PROFILE) $(ARGS)

# Testing
test:
	uv run pytest

test-cov:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

test-v:
	uv run pytest -v

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
