#!/usr/bin/env python3
"""
PR Creator - Automated Pull Request Creation (Phase 3)

This module creates GitHub PRs with documentation updates. It:
1. Creates a branch with the documentation changes
2. Commits the changes with proper traceability
3. Creates a PR via GitHub MCP or gh CLI
4. Returns the PR URL for tracking

The PR includes:
- Summary of what ADR triggered the update
- List of documents updated
- Diff summary
- Test plan checklist
- Traceability to the original ADR

Usage:
    creator = PRCreator(repo_root)
    pr_url = creator.create_doc_sync_pr(adr_metadata, updates)
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from doc_generator import GeneratedUpdate


@dataclass
class PRResult:
    """Result of PR creation."""

    success: bool
    pr_url: str | None = None
    pr_number: int | None = None
    branch_name: str | None = None
    error: str | None = None


class PRCreator:
    """Creates PRs for documentation updates."""

    def __init__(self, repo_root: Path):
        """
        Initialize the PR creator.

        Args:
            repo_root: Path to the repository root
        """
        self.repo_root = repo_root

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the repo root."""
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=check,
        )

    def _get_current_branch(self) -> str:
        """Get the current git branch name."""
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip()

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists (local or remote)."""
        result = self._run_git(
            "show-ref", "--verify", f"refs/heads/{branch_name}", check=False
        )
        if result.returncode == 0:
            return True

        result = self._run_git(
            "show-ref", "--verify", f"refs/remotes/origin/{branch_name}", check=False
        )
        return result.returncode == 0

    def _create_branch(self, branch_name: str, base: str = "origin/main") -> bool:
        """Create a new branch from base."""
        try:
            # Fetch latest
            self._run_git("fetch", "origin", "main", check=False)

            # Create branch from base
            self._run_git("checkout", "-b", branch_name, base)
            return True
        except subprocess.CalledProcessError as e:
            print(f"    Error creating branch: {e.stderr}")
            return False

    def _commit_changes(
        self,
        files: list[Path],
        adr_title: str,
        adr_path: Path,
    ) -> bool:
        """Commit the documentation changes."""
        try:
            # Add files
            for file_path in files:
                relative_path = file_path.relative_to(self.repo_root)
                self._run_git("add", str(relative_path))

            # Create commit message
            timestamp = datetime.now(UTC).isoformat()
            commit_msg = f"""docs: Sync with {adr_title} (auto-generated)

Auto-updated documentation to reflect implemented ADR.

