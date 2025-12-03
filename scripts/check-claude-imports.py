#!/usr/bin/env python3
"""
Lint check: Ensure Claude is not imported in host-services.

The Claude module can ONLY be used inside the jib container because:
1. Claude CLI requires the container environment to run
2. Host services run on the host machine without container tools
3. Importing claude directly in host-services causes ModuleNotFoundError at runtime

CORRECT pattern for host-services:
    - Use jib_exec to delegate to a container-side processor
    - The processor (in jib-container/jib-tasks/) can import and use claude

INCORRECT pattern:
    - Directly importing 'from claude import ...' in host-services files

This script is intended to be run as a CI check or pre-commit hook.

Usage:
    python3 scripts/check-claude-imports.py

Exit codes:
    0 - No forbidden imports found
    1 - Found forbidden Claude imports in host-services
"""

import re
import sys
from pathlib import Path


def check_file_for_claude_import(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for forbidden Claude imports.

    Returns:
        List of (line_number, line_content) tuples for each violation.
    """
    violations = []

    # Patterns that indicate direct Claude usage
    forbidden_patterns = [
        r"^\s*from\s+claude\s+import",  # from claude import ...
        r"^\s*import\s+claude\b",  # import claude
        r"^\s*from\s+claude\.",  # from claude.module import ...
    ]

    try:
        content = file_path.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, start=1):
            for pattern in forbidden_patterns:
                if re.match(pattern, line):
                    violations.append((i, line.strip()))
                    break

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)

    return violations


def main():
    """Run the lint check on host-services directory."""
    # Get repo root (parent of scripts/)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    host_services_dir = repo_root / "host-services"

    if not host_services_dir.exists():
        print(f"Warning: host-services directory not found at {host_services_dir}")
        return 0

    # Find all Python files in host-services
    python_files = list(host_services_dir.rglob("*.py"))

    all_violations = []

    for file_path in python_files:
        violations = check_file_for_claude_import(file_path)
        if violations:
            rel_path = file_path.relative_to(repo_root)
            all_violations.append((rel_path, violations))

    # Report results
    if all_violations:
        print("ERROR: Found forbidden Claude imports in host-services!\n")
        print("=" * 70)
        print("Claude can ONLY be used inside the jib container.")
        print("Host services must use jib_exec to delegate to container-side processors.")
        print("=" * 70)
        print()

        for file_path, violations in all_violations:
            print(f"File: {file_path}")
            for line_num, line_content in violations:
                print(f"  Line {line_num}: {line_content}")
            print()

        print("How to fix:")
        print("  1. Create a processor in jib-container/jib-tasks/ that imports Claude")
        print("  2. Update the host-services script to use jib_exec to call the processor")
        print("  3. See host-services/analysis/beads-analyzer/ for an example")
        print()

        return 1
    else:
        print("OK: No forbidden Claude imports found in host-services")
        return 0


if __name__ == "__main__":
    sys.exit(main())
