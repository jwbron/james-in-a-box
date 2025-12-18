#!/usr/bin/env python3
"""
Automatically create symlinks to Confluence documentation in all git projects in the workspace.
"""

import os
import sys
from pathlib import Path

from connectors.confluence.config import ConfluenceConfig
from dotenv import load_dotenv


# Default workspace directory - can be overridden via WORKSPACE_DIR env var
DEFAULT_WORKSPACE_DIR = "workspace"


def get_workspace_path() -> Path:
    """Get the workspace path, defaulting to ~/workspace or using WORKSPACE_DIR env var."""
    workspace_name = os.environ.get("WORKSPACE_DIR", DEFAULT_WORKSPACE_DIR)
    return Path.home() / workspace_name


def find_git_projects(base_path: str) -> list[Path]:
    """Find all git projects under the given path."""
    base = Path(base_path)
    if not base.exists():
        print(f"Error: Base path does not exist: {base}")
        return []

    git_projects = []
    current_project = Path.cwd().resolve()

    # Walk through all directories under the base path
    for item in base.rglob(".git"):
        if item.is_dir():
            # The git project root is the parent of the .git directory
            project_root = item.parent.resolve()

            # Skip the current project (confluence-sync)
            if project_root == current_project:
                continue

            git_projects.append(project_root)

    return git_projects


def ensure_gitignore_pattern(link_name: str = "confluence-docs") -> bool:
    """Ensure the symlink pattern is in the global gitignore."""
    global_gitignore = Path.home() / ".gitignore"

    if not global_gitignore.exists():
        print(f"Creating global gitignore at {global_gitignore}")
        global_gitignore.write_text(f"# Confluence documentation symlinks\n{link_name}\n")
        return True

    gitignore_content = global_gitignore.read_text()
    pattern = f"{link_name}"

    if pattern in gitignore_content:
        return True

    # Add the pattern to the gitignore
    with open(global_gitignore, "a") as f:
        f.write(f"\n# Confluence documentation symlinks\n{pattern}\n")

    print(f"Added '{pattern}' to global gitignore at {global_gitignore}")
    return True


def ensure_cursor_rule(link_name: str = "confluence-docs") -> bool:
    """Ensure Cursor rule exists to guide AI behavior with confluence-docs directories."""
    cursor_rules_dir = Path.home() / ".cursor" / "rules"
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)

    rule_file = cursor_rules_dir / "confluence-docs.mdc"

    rule_content = f"""---
description: Use internal company documentation in confluence-docs directories to guide decision making and best practices
globs: ["**/{link_name}/**"]
alwaysApply: false
---

When working with confluence-docs directories:

- Use the internal company documentation to guide decision making and best practices
- Reference relevant documentation when making architectural decisions, choosing technologies, or implementing features
- Follow established patterns and guidelines documented in the confluence-docs
- Consult the documentation for coding standards, deployment procedures, and operational practices
- The confluence-docs contains authoritative internal knowledge - prioritize it over external sources when available
- When asked about best practices, architecture decisions, or coding standards, first check the confluence-docs for relevant guidance
- Use the documentation to understand company-specific patterns, conventions, and procedures
- Reference specific pages from confluence-docs when making recommendations or suggestions

The confluence-docs directory contains synced internal company documentation that should be used as the primary source for:
- Architectural decisions
- Technology choices
- Coding standards and conventions
- Deployment procedures
- Operational practices
- Company-specific patterns and guidelines
"""

    if rule_file.exists():
        existing_content = rule_file.read_text()
        if rule_content.strip() == existing_content.strip():
            return True

    rule_file.write_text(rule_content)
    print(f"Created Cursor rule at {rule_file}")
    print("  - AI will prioritize internal company documentation for decision making")
    print("  - Rule applies when working with confluence-docs directories")
    print("  - Documentation will guide architectural and technology decisions")
    return True


