#!/usr/bin/env python3
"""Pre-push checks that mirror GitHub Actions workflows.

This script runs locally (in-container) to catch issues before pushing code.
It replicates the checks from .github/workflows/ without needing Docker.

Usage:
    # Run all checks
    python scripts/pre-push-checks.py

    # Run specific checks
    python scripts/pre-push-checks.py --python     # Python linting only
    python scripts/pre-push-checks.py --bash       # Bash syntax only
    python scripts/pre-push-checks.py --fix        # Auto-fix Python issues

    # Run from Makefile
    make check                # Run all pre-push checks
    make check-fix            # Run with auto-fix

Environment:
    Works inside jib container without Docker.
    Will install ruff via pip if not found.

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(msg: str) -> None:
    """Print a section header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}==> {msg}{Colors.RESET}")


def print_success(msg: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")


def print_error(msg: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")


def print_warning(msg: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")


def find_ruff_executable() -> str | None:
    """Find ruff executable, checking common pip install locations."""
    # Check if it's in PATH
    ruff_path = shutil.which("ruff")
    if ruff_path:
        return ruff_path

    # Check user local bin (pip install --user location)
    user_bin = Path.home() / ".local" / "bin" / "ruff"
    if user_bin.is_file():
        return str(user_bin)

    return None


def ensure_ruff_installed() -> str | None:
    """Ensure ruff is installed, installing via pip if needed. Returns executable path."""
    ruff_path = find_ruff_executable()
    if ruff_path:
        return ruff_path

    print_warning("ruff not found, installing via pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "ruff"],
            check=True,
            capture_output=True,
        )
        print_success("ruff installed successfully")
        # Try to find it again after install
        ruff_path = find_ruff_executable()
        if ruff_path:
            return ruff_path
        print_error("ruff installed but not found in PATH")
        return None
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install ruff: {e}")
        return None


def find_bashate_executable() -> str | None:
    """Find bashate executable, checking common pip install locations."""
    # Check if it's in PATH
    bashate_path = shutil.which("bashate")
    if bashate_path:
        return bashate_path

    # Check user local bin (pip install --user location)
    user_bin = Path.home() / ".local" / "bin" / "bashate"
    if user_bin.is_file():
        return str(user_bin)

    return None


def ensure_bashate_installed() -> str | None:
    """Ensure bashate is installed, installing via pip if needed. Returns executable path."""
    bashate_path = find_bashate_executable()
    if bashate_path:
        return bashate_path

    print_warning("bashate not found, installing via pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "bashate"],
            check=True,
            capture_output=True,
        )
        print_success("bashate installed successfully")
        # Try to find it again after install
        bashate_path = find_bashate_executable()
        if bashate_path:
            return bashate_path
        print_error("bashate installed but not found in PATH")
        return None
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install bashate: {e}")
        return None


def find_project_root() -> Path:
    """Find the project root by looking for .github directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".github").is_dir():
            return current
        current = current.parent

    # Fall back to current directory
    return Path.cwd()


def find_python_files(root: Path) -> list[Path]:
    """Find all Python files in the project."""
    python_files = []
    exclude_dirs = {".git", ".venv", "venv", "__pycache__", ".eggs", "node_modules"}

    for path in root.rglob("*.py"):
        if not any(part in exclude_dirs for part in path.parts):
            python_files.append(path)

    return python_files


def find_shell_files(root: Path) -> list[Path]:
    """Find all shell script files in the project."""
    shell_files = []
    exclude_dirs = {".git", ".venv", "venv", "node_modules"}

    for path in root.rglob("*.sh"):
        if not any(part in exclude_dirs for part in path.parts):
            shell_files.append(path)

    return shell_files


def check_python_syntax(root: Path) -> bool:
    """Check Python syntax for all files."""
    print_header("Checking Python syntax...")

    python_files = find_python_files(root)
    if not python_files:
        print_warning("No Python files found")
        return True

    errors = []
    for py_file in python_files:
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append((py_file, e.stderr.decode() if e.stderr else str(e)))

    if errors:
        print_error(f"Python syntax errors found in {len(errors)} file(s):")
        for file, error in errors[:5]:  # Show first 5
            print(f"  {file}: {error.strip()}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")
        return False

    print_success(f"All {len(python_files)} Python files have valid syntax")
    return True


def check_bash_syntax(root: Path) -> bool:
    """Check Bash syntax for all shell scripts."""
    print_header("Checking Bash syntax...")

    shell_files = find_shell_files(root)
    if not shell_files:
        print_warning("No shell scripts found")
        return True

    errors = []
    for sh_file in shell_files:
        try:
            subprocess.run(
                ["bash", "-n", str(sh_file)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append((sh_file, e.stderr.decode() if e.stderr else str(e)))

    if errors:
        print_error(f"Bash syntax errors found in {len(errors)} file(s):")
        for file, error in errors[:5]:
            print(f"  {file}: {error.strip()}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")
        return False

    print_success(f"All {len(shell_files)} shell scripts have valid syntax")
    return True


def run_ruff_check(root: Path, fix: bool = False) -> bool:
    """Run ruff linter."""
    print_header("Running ruff check (Python linting)...")

    ruff_path = ensure_ruff_installed()
    if not ruff_path:
        return False

    cmd = [ruff_path, "check"]
    if fix:
        cmd.extend(["--fix", "--unsafe-fixes"])
    cmd.append(str(root))

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    if result.returncode != 0:
        if fix:
            print_warning("Applied fixes, checking remaining issues...")
            # Run again without fix to show remaining issues
            result = subprocess.run(
                [ruff_path, "check", str(root)], check=False, capture_output=True, text=True
            )
            if result.returncode != 0:
                print_error("Some issues could not be auto-fixed:")
                print(result.stdout)
                return False
        else:
            print_error("Ruff check failed:")
            # Truncate output if too long
            output = result.stdout
            lines = output.split("\n")
            if len(lines) > 20:
                print("\n".join(lines[:20]))
                print(f"  ... and {len(lines) - 20} more lines")
                print(f"\n{Colors.YELLOW}Run 'make check-fix' to auto-fix issues{Colors.RESET}")
            else:
                print(output)
            return False

    print_success("Ruff check passed")
    return True


def run_ruff_format(root: Path, fix: bool = False) -> bool:
    """Run ruff formatter check."""
    print_header("Running ruff format check (Python formatting)...")

    ruff_path = ensure_ruff_installed()
    if not ruff_path:
        return False

    if fix:
        # Apply formatting
        result = subprocess.run(
            [ruff_path, "format", str(root)], check=False, capture_output=True, text=True
        )
        print_success("Formatting applied")
        return True

    # Check only
    result = subprocess.run(
        [ruff_path, "format", "--check", str(root)], check=False, capture_output=True, text=True
    )

    if result.returncode != 0:
        print_error("Ruff format check failed (files need formatting):")
        output = result.stdout
        lines = output.split("\n")
        if len(lines) > 10:
            print("\n".join(lines[:10]))
            print(f"  ... and {len(lines) - 10} more files")
        else:
            print(output)
        print(f"\n{Colors.YELLOW}Run 'make check-fix' to auto-format{Colors.RESET}")
        return False

    print_success("Ruff format check passed")
    return True


def run_bashate(root: Path) -> bool:
    """Run bashate linter for shell scripts."""
    print_header("Running bashate (shell linting)...")

    shell_files = find_shell_files(root)
    if not shell_files:
        print_warning("No shell scripts found")
        return True

    bashate_path = ensure_bashate_installed()
    if not bashate_path:
        return False

    # Run bashate with ignores that match the GitHub workflow
    # E003 = indent not multiple of 4
    # E006 = long lines
    # E042 = local hides errors
    cmd = [bashate_path, "-i", "E003,E006,E042"] + [str(f) for f in shell_files]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    if result.returncode != 0:
        print_error("Bashate found issues:")
        output = result.stdout + result.stderr
        lines = output.split("\n")
        if len(lines) > 15:
            print("\n".join(lines[:15]))
            print(f"  ... and {len(lines) - 15} more lines")
        else:
            print(output)
        return False

    print_success(f"Bashate passed for {len(shell_files)} shell scripts")
    return True


def run_pytest(root: Path) -> bool:
    """Run pytest if tests directory exists."""
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        print_warning("No tests directory found, skipping pytest")
        return True

    print_header("Running pytest...")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )

    if result.returncode != 0:
        print_error("Tests failed:")
        # Show the last part of output (usually the summary)
        output = result.stdout + result.stderr
        lines = output.split("\n")
        # Find summary section or show last 30 lines
        summary_idx = -1
        for i, line in enumerate(lines):
            if "short test summary" in line.lower() or "FAILED" in line or "passed" in line:
                summary_idx = i
                break
        if summary_idx >= 0:
            print("\n".join(lines[max(0, summary_idx - 5) :]))
        else:
            print("\n".join(lines[-30:]))
        return False

    print_success("All tests passed")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run pre-push checks that mirror GitHub Actions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--python", action="store_true", help="Run Python checks only")
    parser.add_argument("--bash", action="store_true", help="Run Bash checks only")
    parser.add_argument("--test", action="store_true", help="Run tests only")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    parser.add_argument("--no-test", action="store_true", help="Skip running tests")
    parser.add_argument("path", nargs="?", type=Path, help="Project root (default: auto-detect)")

    args = parser.parse_args()

    # Find project root
    root = args.path if args.path else find_project_root()
    if not root.is_dir():
        print_error(f"Directory not found: {root}")
        sys.exit(1)

    print(f"{Colors.BOLD}Pre-push checks for: {root}{Colors.RESET}")

    # Track results
    results = {}
    run_all = not (args.python or args.bash or args.test)

    # Python checks
    if run_all or args.python:
        results["python_syntax"] = check_python_syntax(root)
        results["ruff_check"] = run_ruff_check(root, fix=args.fix)
        results["ruff_format"] = run_ruff_format(root, fix=args.fix)

    # Bash checks
    if run_all or args.bash:
        results["bash_syntax"] = check_bash_syntax(root)
        results["bashate"] = run_bashate(root)

    # Tests
    if (run_all or args.test) and not args.no_test:
        results["pytest"] = run_pytest(root)

    # Summary
    print(f"\n{Colors.BOLD}{'=' * 50}{Colors.RESET}")
    print(f"{Colors.BOLD}Summary:{Colors.RESET}")

    all_passed = True
    for check, passed in results.items():
        status = (
            f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
        )
        print(f"  {check}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n{Colors.GREEN}{Colors.BOLD}All checks passed! Ready to push.{Colors.RESET}")
        sys.exit(0)
    else:
        print(
            f"\n{Colors.RED}{Colors.BOLD}Some checks failed. Please fix issues before pushing.{Colors.RESET}"
        )
        if not args.fix:
            print(f"{Colors.YELLOW}Tip: Run with --fix to auto-fix Python issues{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
