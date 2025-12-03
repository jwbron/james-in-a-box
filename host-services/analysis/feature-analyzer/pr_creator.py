#!/usr/bin/env python3
"""
PR Creator - Automated Pull Request Creation (Phase 3-4)

This module creates GitHub PRs with documentation updates. It:
1. Creates a branch with the documentation changes
2. Commits the changes with proper traceability
3. Creates a PR via GitHub MCP or gh CLI
4. Creates git tags for audit trail (Phase 4)
5. Returns the PR URL for tracking

The PR includes:
- Summary of what ADR triggered the update
- List of documents updated
- Diff summary
- Test plan checklist
- Traceability to the original ADR

Phase 4 additions:
- Git tagging: auto-doc-sync-YYYYMMDD for traceability
- Query support: git log --tags='auto-doc-sync-*'

Usage:
    creator = PRCreator(repo_root)
    pr_url = creator.create_doc_sync_pr(adr_metadata, updates)
"""

import contextlib
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING


# Add host-services shared modules to path for jib_exec
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from git_utils import get_repo_name_from_remote
from jib_exec import jib_exec


# Processor for GitHub operations via jib (in PATH via /opt/jib-runtime/bin)
ANALYSIS_PROCESSOR = "analysis-processor"


if TYPE_CHECKING:
    from doc_generator import GeneratedUpdate


