# =============================================================
#  ha-webauthn-mfa - Developer Makefile
# =============================================================
#
#  Commands:
#    make help          Show this help
#    make install       Install all dev dependencies
#    make lint          Run ruff checks
#    make format        Auto-format Python sources
#    make test          Run pytest
#    make version       Show current version
#    make bump-patch    1.0.0 -> 1.0.1  (bug fix)
#    make bump-minor    1.0.0 -> 1.1.0  (new feature)
#    make bump-major    1.0.0 -> 2.0.0  (breaking change)
#    make release       lint + bump-patch + tag + push
#    make release-minor lint + bump-minor + tag + push
#    make release-major lint + bump-major + tag + push

.DEFAULT_GOAL := help

PYTHON    ?= python3
MANIFEST  := custom_components/webauthn_mfa/manifest.json
COMPONENT := custom_components/webauthn_mfa

# ── Helpers ──────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  ha-webauthn-mfa -- Developer Commands"
	@echo ""
	@echo "  make install        Install Python dev dependencies"
	@echo "  make lint           Check Python (ruff)"
	@echo "  make format         Auto-format Python sources"
	@echo "  make test           Run pytest"
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

# ── Dependencies ─────────────────────────────────────────────

.PHONY: install
install:
	@echo "--- Installing Python dependencies"
	pip install -r requirements_test.txt
	pip install ruff
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
	@python3 -c "import json; m=json.load(open('$(MANIFEST)')); print('Version: ' + m['version'])"


# ── Release ──────────────────────────────────────────────────

.PHONY: release release-dry release-patch release-minor release-major

release:
	@$(PYTHON) scripts/release.py $(if $(VERSION),--version $(VERSION),) $(if $(BUMP),--bump $(BUMP),)

release-dry:
	@$(PYTHON) scripts/release.py --dry-run $(if $(VERSION),--version $(VERSION),) $(if $(BUMP),--bump $(BUMP),)

release-patch:
	@$(MAKE) release BUMP=patch

release-minor:
	@$(MAKE) release BUMP=minor

release-major:
	@$(MAKE) release BUMP=major