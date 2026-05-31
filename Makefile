PY_INDEX := --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com

PHONY: help venv install dev run fmt lint test clean dead-code duplication audit outdated code-health links

help:
	@echo "Targets:"
	@echo "  venv        - create .venv with uv"
	@echo "  install     - editable install bdboard into .venv"
	@echo "  dev         - run with reload (in cwd workspace)"
	@echo "  run         - run normally"
	@echo "  fmt         - ruff format"
	@echo "  lint        - ruff check (incl. F401 unused-import / dead-code)"
	@echo "  test        - run pytest"
	@echo "  dead-code   - vulture dead-code sweep (>=80%% confidence)"
	@echo "  duplication - jscpd copy-paste detector (config: .jscpd.json)"
	@echo "  audit       - pip-audit dependency CVE scan"
	@echo "  outdated    - uv pip list --outdated (advisory, never fails)"
	@echo "  links       - lychee broken-link sweep over all markdown (config: lychee.toml)"
	@echo "  code-health - run all mechanical code-health gates (CI parity)"
	@echo "  clean       - rm caches and venv"

venv:
	uv venv

install: venv
	uv pip install $(PY_INDEX) -e .

dev:
	.venv/bin/uvicorn bdboard.app:app --reload --port 7332

run:
	.venv/bin/bdboard

fmt:
	uvx $(PY_INDEX) ruff format src/ tests/

lint:
	uvx $(PY_INDEX) ruff check src/ tests/

test:
	.venv/bin/pytest -q

# --- Mechanical code-health gates (deterministic pass/fail; CI runs these) ---
# Rationale (bdboard-ndm): formulas SPAWN work, they don't RUN checks. These
# deterministic checks gate every PR; the code-health-audit formula triages
# their output rather than re-running tools.

# Dead code: vulture catches unreferenced funcs/vars/imports that ruff F811/
# F841 miss. >=80%% confidence keeps false positives low for a hard gate.
dead-code:
	uvx $(PY_INDEX) vulture src/ --min-confidence 80

# Duplication: jscpd reads .jscpd.json (the single source of truth for
# min-tokens / threshold). Fails when duplication exceeds the configured %%.
duplication:
	npx --yes jscpd

# Dependency CVE scan against the resolved environment.
audit:
	uvx $(PY_INDEX) pip-audit

# Outdated deps: advisory only (|| true) — staleness shouldn't block a PR,
# the code-health-audit formula triages upgrades on its own cadence.
outdated:
	uv pip list --outdated || true

# Aggregate gate — mirror of the CI workflow so contributors can repro locally.
code-health: lint dead-code duplication audit
	@echo "\n✅ mechanical code-health gates passed (outdated is advisory; run 'make outdated')"

# Broken-link sweep (bdboard-mol-003): scan all markdown for dead
# internal/external links and anchors. Requires lychee (brew install lychee).
links:
	@command -v lychee >/dev/null 2>&1 || { echo "lychee not found — install with: brew install lychee"; exit 1; }
	lychee --config lychee.toml './**/*.md'

clean:
	rm -rf .venv __pycache__ src/bdboard/__pycache__ .ruff_cache build dist *.egg-info
