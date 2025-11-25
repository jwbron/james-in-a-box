# James-in-a-Box Makefile
# Unified linting and development commands

.PHONY: help lint lint-python lint-shell lint-yaml lint-docker lint-workflows \
        lint-fix lint-python-fix install-linters check-linters

# Default target
help:
	@echo "James-in-a-Box Development Commands"
	@echo ""
	@echo "Linting:"
	@echo "  make lint              - Run all linters"
	@echo "  make lint-fix          - Run all linters with auto-fix"
	@echo "  make lint-python       - Lint Python files with ruff"
	@echo "  make lint-python-fix   - Lint and fix Python files"
	@echo "  make lint-shell        - Lint shell scripts with shellcheck"
	@echo "  make lint-yaml         - Lint YAML files with yamllint"
	@echo "  make lint-docker       - Lint Dockerfiles with hadolint"
	@echo "  make lint-workflows    - Lint GitHub Actions with actionlint"
	@echo ""
	@echo "Setup:"
	@echo "  make install-linters   - Install all linting tools"
	@echo "  make check-linters     - Check if linting tools are installed"

# ============================================================================
# Linting Targets
# ============================================================================

# Run all linters
lint: lint-python lint-shell lint-yaml lint-docker
	@echo ""
	@echo "All linters passed!"

# Run all linters with auto-fix where possible
lint-fix: lint-python-fix lint-shell lint-yaml lint-docker
	@echo ""
	@echo "All linters completed!"

# ----------------------------------------------------------------------------
# Python (ruff)
# ----------------------------------------------------------------------------
lint-python:
	@echo "==> Linting Python files with ruff..."
	@ruff check . || (echo "Python linting failed. Run 'make lint-python-fix' to auto-fix." && exit 1)
	@ruff format --check . || (echo "Python formatting issues found. Run 'make lint-python-fix' to auto-fix." && exit 1)
	@echo "Python linting passed!"

lint-python-fix:
	@echo "==> Fixing Python files with ruff..."
	@ruff check --fix .
	@ruff format .
	@echo "Python files fixed!"

# ----------------------------------------------------------------------------
# Shell (shellcheck)
# ----------------------------------------------------------------------------
SHELL_FILES := $(shell find . -name "*.sh" -not -path "./.venv/*" -not -path "./venv/*" 2>/dev/null)

lint-shell:
	@echo "==> Linting shell scripts with shellcheck..."
	@if [ -n "$(SHELL_FILES)" ]; then \
		shellcheck --severity=warning $(SHELL_FILES) || (echo "Shell linting failed!" && exit 1); \
		echo "Shell linting passed!"; \
	else \
		echo "No shell scripts found."; \
	fi

# ----------------------------------------------------------------------------
# YAML (yamllint)
# ----------------------------------------------------------------------------
lint-yaml:
	@echo "==> Linting YAML files with yamllint..."
	@yamllint -c .yamllint.yaml . || (echo "YAML linting failed!" && exit 1)
	@echo "YAML linting passed!"

# ----------------------------------------------------------------------------
# Docker (hadolint)
# ----------------------------------------------------------------------------
DOCKERFILES := $(shell find . -name "Dockerfile*" -not -path "./.venv/*" 2>/dev/null)

lint-docker:
	@echo "==> Linting Dockerfiles with hadolint..."
	@if [ -n "$(DOCKERFILES)" ]; then \
		for f in $(DOCKERFILES); do \
			echo "  Checking $$f..."; \
			hadolint --config .hadolint.yaml "$$f" || exit 1; \
		done; \
		echo "Docker linting passed!"; \
	else \
		echo "No Dockerfiles found."; \
	fi

# ----------------------------------------------------------------------------
# GitHub Actions (actionlint)
# ----------------------------------------------------------------------------
lint-workflows:
	@echo "==> Linting GitHub Actions workflows with actionlint..."
	@if [ -d ".github/workflows" ]; then \
		actionlint || (echo "GitHub Actions linting failed!" && exit 1); \
		echo "GitHub Actions linting passed!"; \
	else \
		echo "No .github/workflows directory found."; \
	fi

# ============================================================================
# Setup Targets
# ============================================================================

# Install all linting tools
install-linters:
	@echo "Installing linting tools..."
	@echo ""
	@echo "==> Installing ruff (Python linter)..."
	pip install ruff
	@echo ""
	@echo "==> Installing yamllint (YAML linter)..."
	pip install yamllint
	@echo ""
	@echo "==> Checking for shellcheck..."
	@if ! command -v shellcheck >/dev/null 2>&1; then \
		echo "shellcheck not found. Install with:"; \
		echo "  Ubuntu/Debian: sudo apt-get install shellcheck"; \
		echo "  macOS: brew install shellcheck"; \
		echo "  Or: https://github.com/koalaman/shellcheck#installing"; \
	else \
		echo "shellcheck is installed: $$(shellcheck --version | head -1)"; \
	fi
	@echo ""
	@echo "==> Checking for hadolint..."
	@if ! command -v hadolint >/dev/null 2>&1; then \
		echo "hadolint not found. Install with:"; \
		echo "  macOS: brew install hadolint"; \
		echo "  Linux: Download from https://github.com/hadolint/hadolint/releases"; \
		echo "  Or: docker run --rm -i hadolint/hadolint < Dockerfile"; \
	else \
		echo "hadolint is installed: $$(hadolint --version)"; \
	fi
	@echo ""
	@echo "==> Checking for actionlint..."
	@if ! command -v actionlint >/dev/null 2>&1; then \
		echo "actionlint not found. Install with:"; \
		echo "  macOS: brew install actionlint"; \
		echo "  Go: go install github.com/rhysd/actionlint/cmd/actionlint@latest"; \
		echo "  Or: https://github.com/rhysd/actionlint#installation"; \
	else \
		echo "actionlint is installed: $$(actionlint --version)"; \
	fi
	@echo ""
	@echo "Linting tools installation complete!"

# Check if linting tools are installed
check-linters:
	@echo "Checking linting tools..."
	@echo ""
	@echo -n "ruff: "
	@if command -v ruff >/dev/null 2>&1; then ruff --version; else echo "NOT INSTALLED"; fi
	@echo -n "shellcheck: "
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck --version | head -1; else echo "NOT INSTALLED"; fi
	@echo -n "yamllint: "
	@if command -v yamllint >/dev/null 2>&1; then yamllint --version; else echo "NOT INSTALLED"; fi
	@echo -n "hadolint: "
	@if command -v hadolint >/dev/null 2>&1; then hadolint --version; else echo "NOT INSTALLED"; fi
	@echo -n "actionlint: "
	@if command -v actionlint >/dev/null 2>&1; then actionlint --version; else echo "NOT INSTALLED"; fi