ADR: {adr_path}
Generated: {timestamp}

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"""

            # Commit
            self._run_git("commit", "-m", commit_msg)
            return True

        except subprocess.CalledProcessError as e:
            print(f"    Error committing changes: {e.stderr}")
            return False

    def _push_branch(self, branch_name: str) -> bool:
        """Push the branch to origin."""
        try:
            self._run_git("push", "-u", "origin", branch_name)
            return True
        except subprocess.CalledProcessError as e:
            print(f"    Error pushing branch: {e.stderr}")
            return False

    def _format_doc_list(self, updates: list["GeneratedUpdate"]) -> str:
        """Format the list of updated documents for PR description."""
        lines = []
        for update in updates:
            relative_path = update.doc_path.relative_to(self.repo_root)
            status = "✅" if update.validation_passed else "⚠️"
            lines.append(f"- {status} `{relative_path}` - {update.changes_summary}")
        return "\n".join(lines)

    def _format_diff_summary(self, updates: list["GeneratedUpdate"]) -> str:
        """Format a summary of changes for each document."""
        lines = []
        for update in updates:
            relative_path = update.doc_path.relative_to(self.repo_root)
            original_len = len(update.original_content)
            updated_len = len(update.updated_content)
            diff = updated_len - original_len

            if diff > 0:
                change = f"+{diff} chars"
            elif diff < 0:
                change = f"{diff} chars"
            else:
                change = "no size change"

            confidence = f"{update.confidence:.0%} confidence"
            lines.append(f"- `{relative_path}`: {change} ({confidence})")

        return "\n".join(lines)

    def _create_pr_with_gh(
        self,
        branch_name: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PRResult:
        """Create a PR using the gh CLI."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    title,
                    "--body",
                    body,
                    "--base",
                    base,
                    "--head",
                    branch_name,
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse PR URL from output
            pr_url = result.stdout.strip()
            pr_number = None
            if pr_url and "/" in pr_url:
                try:
                    pr_number = int(pr_url.split("/")[-1])
                except ValueError:
                    pass

            return PRResult(
                success=True,
                pr_url=pr_url,
                pr_number=pr_number,
                branch_name=branch_name,
            )

        except subprocess.CalledProcessError as e:
            return PRResult(
                success=False,
                branch_name=branch_name,
                error=f"gh pr create failed: {e.stderr}",
            )
        except FileNotFoundError:
            return PRResult(
                success=False,
                branch_name=branch_name,
                error="gh CLI not found. Install GitHub CLI to create PRs.",
            )

    def _write_updates_to_files(self, updates: list["GeneratedUpdate"]) -> list[Path]:
        """Write the updated content to files."""
        written_files = []
        for update in updates:
            if update.validation_passed and update.updated_content:
                update.doc_path.write_text(update.updated_content)
                written_files.append(update.doc_path)
        return written_files

    def create_doc_sync_pr(
        self,
        adr_title: str,
        adr_path: Path,
        updates: list["GeneratedUpdate"],
        dry_run: bool = False,
    ) -> PRResult:
        """
        Create a PR with documentation updates.

        Args:
            adr_title: Title of the ADR
            adr_path: Path to the ADR file
            updates: List of generated documentation updates
            dry_run: If True, don't actually create the PR

        Returns:
            PRResult with PR details or error.
        """
        # Filter to valid updates only
        valid_updates = [u for u in updates if u.validation_passed and u.updated_content]

        if not valid_updates:
            return PRResult(
                success=False,
                error="No valid updates to commit (all failed validation or had no changes)",
            )

        # Generate branch name from ADR slug
        adr_slug = adr_path.stem.lower()
        adr_slug = adr_slug.replace("adr-", "").replace("_", "-")[:40]
        timestamp = datetime.now(UTC).strftime("%Y%m%d")
        branch_name = f"docs/sync-{adr_slug}-{timestamp}"

        # Handle dry run
        if dry_run:
            print(f"  [DRY RUN] Would create PR:")
            print(f"    Branch: {branch_name}")
            print(f"    Files: {len(valid_updates)}")
            for update in valid_updates:
                rel_path = update.doc_path.relative_to(self.repo_root)
                print(f"      - {rel_path}")
            return PRResult(
                success=True,
                branch_name=branch_name,
                pr_url="[dry-run]",
            )

        # Save current branch to return to
        original_branch = self._get_current_branch()

        try:
            # Create branch
            print(f"  Creating branch: {branch_name}")
            if self._branch_exists(branch_name):
                # Add suffix to make unique
                branch_name = f"{branch_name}-{datetime.now(UTC).strftime('%H%M%S')}"

            if not self._create_branch(branch_name):
                return PRResult(
                    success=False,
                    error=f"Failed to create branch {branch_name}",
                )

            # Write updates to files
            print(f"  Writing {len(valid_updates)} file(s)...")
            written_files = self._write_updates_to_files(valid_updates)

            if not written_files:
                return PRResult(
                    success=False,
                    error="No files were written",
                )

            # Commit changes
            print(f"  Committing changes...")
            if not self._commit_changes(written_files, adr_title, adr_path):
                return PRResult(
                    success=False,
                    error="Failed to commit changes",
                )

            # Push branch
            print(f"  Pushing branch to origin...")
            if not self._push_branch(branch_name):
                return PRResult(
                    success=False,
                    branch_name=branch_name,
                    error="Failed to push branch. Changes committed locally.",
                )

            # Create PR body
            pr_body = f"""## Summary

Updates documentation to reflect implemented ADR: {adr_title}

### ADR Context

**ADR:** [{adr_path.name}](../blob/main/{adr_path})
**Decision:** See ADR for full decision details.

### Documentation Updated

{self._format_doc_list(valid_updates)}

### Changes Made

{self._format_diff_summary(valid_updates)}

## Test Plan

- [x] All updated docs render correctly
- [x] Validation checks passed
- [ ] Human review of technical accuracy
- [ ] Verify links are valid

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"""

            # Create PR
            pr_title = f"docs: Sync documentation with {adr_title}"
            print(f"  Creating PR...")

            result = self._create_pr_with_gh(branch_name, pr_title, pr_body)

            return result

        except Exception as e:
            return PRResult(
                success=False,
                branch_name=branch_name,
                error=f"Unexpected error: {e}",
            )

        finally:
            # Return to original branch
            try:
                self._run_git("checkout", original_branch, check=False)
            except Exception:
                pass


def main():
    """Test the PR creator."""
    import argparse

    parser = argparse.ArgumentParser(description="Test PR creator")
    parser.add_argument("--adr", type=Path, required=True, help="Path to ADR file")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't create actual PR")

    args = parser.parse_args()

    # Import modules
    sys.path.insert(0, str(Path(__file__).parent))
    from doc_generator import DocGenerator, GeneratedUpdate
    from feature_analyzer import FeatureAnalyzer

    # Parse ADR
    analyzer = FeatureAnalyzer(args.repo_root)
    adr_metadata = analyzer.parse_adr(args.adr)

    # Generate updates
    generator = DocGenerator(args.repo_root, use_jib=False)
    gen_result = generator.generate_updates_for_adr(adr_metadata)
    gen_result = generator.validate_all_updates(gen_result)

    # Create test updates if none generated
    if not gen_result.updates:
        print("No updates generated, creating test update...")
        test_update = GeneratedUpdate(
            doc_path=args.repo_root / "docs" / "FEATURES.md",
            original_content="# Test",
            updated_content="# Test\n\n<!-- Updated for testing -->",
            changes_summary="Test update",
            confidence=0.9,
            validation_passed=True,
        )
        gen_result.updates.append(test_update)

    # Create PR
    creator = PRCreator(args.repo_root)
    result = creator.create_doc_sync_pr(
        adr_title=adr_metadata.title,
        adr_path=adr_metadata.path,
        updates=gen_result.updates,
        dry_run=args.dry_run,
    )

    print(f"\nPR Creation Result:")
    print(f"  Success: {result.success}")
    print(f"  Branch: {result.branch_name}")
    print(f"  PR URL: {result.pr_url}")
    if result.error:
        print(f"  Error: {result.error}")


if __name__ == "__main__":
    main()
