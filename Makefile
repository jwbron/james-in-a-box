# james-in-a-box Makefile
# ========================
# Single entry point for common development tasks

.PHONY: test test-quick test-python test-bash lint help

# Default target
help:
	@echo "james-in-a-box Development Commands"
	@echo "===================================="
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests (pytest)"
	@echo "  make test-quick   - Quick syntax check (faster)"
	@echo "  make test-python  - Run Python syntax tests only"
	@echo "  make test-bash    - Run Bash syntax tests only"
	@echo ""
	@echo "Linting:"
	@echo "  make lint         - Run linters (bashate for shell scripts)"
	@echo ""

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

# Run linters
lint:
	@echo "Running bashate on shell scripts..."
	@find . -name "*.sh" -not -path "./.git/*" -exec bashate {} \; || true
	@echo ""
	@echo "Linting complete."
