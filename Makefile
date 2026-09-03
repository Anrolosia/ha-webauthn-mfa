# =============================================================
#  ha-webauthn-mfa - Developer Makefile
# =============================================================
#
#  Commands:
#    make help          Show this help
#    make install       Install all dev dependencies (needs Python 3.14+)
#    make lint          Run ruff checks
#    make format        Auto-format Python sources
#    make test          Run pytest in Docker (no local Python needed)
#    make version       Show current version
#    make release-dry   Preview the inferred bump and changelog
#    make release       Auto-bump from conventional commits + tag + push
#
#  An activated virtual environment is picked up automatically.
#  Otherwise, override the interpreter explicitly:
#    make install PYTHON=/path/to/python3.14

.DEFAULT_GOAL := help

# Prefer the interpreter of an activated virtualenv. A Windows venv creates
# Scripts/python.exe and no python3 at all, so a bare "python3" would silently
# fall through to whatever is on PATH (usually the Microsoft Store build) even
# with the venv active. A variable passed on the command line still wins.
ifdef VIRTUAL_ENV
  ifneq ($(wildcard $(VIRTUAL_ENV)/bin/python),)
    PYTHON ?= $(VIRTUAL_ENV)/bin/python
  else
    PYTHON ?= $(VIRTUAL_ENV)/Scripts/python.exe
  endif
else
  PYTHON ?= python3
endif

MANIFEST  := custom_components/webauthn_mfa/manifest.json
COMPONENT := custom_components/webauthn_mfa

# ── Helpers ──────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  ha-webauthn-mfa -- Developer Commands"
	@echo ""
	@echo "  make install        Install Python dev dependencies (Python 3.14+)"
	@echo "  make lint           Check Python (ruff)"
	@echo "  make format         Auto-format Python sources"
	@echo "  make test           Run pytest (docker)"
	@echo ""
	@echo "  make version        Show current version"
	@echo ""
	@echo "  make release-dry    Preview the inferred bump and changelog"
	@echo "  make release        Auto-bump from conventional commits + tag + push"
	@echo "  make release BUMP=minor      Force a bump type"
	@echo "  make release VERSION=1.2.0   Set an explicit version"
	@echo "  make release-patch  Force patch bump"
	@echo "  make release-minor  Force minor bump"
	@echo "  make release-major  Force major bump"
	@echo ""
	@echo "  Interpreter in use: $(PYTHON)"
	@echo ""

# ── Dependencies ─────────────────────────────────────────────

# pytest-homeassistant-custom-component tracks Home Assistant, which requires
# Python 3.14+. On an older interpreter pip filters the newer releases out of
# the index and fails with a misleading "no matching distribution" error, so
# check the version up front and say what is actually wrong.
.PHONY: check-python
check-python:
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { \
		echo ""; \
		echo "Interpreter '$(PYTHON)' was not found."; \
		echo "Activate a virtualenv, or point make at one:"; \
		echo "  make install PYTHON=/path/to/python3.14"; \
		echo "Or skip the local install:  make test"; \
		echo ""; \
		exit 1; \
	}
	@"$(PYTHON)" -c "import sys; sys.exit(0) if sys.version_info[:2] >= (3, 14) else sys.exit('\nPython 3.14 or newer is required by the test stack.\nFound ' + sys.version.split()[0] + ' at ' + sys.executable + '.\n\nIf a virtualenv is active, make did not pick it up. Otherwise:\n  make install PYTHON=/path/to/python3.14\nOr skip the local install entirely:\n  make test   (builds in Docker)\n')"

.PHONY: install
install: check-python
	@echo "--- Installing Python dependencies with $(PYTHON)"
	"$(PYTHON)" -m pip install -r requirements_test.txt
	"$(PYTHON)" -m pip install ruff
	@echo "Done."

# ── Lint ─────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo "--- ruff check"
	ruff check $(COMPONENT)
	@echo "--- ruff format check"
	ruff format --check $(COMPONENT)
	@echo "Lint passed."

# ── Format ───────────────────────────────────────────────────

.PHONY: format
format:
	@echo "--- ruff format"
	ruff format $(COMPONENT)
	ruff check --fix $(COMPONENT)
	@echo "Format done."

# ── Tests ────────────────────────────────────────────────────

.PHONY: test
test:
	@echo "--- pytest (docker)"
	docker compose run --rm test

# ── Dev environment ──────────────────────────────────────────

.PHONY: dev-init
dev-init:
	@echo "--- Preparing dev/ha-config"
	mkdir -p dev/ha-config
	@if [ -f dev/ha-config/configuration.yaml ]; then \
		echo "dev/ha-config/configuration.yaml already exists, left untouched."; \
	else \
		cp dev/configuration.example.yaml dev/ha-config/configuration.yaml; \
		echo "Created dev/ha-config/configuration.yaml"; \
	fi

# ── Version ──────────────────────────────────────────────────

.PHONY: version
version:
	@"$(PYTHON)" -c "import json; m=json.load(open('$(MANIFEST)')); print('Version: ' + m['version'])"


# ── Release ──────────────────────────────────────────────────

.PHONY: release release-dry release-patch release-minor release-major

release:
	@"$(PYTHON)" scripts/release.py $(if $(VERSION),--version $(VERSION),) $(if $(BUMP),--bump $(BUMP),)

release-dry:
	@"$(PYTHON)" scripts/release.py --dry-run $(if $(VERSION),--version $(VERSION),) $(if $(BUMP),--bump $(BUMP),)

release-patch:
	@$(MAKE) release BUMP=patch

release-minor:
	@$(MAKE) release BUMP=minor

release-major:
	@$(MAKE) release BUMP=major