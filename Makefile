PY_INDEX := --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com

.PHONY: help venv install dev run fmt lint test clean

help:
	@echo "Targets:"
	@echo "  venv     - create .venv with uv"
	@echo "  install  - editable install bdboard into .venv"
	@echo "  dev      - run with reload (in cwd workspace)"
	@echo "  run      - run normally"
	@echo "  fmt      - ruff format"
	@echo "  lint     - ruff check"
	@echo "  clean    - rm caches and venv"

venv:
	uv venv

install: venv
	uv pip install $(PY_INDEX) -e .

dev:
	.venv/bin/uvicorn bdboard.app:app --reload --port 7332

run:
	.venv/bin/bdboard

fmt:
	.venv/bin/ruff format src/

lint:
	.venv/bin/ruff check src/

clean:
	rm -rf .venv __pycache__ src/bdboard/__pycache__ .ruff_cache build dist *.egg-info
