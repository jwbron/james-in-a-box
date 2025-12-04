#!/usr/bin/env python3
"""
Lint check: Ensure all container executables have symlinks in jib-container/bin/.

This prevents the "executable not found in $PATH" error that occurs when:
1. A new processor is added to jib-tasks/ or jib-tools/
2. But no symlink is created in jib-container/bin/
3. The container builds successfully but the executable isn't in PATH

The container's PATH includes /opt/jib-runtime/jib-container/bin/, so all
executables must be accessible via symlinks in that directory.

CORRECT pattern:
    1. Add executable to jib-container/jib-tasks/<category>/<name>.py
    2. Add symlink to jib-container/bin/maintain-bin-symlinks SYMLINKS array
    3. Run maintain-bin-symlinks to create the symlink

This script is intended to be run as a CI check or pre-commit hook.

Usage:
    python3 scripts/check-bin-symlinks.py

Exit codes:
    0 - All symlinks are correct
    1 - Missing or broken symlinks found
"""

import os
import re
import sys
from pathlib import Path


def is_executable_python_file(file_path: Path) -> bool:
    """Check if a Python file is intended to be an executable.

    Checks for:
    - Shebang line (#!/usr/bin/env python3 or similar)
    - __main__ block

    Returns:
        True if the file appears to be an executable script.
    """
    try:
        content = file_path.read_text()
        lines = content.split("\n")

        # Check for shebang
        if lines and lines[0].startswith("#!") and "python" in lines[0]:
            return True

        # Check for __main__ block (even without shebang, indicates executable)
        if 'if __name__ == "__main__"' in content or "if __name__ == '__main__'" in content:
            return True

    except Exception:
        pass

    return False


def parse_maintain_bin_symlinks(script_path: Path) -> dict[str, str]:
    """Parse the SYMLINKS array from maintain-bin-symlinks script.

    Returns:
        Dict mapping symlink name to target path.
    """
    symlinks = {}

    try:
        content = script_path.read_text()

        # Find the SYMLINKS array - match lines like "name:target"
        # Pattern: "symlink_name:relative_path_from_bin"
        in_array = False
        for line in content.split("\n"):
            line = line.strip()

            if "declare -a SYMLINKS=(" in line:
                in_array = True
                continue

            if in_array:
                if line == ")":
                    break

                # Parse "name:target" format (quoted)
                match = re.match(r'"([^:]+):([^"]+)"', line)
                if match:
                    name, target = match.groups()
                    symlinks[name] = target

    except Exception as e:
        print(f"Warning: Could not parse {script_path}: {e}", file=sys.stderr)

    return symlinks


def find_container_executables(jib_container_dir: Path) -> list[tuple[Path, str]]:
    """Find all executable Python files in jib-tasks/ and jib-tools/.

    Returns:
        List of (file_path, suggested_symlink_name) tuples.
    """
    executables = []

    # Files that are intentionally NOT symlinked in bin/
    # These are either:
    # - PATH shadow scripts (like 'git' which shadows /usr/bin/git)
    # - Internal utilities not meant to be called directly
    EXCLUDED_FILES = {
        "git",  # Git wrapper that shadows /usr/bin/git (placed elsewhere in PATH)
    }

    # Directories containing container executables
    exec_dirs = [
        jib_container_dir / "jib-tasks",
        jib_container_dir / "jib-tools",
        jib_container_dir / "scripts",
    ]

    for exec_dir in exec_dirs:
        if not exec_dir.exists():
            continue

        for file_path in exec_dir.rglob("*.py"):
            if is_executable_python_file(file_path):
                # Suggest symlink name: file stem (without .py)
                name = file_path.stem
                if name not in EXCLUDED_FILES:
                    executables.append((file_path, name))

        # Also check for shell scripts
        for file_path in exec_dir.rglob("*"):
            if file_path.is_file() and not file_path.suffix:
                # Check if it's a shell script
                try:
                    content = file_path.read_text()
                    if content.startswith("#!/"):
                        name = file_path.name
                        if name not in EXCLUDED_FILES:
                            executables.append((file_path, name))
                except Exception:
                    pass

    return executables


