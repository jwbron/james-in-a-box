#!/usr/bin/env python3
"""
Create symlinks to Confluence documentation in other projects.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from connectors.confluence.config import ConfluenceConfig


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


def create_symlink(target_project_path: str, link_name: str = "confluence-docs"):
    """Create a symlink to Confluence documentation in the specified project."""
    load_dotenv()
    config = ConfluenceConfig()
    
    # Ensure gitignore pattern and Cursor rule are set up
    ensure_gitignore_pattern(link_name)
    ensure_cursor_rule(link_name)
    
    # Get the source documentation path
    source_path = Path(config.OUTPUT_DIR).resolve()
    if not source_path.exists():
        print(f"Error: Documentation not found at {source_path}")
        print("Run 'make docs-sync' first to sync documentation.")
        return False
    
    # Get the target project path
    target_path = Path(target_project_path).resolve()
    if not target_path.exists():
        print(f"Error: Target project path does not exist: {target_path}")
        return False
    
    # Prevent creating symlink in the current project (confluence-sync)
    current_project = Path.cwd().resolve()
    if target_path == current_project:
        print(f"Skipping current project: {target_path.name}")
        print("   The confluence-sync project is the source of documentation.")
        return False
    
    # Create the symlink path
    symlink_path = target_path / link_name
    
    # Check if symlink already exists
    if symlink_path.exists():
        if symlink_path.is_symlink():
            try:
                if symlink_path.resolve() == source_path:
                    print(f"Symlink already exists and points to correct location: {symlink_path}")
                    return True
                else:
                    print(f"Symlink exists but points to wrong location. Updating...")
                    symlink_path.unlink()
                    symlink_path.symlink_to(source_path)
                    print(f"Updated symlink: {symlink_path}")
                    return True
            except Exception as e:
                print(f"Error updating symlink: {e}")
                return False
        else:
            print(f"Error: {symlink_path} exists but is not a symlink")
            return False
    else:
        try:
            symlink_path.symlink_to(source_path)
            print(f"Created symlink: {symlink_path}")
            print(f"   Points to: {source_path}")
            print(f"   Cursor will now index the documentation in this project!")
            return True
        except Exception as e:
            print(f"Error creating symlink: {e}")
            return False


def list_projects_with_symlinks():
    """List projects that have symlinks to the Confluence documentation."""
    load_dotenv()
    config = ConfluenceConfig()
    
    source_path = Path(config.OUTPUT_DIR).resolve()
    if not source_path.exists():
        print("No synced documentation found.")
        return
    
    print("Projects with Confluence documentation symlinks:")
    print("=" * 50)
    
    # Look for symlinks in common project locations
    search_paths = [
        Path.home() / "khan",
        Path.home() / "projects", 
        Path.home() / "workspace",
        Path.home() / "dev",
        Path.home() / "code"
    ]
    
    found_links = []
    current_project = Path.cwd().resolve()
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
            
        for project in search_path.iterdir():
            if project.is_dir():
                # Skip the current project (confluence-sync)
                if project.resolve() == current_project:
                    continue
                    
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
        print("  No symlinks found in common project locations.")


def main():
    """Main function for command line usage."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python create_symlink.py <project_path> [link_name]")
        print("  python create_symlink.py --list")
        print()
        print("Examples:")
        print("  python create_symlink.py ~/projects/my-app")
        print("  python create_symlink.py ~/workspace/backend docs")
        print("  python create_symlink.py --list")
        return
    
    if sys.argv[1] == "--list":
        list_projects_with_symlinks()
    else:
        target_project = sys.argv[1]
        link_name = sys.argv[2] if len(sys.argv) > 2 else "confluence-docs"
        create_symlink(target_project, link_name)


if __name__ == "__main__":
    main() 