def create_symlinks_for_projects(link_name: str = "confluence-docs", dry_run: bool = False):
    """Create symlinks in all git projects in the workspace."""
    load_dotenv()
    config = ConfluenceConfig()

    # Ensure gitignore pattern and Cursor rule are set up
    if not dry_run:
        ensure_gitignore_pattern(link_name)
        ensure_cursor_rule(link_name)

    # Get the source documentation path
    source_path = Path(config.OUTPUT_DIR).resolve()
    if not source_path.exists():
        print(f"Error: Documentation not found at {source_path}")
        print("Run 'make docs-sync' first to sync documentation.")
        return False

    # Find all git projects under workspace
    workspace_path = get_workspace_path()
    git_projects = find_git_projects(workspace_path)

    if not git_projects:
        print(f"No git projects found under {workspace_path}")
        return False

    print(f"Found {len(git_projects)} git projects under {workspace_path}:")
    for project in git_projects:
        print(f"  - {project.name}")
    print()

    created_links = []
    skipped_links = []
    error_links = []

    for project in git_projects:
        symlink_path = project / link_name

        # Check if symlink already exists
        if symlink_path.exists():
            if symlink_path.is_symlink():
                try:
                    if symlink_path.resolve() == source_path:
                        skipped_links.append((project, "already linked"))
                    elif not dry_run:
                        symlink_path.unlink()
                        symlink_path.symlink_to(source_path)
                        created_links.append((project, "updated"))
                    else:
                        skipped_links.append((project, "would update"))
                except Exception as e:
                    error_links.append((project, f"error: {e}"))
            else:
                error_links.append((project, "exists but not a symlink"))
        elif not dry_run:
            try:
                symlink_path.symlink_to(source_path)
                created_links.append((project, "created"))
            except Exception as e:
                error_links.append((project, f"error: {e}"))
        else:
            created_links.append((project, "would create"))

    # Report results
    if created_links:
        print("Successfully created/updated symlinks:")
        for project, status in created_links:
            print(f"  - {project.name}: {status}")
        print()

    if skipped_links:
        print("Skipped (already linked):")
        for project, status in skipped_links:
            print(f"  - {project.name}: {status}")
        print()

    if error_links:
        print("Errors:")
        for project, error in error_links:
            print(f"  - {project.name}: {error}")
        print()

    if dry_run:
        print("This was a dry run. Use --execute to actually create the symlinks.")
    else:
        print(f"Confluence documentation is now available in {len(created_links)} projects!")
        print("Cursor will automatically index the documentation in each project.")

    return len(created_links) > 0 or len(skipped_links) > 0


def list_projects_with_links():
    """List projects that have symlinks to the documentation."""
    load_dotenv()
    config = ConfluenceConfig()

    source_path = Path(config.OUTPUT_DIR).resolve()
    if not source_path.exists():
        print("No synced documentation found.")
        return

    workspace_path = get_workspace_path()
    git_projects = find_git_projects(workspace_path)

    print(f"Projects with Confluence documentation symlinks (in {workspace_path}):")
    print("=" * 60)

    found_links = []

    for project in git_projects:
        # Look for symlinks in this project
        for item in project.iterdir():
            if item.is_symlink():
                try:
                    if item.resolve() == source_path:
                        found_links.append((project, item))
                except:
                    pass

    if found_links:
        for project, symlink in found_links:
            print(f"  {project.name}: {symlink.name}")
    else:
        print("  No symlinks found in workspace projects.")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python link_to_projects.py [--dry-run] [--execute] [--list]")
        print("  python link_to_projects.py --link-name docs [--execute]")
        print("  python link_to_projects.py --setup-cursor")
        print()
        print("Options:")
        print("  --dry-run     Show what would be done without creating symlinks")
        print("  --execute     Actually create the symlinks (default is dry-run)")
        print("  --list        List projects that already have symlinks")
        print("  --link-name   Custom name for the symlink (default: confluence-docs)")
        print("  --setup-cursor Create Cursor rule for confluence-docs directories")
        print()
        print("Environment Variables:")
        print("  WORKSPACE_DIR  Name of workspace directory under $HOME (default: workspace)")
        print()
        print("Examples:")
        print("  python link_to_projects.py --dry-run")
        print("  python link_to_projects.py --execute")
        print("  python link_to_projects.py --link-name docs --execute")
        print("  python link_to_projects.py --list")
        print("  python link_to_projects.py --setup-cursor")
        print("  WORKSPACE_DIR=projects python link_to_projects.py --execute")
        return

    # Parse arguments
    dry_run = "--execute" not in sys.argv
    list_mode = "--list" in sys.argv
    setup_cursor = "--setup-cursor" in sys.argv

    # Get custom link name if specified
    link_name = "confluence-docs"
    for i, arg in enumerate(sys.argv):
        if arg == "--link-name" and i + 1 < len(sys.argv):
            link_name = sys.argv[i + 1]

    if setup_cursor:
        ensure_cursor_rule(link_name)
    elif list_mode:
        list_projects_with_links()
    else:
        create_symlinks_for_projects(link_name, dry_run)


if __name__ == "__main__":
    main()
