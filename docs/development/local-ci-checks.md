# Running CI Checks Locally

This guide explains how to run GitHub Actions checks locally before pushing code.

## Quick Start (Inside jib Container)

```bash
cd ~/khan/james-in-a-box

# Run all pre-push checks
make check

# Run with auto-fix for Python issues
make check-fix
```

## What Gets Checked

The `make check` command runs checks that mirror our GitHub Actions workflows:

| Check | What It Does | Auto-fixable? |
|-------|--------------|---------------|
| Python Syntax | Validates all `.py` files compile | No |
| Ruff Check | Python linting (style, bugs, imports) | Yes |
| Ruff Format | Python code formatting | Yes |
| Bash Syntax | Validates all `.sh` files | No |
| Bashate | Shell script style linting | No |
| Pytest | Runs tests in `tests/` directory | No |

## Commands

### Pre-Push Checks (Work in jib Container)

These commands work inside the jib container without Docker:

```bash
# Run all checks
make check

# Run with auto-fix
make check-fix

# Run specific checks
make check-python    # Python checks only
make check-bash      # Bash checks only
```

## Workflow for jib/Claude

Before pushing any changes to the james-in-a-box repository:

1. **Make your changes**
2. **Run pre-push checks:**
   ```bash
   cd ~/khan/james-in-a-box
   make check
   ```
3. **If checks fail:**
   - Run `make check-fix` to auto-fix Python issues
   - Manually fix remaining errors
   - Re-run `make check` to verify
4. **Once checks pass:** Commit and push

## Common Issues and Fixes

### Ruff Linting Errors

Most ruff errors can be auto-fixed:
```bash
make check-fix
```

For errors that can't be auto-fixed, common patterns include:
- **Unused imports**: Remove the import
- **Line too long**: Ruff formatter handles this automatically
- **Import order**: Auto-fixed by `make check-fix`

### Bash Syntax Errors

Check for:
- Missing `fi` or `done` to close blocks
- Unquoted variables with spaces
- Missing shebangs (`#!/bin/bash`)

### Bashate Errors

The following are ignored (per our config):
- E003: Indent not multiple of 4
- E006: Long lines
- E042: Local hides errors

## How It Works

The `scripts/pre-push-checks.py` script:
1. Auto-installs ruff and bashate via pip if not present
2. Runs syntax checks on all Python and Bash files
3. Runs ruff linting and formatting checks
4. Runs bashate shell linting
5. Runs pytest if tests exist
6. Reports pass/fail status with helpful error messages

## Relationship to GitHub Actions

Our GitHub Actions workflows in `.github/workflows/`:

| Workflow | What It Does | Local Equivalent |
|----------|--------------|------------------|
| `lint.yml` | Ruff + Bashate | `make check-python`, `make check-bash` |
| `test.yml` | Pytest + syntax | `make check` |
| `validate-deps.yml` | Dependency validation | Not replicated locally |
| `fix-doc-links.yml` | Documentation links | Not replicated locally |

## Tips

1. **Run checks before every push** - It's faster than waiting for CI
2. **Use `--fix` liberally** - Most Python issues are auto-fixable
3. **Check one type at a time** - Use `make check-python` to focus
4. **Trust the output** - If `make check` passes, CI will likely pass
