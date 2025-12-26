# Makefile for TechSprint project (uv + pyproject.toml workflow)

.PHONY: help install lock test lint format run clean ci

help:
	@echo "Available targets:"
	@echo "  install   Install all dependencies (including dev) via uv"
	@echo "  lock      Update requirements.lock.txt from pyproject.toml"
	@echo "  test      Run all tests with pytest"
	@echo "  lint      Run ruff for lint checks"
	@echo "  format    Run ruff to auto-fix formatting issues"
	@echo "  run       Run the main pipeline in stub mode (no OpenAI)"
	@echo "  clean     Remove build/test artifacts"
	@echo "  ci        Run lint, test, and check lockfile (for CI)"

install:
	uv pip install --all-extras pyproject.toml
	uv pip install --group dev

lock:
	uv pip compile pyproject.toml --output-file requirements.lock.txt

lint:
	ruff check .

format:
	ruff check . --fix

test:
	pytest tests/ --maxfail=3 --disable-warnings -v

run:
	@echo "[DEPRECATED] Use \`techsprint run\` (or \`techsprint run --demo\`) instead." 1>&2
	STUB_SCRIPT_SERVICE=1 uv run techsprint make --log-level DEBUG

clean:
	rm -rf .techsprint
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type d -name '.mypy_cache' -exec rm -rf {} +
	find . -type d -name '.ruff_cache' -exec rm -rf {} +
	find . -type d -name '.pytest_cache' -exec rm -rf {} +

ci: lint test
	@echo "CI checks complete."
