# james-in-a-box Makefile
# ========================
# Single entry point for common development tasks

.PHONY: help \
        test test-quick test-python test-bash \
        check check-fix check-python check-bash \
        lint lint-fix lint-fix-jib \
        lint-python lint-python-fix \
        lint-shell lint-shell-fix \
        lint-yaml lint-yaml-fix \
        lint-docker lint-workflows \
        install-linters check-linters \
        act act-lint act-test

# Default target
help:
	@echo "james-in-a-box Development Commands"
	@echo "===================================="
	@echo ""
	@echo "Pre-Push Checks (run before pushing code):"
	@echo "  make check             - Run all pre-push checks (works in jib container)"
	@echo "  make check-fix         - Run checks with auto-fix"
	@echo "  make check-python      - Python checks only"
	@echo "  make check-bash        - Bash checks only"
	@echo ""
	@echo "Local GitHub Actions (requires Docker on host):"
	@echo "  make act               - Run all GH Actions locally with act"
	@echo "  make act-lint          - Run lint workflow with act"
	@echo "  make act-test          - Run test workflow with act"
	@echo ""
	@echo "Testing:"
	@echo "  make test              - Run all tests (pytest)"
	@echo "  make test-quick        - Quick syntax check (faster)"
	@echo "  make test-python       - Run Python syntax tests only"
	@echo "  make test-bash         - Run Bash syntax tests only"
	@echo ""
	@echo "Linting (host-side, requires full tool installation):"
	@echo "  make lint              - Run all linters"
	@echo "  make lint-fix          - Run all linters with auto-fix"
	@echo "  make lint-fix-jib      - Fix remaining issues with jib"
	@echo "  make lint-python       - Lint Python files with ruff"
	@echo "  make lint-python-fix   - Lint and fix Python files"
	@echo "  make lint-shell        - Lint shell scripts with shellcheck"
	@echo "  make lint-shell-fix    - Format shell scripts with shfmt"
	@echo "  make lint-yaml         - Lint YAML files with yamllint"
	@echo "  make lint-yaml-fix     - Fix common YAML issues (trailing spaces)"
	@echo "  make lint-docker       - Lint Dockerfiles with hadolint"
	@echo "  make lint-workflows    - Lint GitHub Actions with actionlint"
	@echo ""
	@echo "Setup:"
	@echo "  make install-linters   - Install all linting tools"
	@echo "  make check-linters     - Check if linting tools are installed"

# ============================================================================
# Pre-Push Check Targets (work inside jib container without Docker)
# ============================================================================

# Run all pre-push checks - USE THIS BEFORE PUSHING CODE
check:
	@echo "Running pre-push checks..."
	@python scripts/pre-push-checks.py

# Run checks with auto-fix enabled
check-fix:
	@echo "Running pre-push checks with auto-fix..."
	@python scripts/pre-push-checks.py --fix

# Python checks only
check-python:
	@python scripts/pre-push-checks.py --python

# Bash checks only
check-bash:
	@python scripts/pre-push-checks.py --bash

# ============================================================================
# Local GitHub Actions with act (requires Docker on host)
# ============================================================================

# Run all GitHub Actions workflows locally using act
# This requires Docker to be running on the HOST (not in jib container)
act:
	@echo "Running all GitHub Actions workflows with act..."
	@if ! command -v act >/dev/null 2>&1; then \
		echo "Error: 'act' is not installed."; \
		echo "Install with: brew install act (macOS) or curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash"; \
		exit 1; \
	fi
	@if ! docker info >/dev/null 2>&1; then \
		echo "Error: Docker is not running. act requires Docker."; \
		exit 1; \
	fi
	act push --platform ubuntu-latest=catthehacker/ubuntu:act-latest

# Run lint workflow only with act
act-lint:
	@echo "Running lint workflow with act..."
	act push --platform ubuntu-latest=catthehacker/ubuntu:act-latest -W .github/workflows/lint.yml

# Run test workflow only with act
act-test:
	@echo "Running test workflow with act..."
	act push --platform ubuntu-latest=catthehacker/ubuntu:act-latest -W .github/workflows/test.yml

# ============================================================================
# Testing Targets
# ============================================================================

# Run all tests using pytest
test:
	python -m pytest tests/ -v

# Quick syntax-only check (no pytest overhead)
test-quick:
	python tests/run_tests.py --quick -v

# Run Python tests only
test-python:
	python -m pytest tests/test_python_syntax.py -v

# Run Bash tests only
test-bash:
	python -m pytest tests/test_bash_syntax.py -v

# ============================================================================
# Linting Targets
# ============================================================================

# Run all linters
lint: lint-python lint-shell lint-yaml lint-docker
	@echo ""
	@echo "All linters completed!"

# Run all linters with auto-fix where possible
lint-fix: lint-python-fix lint-shell-fix lint-yaml-fix
	@echo ""
	@echo "==> Running lint to check for remaining issues..."
	@$(MAKE) lint 2>&1 | tee /tmp/lint-output.txt; \
	if grep -q "failed\|error\|Error" /tmp/lint-output.txt 2>/dev/null; then \
		echo ""; \
		echo "Some issues remain. Run 'make lint-fix-jib' to fix them with jib."; \
	else \
		echo "All linters completed with auto-fixes applied!"; \
	fi

