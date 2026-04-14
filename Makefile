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
	@echo "  make bump-patch     x.y.Z+1  -- bug fix"
	@echo "  make bump-minor     x.Y+1.0  -- new feature"
	@echo "  make bump-major     X+1.0.0  -- breaking change"
	@echo ""
	@echo "  make release        lint -> bump-patch -> tag -> push"
	@echo "  make release-minor  lint -> bump-minor -> tag -> push"
	@echo "  make release-major  lint -> bump-major -> tag -> push"
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

# ── Version ──────────────────────────────────────────────────

.PHONY: version
version:
	@python3 -c "import json; m=json.load(open('$(MANIFEST)')); print('Version: ' + m['version'])"

.PHONY: bump-patch
bump-patch:
	@python3 -c "\
import json; \
m=json.load(open('$(MANIFEST)')); \
p=list(map(int,m['version'].split('.'))); \
p[2]+=1; \
m['version']='.'.join(map(str,p)); \
json.dump(m,open('$(MANIFEST)','w'),indent=2); \
open('$(MANIFEST)','a').write('\n'); \
print('Bumped to ' + m['version'])"

.PHONY: bump-minor
bump-minor:
	@python3 -c "\
import json; \
m=json.load(open('$(MANIFEST)')); \
p=list(map(int,m['version'].split('.'))); \
p[1]+=1; p[2]=0; \
m['version']='.'.join(map(str,p)); \
json.dump(m,open('$(MANIFEST)','w'),indent=2); \
open('$(MANIFEST)','a').write('\n'); \
print('Bumped to ' + m['version'])"

.PHONY: bump-major
bump-major:
	@python3 -c "\
import json; \
m=json.load(open('$(MANIFEST)')); \
p=list(map(int,m['version'].split('.'))); \
p[0]+=1; p[1]=0; p[2]=0; \
m['version']='.'.join(map(str,p)); \
json.dump(m,open('$(MANIFEST)','w'),indent=2); \
open('$(MANIFEST)','a').write('\n'); \
print('Bumped to ' + m['version'])"

# ── Release ──────────────────────────────────────────────────

.PHONY: release
release: lint bump-patch
	$(eval VER := $(shell python3 -c "import json; print(json.load(open('$(MANIFEST)'))['version'])"))
	@echo "--- Releasing v$(VER)"
	git add $(MANIFEST)
	git commit -m "chore: release v$(VER)"
	git tag -a "v$(VER)" -m "Release v$(VER)"
	git push && git push --tags
	@echo "Released v$(VER)"

.PHONY: release-minor
release-minor: lint bump-minor
	$(eval VER := $(shell python3 -c "import json; print(json.load(open('$(MANIFEST)'))['version'])"))
	@echo "--- Releasing v$(VER)"
	git add $(MANIFEST)
	git commit -m "chore: release v$(VER)"
	git tag -a "v$(VER)" -m "Release v$(VER)"
	git push && git push --tags
	@echo "Released v$(VER)"

.PHONY: release-major
release-major: lint bump-major
	$(eval VER := $(shell python3 -c "import json; print(json.load(open('$(MANIFEST)'))['version'])"))
	@echo "--- Releasing v$(VER)"
	git add $(MANIFEST)
	git commit -m "chore: release v$(VER)"
	git tag -a "v$(VER)" -m "Release v$(VER)"
	git push && git push --tags
	@echo "Released v$(VER)"
