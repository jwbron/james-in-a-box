#!/usr/bin/env python3
"""
Lint check: Ensure host-services and jib-container code don't cross-call each other.

The host/container boundary is a critical security and architectural pattern:
1. Host code (host-services/) must NOT directly call container code (jib-container/)
2. Container code (jib-container/) must NOT directly call host code (host-services/)

CORRECT pattern:
    - Host -> Container: Use `jib --exec` to run container commands
    - Container -> Host: Not allowed (container is sandboxed)

INCORRECT patterns:
    - Host script doing: python3 /path/to/jib-container/script.py
    - Host script importing: from jib_container.module import ...
    - Adding jib-container paths to sys.path in host code

This script is intended to be run as a CI check or pre-commit hook.

See: jib-container/.claude/rules/host-container-boundary.md

Usage:
    python3 scripts/check-host-container-boundary.py

Exit codes:
    0 - No cross-boundary violations found
    1 - Found cross-boundary code calls
"""

import re
import sys
from pathlib import Path


def check_host_calls_container(file_path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """Check a host-services file for direct calls to jib-container code.

    Returns:
        List of (line_number, line_content, reason) tuples for each violation.
    """
    violations = []

    # Patterns that indicate host code directly calling container code
    # Each tuple is (pattern, reason, is_execution_pattern)
    # is_execution_pattern=True means we need to verify it's actually executing code
    violation_patterns = [
        # Direct python3 calls to jib-container scripts
        (
            r"python3?\s+.*jib-container/",
            "Direct python call to jib-container script. Use 'jib --exec' instead.",
            True,
        ),
        # sys.path.insert with jib-container
        (
            r"sys\.path\.(insert|append).*jib-container",
            "Adding jib-container to sys.path. Use 'jib --exec' instead.",
            True,
        ),
        # Import from jib_container (if someone tries to make it a package)
        (
            r"^\s*from\s+jib_container\b",
            "Import from jib_container. Use 'jib --exec' instead.",
            True,
        ),
        (
            r"^\s*import\s+jib_container\b",
            "Import of jib_container. Use 'jib --exec' instead.",
            True,
        ),
        # Direct source of jib-container scripts in bash
        (
            r"^\s*source\s+.*jib-container/",
            "Sourcing jib-container script. Use 'jib --exec' instead.",
            True,
        ),
        (
            r"^\s*\.\s+.*jib-container/",
            "Sourcing jib-container script. Use 'jib --exec' instead.",
            True,
        ),
    ]

    try:
        content = file_path.read_text()
        lines = content.split("\n")

        # Track if we're in a docstring or multi-line string
        in_docstring = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip single-line comments
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Track docstrings (simple heuristic)
            if '"""' in line or "'''" in line:
                # Toggle docstring state (simple - doesn't handle all edge cases)
                count = line.count('"""') + line.count("'''")
                if count == 1:
                    in_docstring = not in_docstring
                continue

            if in_docstring:
                continue

            for pattern, reason, is_exec in violation_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append((i, line.strip(), reason))
                    break

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)

    return violations


def check_container_calls_host(file_path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """Check a jib-container file for direct calls to host-services code.

    NOTE: Container code CAN legitimately import/use host-services modules
    since both are available inside the container at runtime. The boundary
    we're enforcing is:
    - Host code cannot directly execute container code (must use jib --exec)

    For container->host, we only flag subprocess calls that would try to
    execute host scripts as if they were on the host filesystem.

    Returns:
        List of (line_number, line_content, reason) tuples for each violation.
    """
    violations = []

    # Patterns that indicate container code trying to call out to the host
    # (which would fail anyway since container is sandboxed)
    violation_patterns = [
        # Direct subprocess calls to host-services scripts
        # (would indicate confusion about where code runs)
        (
            r"subprocess\.(run|call|Popen).*host-services/",
            "Subprocess call to host-services. Container cannot call host directly.",
        ),
        # Import from host_services as a package (misunderstanding of architecture)
        (
            r"^\s*from\s+host_services\b",
            "Import from host_services as package. Use direct path imports instead.",
        ),
        (
            r"^\s*import\s+host_services\b",
            "Import of host_services as package. Use direct path imports instead.",
        ),
    ]

    try:
        content = file_path.read_text()
        lines = content.split("\n")

        in_docstring = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip single-line comments
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Track docstrings
            if '"""' in line or "'''" in line:
                count = line.count('"""') + line.count("'''")
                if count == 1:
                    in_docstring = not in_docstring
                continue

            if in_docstring:
                continue

            for pattern, reason in violation_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append((i, line.strip(), reason))
                    break

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)

    return violations


def main():
    """Run the lint check on host-services and jib-container directories."""
    # Get repo root (parent of scripts/)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    host_services_dir = repo_root / "host-services"
    jib_container_dir = repo_root / "jib-container"

    all_violations = []

    # Check host-services for calls to jib-container
    if host_services_dir.exists():
        # Find all Python and shell files in host-services
        python_files = list(host_services_dir.rglob("*.py"))
        shell_files = list(host_services_dir.rglob("*.sh"))
        # Also check scripts without extension (like jib-internal-devtools-setup)
        all_files = []
        for f in host_services_dir.rglob("*"):
            if f.is_file() and not f.suffix:
                # Check if it's a shell script by looking at shebang
                try:
                    first_line = f.read_text().split("\n")[0]
                    if first_line.startswith("#!") and ("bash" in first_line or "sh" in first_line):
                        all_files.append(f)
                except Exception:
                    pass
        all_files.extend(python_files)
        all_files.extend(shell_files)

        for file_path in all_files:
            violations = check_host_calls_container(file_path, repo_root)
            if violations:
                rel_path = file_path.relative_to(repo_root)
                all_violations.append(("host->container", rel_path, violations))

    # Check jib-container for calls to host-services
    if jib_container_dir.exists():
        python_files = list(jib_container_dir.rglob("*.py"))
        shell_files = list(jib_container_dir.rglob("*.sh"))

        for file_path in python_files + shell_files:
            violations = check_container_calls_host(file_path, repo_root)
            if violations:
                rel_path = file_path.relative_to(repo_root)
                all_violations.append(("container->host", rel_path, violations))

    # Report results
    if all_violations:
        print("ERROR: Found host/container boundary violations!\n")
        print("=" * 70)
        print("ARCHITECTURE VIOLATION: Host and container code must not cross-call.")
        print()
        print("Why this matters:")
        print("  - Host code runs on the user's machine with full access")
        print("  - Container code runs in a sandboxed Docker environment")
        print("  - Crossing this boundary breaks security isolation")
        print("  - Use 'jib --exec' to delegate from host to container")
        print("=" * 70)
        print()

        for direction, file_path, violations in all_violations:
            print(f"[{direction}] File: {file_path}")
            for line_num, line_content, reason in violations:
                print(f"  Line {line_num}: {line_content[:80]}...")
                print(f"           Reason: {reason}")
            print()

        print("How to fix:")
        print("  1. Host -> Container: Use 'jib --exec <command>' instead of direct calls")
        print("  2. For LLM work: Create a task in jib-container/jib-tasks/ and invoke via")
        print("     'jib --exec analysis-processor --task <task_type> --context <json>'")
        print("  3. See host-services/analysis/repo-onboarding/jib-internal-devtools-setup")
        print("     for an example of the correct pattern.")
        print()
        print("Documentation: jib-container/.claude/rules/host-container-boundary.md")
        print()

        return 1
    else:
        print("OK: No host/container boundary violations found")
        return 0


if __name__ == "__main__":
    sys.exit(main())