# Fix remaining lint issues using jib
lint-fix-jib:
	@echo "==> Collecting remaining lint issues..."
	@echo ""
	@LINT_OUTPUT=$$($(MAKE) lint 2>&1); \
	if echo "$$LINT_OUTPUT" | grep -qE "(failed|error|Error|warning|Warning)"; then \
		echo "Found issues to fix. Invoking jib..."; \
		echo ""; \
		echo "$$LINT_OUTPUT" > /tmp/lint-issues.txt; \
		jib --exec "Fix these linting issues. The output is from running 'make lint'. For each issue, read the file, understand the problem, and fix it. Here are the issues:\n\n$$(cat /tmp/lint-issues.txt)"; \
	else \
		echo "No remaining lint issues found!"; \
	fi

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
	@ruff check --fix --unsafe-fixes .
	@ruff format .
	@echo "Python files fixed!"

# ----------------------------------------------------------------------------
# Shell (shellcheck + shfmt)
# ----------------------------------------------------------------------------
SHELL_FILES := $(shell find . -name "*.sh" -not -path "./.venv/*" -not -path "./venv/*" -not -path "./.git/*" 2>/dev/null)

lint-shell:
	@echo "==> Linting shell scripts with shellcheck..."
	@if [ -n "$(SHELL_FILES)" ]; then \
		shellcheck --severity=warning $(SHELL_FILES) || (echo "Shell linting failed!" && exit 1); \
		echo "Shell linting passed!"; \
	else \
		echo "No shell scripts found."; \
	fi

lint-shell-fix:
	@echo "==> Formatting shell scripts with shfmt..."
	@if [ -n "$(SHELL_FILES)" ]; then \
		shfmt -w -i 2 -ci -bn $(SHELL_FILES); \
		echo "Shell scripts formatted!"; \
		echo "==> Running shellcheck..."; \
		shellcheck --severity=warning $(SHELL_FILES) || echo "Some shellcheck issues require manual fixes (see above)."; \
	else \
		echo "No shell scripts found."; \
	fi

# ----------------------------------------------------------------------------
# YAML (yamllint)
# ----------------------------------------------------------------------------
YAML_FILES := $(shell find . \( -name "*.yaml" -o -name "*.yml" \) \
	-not -path "./.venv/*" -not -path "./venv/*" -not -path "./node_modules/*" -not -path "./.git/*" 2>/dev/null)

lint-yaml:
	@echo "==> Linting YAML files with yamllint..."
	@yamllint -c .yamllint.yaml . || (echo "YAML linting failed!" && exit 1)
	@echo "YAML linting passed!"

lint-yaml-fix:
	@echo "==> Fixing YAML files..."
	@if [ -n "$(YAML_FILES)" ]; then \
		echo "  Removing trailing whitespace..."; \
		for f in $(YAML_FILES); do \
			sed -i 's/[[:space:]]*$$//' "$$f"; \
		done; \
		echo "  Ensuring newline at end of files..."; \
		for f in $(YAML_FILES); do \
			[ -n "$$(tail -c1 "$$f")" ] && echo "" >> "$$f"; \
		done; \
		echo "YAML files fixed!"; \
		echo "==> Running yamllint..."; \
		yamllint -c .yamllint.yaml . || echo "Some YAML issues require manual fixes (see above)."; \
	else \
		echo "No YAML files found."; \
	fi

# ----------------------------------------------------------------------------
# Docker (hadolint)
# ----------------------------------------------------------------------------
DOCKERFILES := $(shell find . -name "Dockerfile*" -not -path "./.venv/*" -not -path "./.git/*" 2>/dev/null)

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
	uv tool install ruff
	@echo ""
	@echo "==> Installing yamllint (YAML linter)..."
	uv tool install yamllint
	@echo ""
	@echo "==> Checking for shfmt..."
	@if ! command -v shfmt >/dev/null 2>&1; then \
		echo "shfmt not found. Install with:"; \
		echo "  Ubuntu/Debian: sudo apt-get install shfmt"; \
		echo "  macOS: brew install shfmt"; \
		echo "  Go: go install mvdan.cc/sh/v3/cmd/shfmt@latest"; \
		echo "  Or: https://github.com/mvdan/sh#shfmt"; \
	else \
		echo "shfmt is installed: $$(shfmt --version)"; \
	fi
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
	@echo -n "shfmt: "
	@if command -v shfmt >/dev/null 2>&1; then shfmt --version; else echo "NOT INSTALLED"; fi
	@echo -n "shellcheck: "
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck --version | head -1; else echo "NOT INSTALLED"; fi
	@echo -n "yamllint: "
	@if command -v yamllint >/dev/null 2>&1; then yamllint --version; else echo "NOT INSTALLED"; fi
	@echo -n "hadolint: "
	@if command -v hadolint >/dev/null 2>&1; then hadolint --version; else echo "NOT INSTALLED"; fi
	@echo -n "actionlint: "
	@if command -v actionlint >/dev/null 2>&1; then actionlint --version; else echo "NOT INSTALLED"; fi