@dataclass
class PRResult:
    """Result of PR creation."""

    success: bool
    pr_url: str | None = None
    pr_number: int | None = None
    branch_name: str | None = None
    tag_name: str | None = None  # Phase 4: Git tag for traceability
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

    def _get_repo_name(self) -> str | None:
        """Get the full repo name (owner/repo) from git remote."""
        return get_repo_name_from_remote(self.repo_root)

    def _get_current_branch(self) -> str:
        """Get the current git branch name."""
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip()

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists (local or remote)."""
        result = self._run_git("show-ref", "--verify", f"refs/heads/{branch_name}", check=False)
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

    def _create_tag(self, tag_name: str, message: str) -> bool:
        """
        Create a git tag for traceability (Phase 4).

        Tags commits containing auto-generated content for easy querying:
            git log --tags='auto-doc-sync-*'
        """
        try:
            self._run_git("tag", "-a", tag_name, "-m", message)
            return True
        except subprocess.CalledProcessError as e:
            print(f"    Warning: Failed to create tag: {e.stderr}")
            return False

    def _push_tag(self, tag_name: str) -> bool:
        """Push a tag to origin."""
        try:
            self._run_git("push", "origin", tag_name)
            return True
        except subprocess.CalledProcessError as e:
            print(f"    Warning: Failed to push tag: {e.stderr}")
            return False

    def _generate_tag_name(self) -> str:
        """
        Generate a tag name for auto-doc-sync commits (Phase 4).

        Format: auto-doc-sync-YYYYMMDD[-N]
        Adds suffix if tag already exists on that date.
        """
        base_tag = f"auto-doc-sync-{datetime.now(UTC).strftime('%Y%m%d')}"

        # Check if tag exists
        result = self._run_git("tag", "-l", f"{base_tag}*", check=False)
        existing_tags = result.stdout.strip().split("\n") if result.stdout.strip() else []

        if base_tag not in existing_tags:
            return base_tag

        # Find next available suffix
        suffix = 2
        while f"{base_tag}-{suffix}" in existing_tags:
            suffix += 1
        return f"{base_tag}-{suffix}"

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
        """Create a PR using jib container's gh CLI (jib identity).

        Uses jib_exec to invoke the github_pr_create task in the container,
        which uses the GITHUB_TOKEN (GitHub App token) so PRs are created
        as jib rather than the host user.
        """
        # Get repo name from git remote
        repo = self._get_repo_name()
        if not repo:
            return PRResult(
                success=False,
                branch_name=branch_name,
                error="Could not determine repository name from git remote",
            )

        # Create PR via jib container
        result = jib_exec(
            ANALYSIS_PROCESSOR,
            "github_pr_create",
            {
                "repo": repo,
                "title": title,
                "body": body,
                "head": branch_name,
                "base": base,
            },
        )

        if result.success and result.json_output:
            return PRResult(
                success=True,
                pr_url=result.json_output.get("pr_url"),
                pr_number=result.json_output.get("pr_number"),
                branch_name=branch_name,
            )

        return PRResult(
            success=False,
            branch_name=branch_name,
            error=result.error or "jib github_pr_create failed",
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
        create_tag: bool = True,
        custom_pr_body: str | None = None,
    ) -> PRResult:
        """
        Create a PR with documentation updates.

        Args:
            adr_title: Title of the ADR
            adr_path: Path to the ADR file
            updates: List of generated documentation updates
            dry_run: If True, don't actually create the PR
            create_tag: If True, create git tag for traceability (Phase 4)
            custom_pr_body: Optional custom PR body (overrides default template)

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
        adr_slug = adr_slug.replace("adr-", "").replace("_", "-")
        # Remove any special characters that might cause issues in branch names
        adr_slug = re.sub(r"[^a-z0-9-]", "", adr_slug)[:40]
        timestamp = datetime.now(UTC).strftime("%Y%m%d")
        branch_name = f"docs/sync-{adr_slug}-{timestamp}"

        # Handle dry run
        if dry_run:
            tag_name = self._generate_tag_name() if create_tag else None
            print("  [DRY RUN] Would create PR:")
            print(f"    Branch: {branch_name}")
            if tag_name:
                print(f"    Tag: {tag_name}")
            print(f"    Files: {len(valid_updates)}")
            for update in valid_updates:
                rel_path = update.doc_path.relative_to(self.repo_root)
                print(f"      - {rel_path}")
            return PRResult(
                success=True,
                branch_name=branch_name,
                tag_name=tag_name,
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
            print("  Committing changes...")
            if not self._commit_changes(written_files, adr_title, adr_path):
                return PRResult(
                    success=False,
                    error="Failed to commit changes",
                )

            # Create git tag for traceability (Phase 4)
            tag_name = None
            if create_tag:
                tag_name = self._generate_tag_name()
                tag_message = f"Auto-generated documentation sync for {adr_title}"
                print(f"  Creating tag: {tag_name}")
                self._create_tag(tag_name, tag_message)

            # Push branch
            print("  Pushing branch to origin...")
            if not self._push_branch(branch_name):
                return PRResult(
                    success=False,
                    branch_name=branch_name,
                    tag_name=tag_name,
                    error="Failed to push branch. Changes committed locally.",
                )

            # Push tag if created
            if tag_name:
                print(f"  Pushing tag: {tag_name}")
                self._push_tag(tag_name)  # Non-fatal if fails

            # Create PR body - use custom body if provided, otherwise generate default
            if custom_pr_body:
                pr_body = custom_pr_body
            else:
                # Note: We use relative path format that works in GitHub PR context
                pr_body = f"""## Summary

Updates documentation to reflect implemented ADR: {adr_title}

### ADR Context

**ADR:** `{adr_path}` (see Files changed for full context)
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
            print("  Creating PR...")

            result = self._create_pr_with_gh(branch_name, pr_title, pr_body)

            # Add tag_name to result
            result.tag_name = tag_name

            return result

        except Exception as e:
            return PRResult(
                success=False,
                branch_name=branch_name,
                tag_name=tag_name if "tag_name" in dir() else None,
                error=f"Unexpected error: {e}",
            )

        finally:
            # Return to original branch
            with contextlib.suppress(Exception):
                self._run_git("checkout", original_branch, check=False)


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

    print("\nPR Creation Result:")
    print(f"  Success: {result.success}")
    print(f"  Branch: {result.branch_name}")
    print(f"  PR URL: {result.pr_url}")
    if result.error:
        print(f"  Error: {result.error}")


if __name__ == "__main__":
    main()
