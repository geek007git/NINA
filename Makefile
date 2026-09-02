# Convenience targets. Everything here is a one-line command you can also run
# directly; nothing depends on make being installed.

.PHONY: help install test lint fmt type check doctor console dev clean

help:
	@echo "install  Install the package with dev extras"
	@echo "test     Run the test suite"
	@echo "lint     Run ruff"
	@echo "fmt      Format with ruff"
	@echo "type     Run mypy"
	@echo "check    lint + type + test"
	@echo "doctor   Validate configuration and dependencies"
	@echo "console  Talk to NINA in the terminal"
	@echo "dev      Run a worker with hot reload"

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

fmt:
	ruff format .
	ruff check --fix .

type:
	mypy

check: lint type test

doctor:
	nina doctor

console:
	nina console

dev:
	nina dev

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