def check_symlinks(repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Check bin symlinks for issues.

    Returns:
        Tuple of (missing_symlinks, broken_symlinks, unlisted_symlinks).
    """
    jib_container_dir = repo_root / "jib-container"
    bin_dir = jib_container_dir / "bin"
    maintain_script = bin_dir / "maintain-bin-symlinks"

    if not jib_container_dir.exists():
        print(f"Warning: jib-container directory not found at {jib_container_dir}")
        return [], [], []

    if not bin_dir.exists():
        print(f"Warning: bin directory not found at {bin_dir}")
        return [], [], []

    # Parse the maintain-bin-symlinks script to get expected symlinks
    expected_symlinks = parse_maintain_bin_symlinks(maintain_script)

    # Find all executables
    executables = find_container_executables(jib_container_dir)

    missing_symlinks = []  # Executables without symlinks
    broken_symlinks = []  # Symlinks pointing to non-existent files
    unlisted_symlinks = []  # Symlinks in bin/ but not in maintain-bin-symlinks
    reported_unlisted = set()  # Track symlinks already reported as unlisted

    # Check that all executables have symlinks
    for exec_path, exec_name in executables:
        # Skip if the executable has a symlink (by any name)
        rel_path_from_bin = os.path.relpath(exec_path, bin_dir)

        # Check if any symlink points to this file
        has_symlink = False
        for _symlink_name, target in expected_symlinks.items():
            # Normalize paths for comparison
            if target == rel_path_from_bin or target.lstrip("./") == rel_path_from_bin.lstrip("./"):
                has_symlink = True
                break

        if not has_symlink:
            # Check if a symlink actually exists in bin/ even if not in the script
            actual_symlink = bin_dir / exec_name
            if actual_symlink.is_symlink():
                # Symlink exists but not listed in maintain-bin-symlinks
                unlisted_symlinks.append(
                    f"{exec_name} (symlink exists but not in maintain-bin-symlinks)"
                )
                reported_unlisted.add(exec_name)
            else:
                # Truly missing
                missing_symlinks.append(f"{exec_name} ({exec_path.relative_to(repo_root)})")

    # Check for broken symlinks
    for symlink_name, target in expected_symlinks.items():
        if symlink_name == "maintain-bin-symlinks":
            continue  # Skip self-reference

        symlink_path = bin_dir / symlink_name
        target_path = bin_dir / target

        if not symlink_path.exists() and not symlink_path.is_symlink():
            broken_symlinks.append(f"{symlink_name} (symlink missing)")
        elif symlink_path.is_symlink() and not target_path.exists():
            broken_symlinks.append(f"{symlink_name} -> {target} (target does not exist)")

    # Check for symlinks in bin/ that aren't listed in maintain-bin-symlinks
    # Skip symlinks already reported in the executables loop above
    for item in bin_dir.iterdir():
        if item.is_symlink():
            name = item.name
            if (
                name not in expected_symlinks
                and name != "maintain-bin-symlinks"
                and name not in reported_unlisted
            ):
                target = os.readlink(item)
                unlisted_symlinks.append(f"{name} -> {target} (not in maintain-bin-symlinks)")

    return missing_symlinks, broken_symlinks, unlisted_symlinks


def main():
    """Run the lint check on jib-container/bin/ symlinks."""
    # Get repo root (parent of scripts/)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    missing, broken, unlisted = check_symlinks(repo_root)

    has_errors = False

    if missing:
        has_errors = True
        print("ERROR: Found executables without symlinks in jib-container/bin/!\n")
        print("=" * 70)
        print("These executables exist but have no symlink in bin/.")
        print("Without a symlink, they won't be in PATH inside the container.")
        print("=" * 70)
        print()

        for item in missing:
            print(f"  - {item}")
        print()

        print("How to fix:")
        print("  1. Edit jib-container/bin/maintain-bin-symlinks")
        print('  2. Add entry to SYMLINKS array: "name:../relative/path"')
        print("  3. Run: ./jib-container/bin/maintain-bin-symlinks")
        print()

    if broken:
        has_errors = True
        print("ERROR: Found broken symlinks!\n")
        print("=" * 70)
        print("These symlinks are defined but their targets don't exist.")
        print("=" * 70)
        print()

        for item in broken:
            print(f"  - {item}")
        print()

        print("How to fix:")
        print("  1. Check if the target file was moved or renamed")
        print("  2. Update the SYMLINKS entry in maintain-bin-symlinks")
        print("  3. Run: ./jib-container/bin/maintain-bin-symlinks")
        print()

    if unlisted:
        # This is a warning, not an error
        print("WARNING: Found symlinks not listed in maintain-bin-symlinks:\n")
        for item in unlisted:
            print(f"  - {item}")
        print()
        print("Consider adding these to the SYMLINKS array for consistency.")
        print()

    if has_errors:
        return 1
    else:
        print("OK: All container executables have valid symlinks in jib-container/bin/")
        return 0


if __name__ == "__main__":
    sys.exit(main())
