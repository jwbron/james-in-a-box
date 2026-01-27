#!/usr/bin/env python3
"""Worktree Watcher - Clean up orphaned git worktrees and branches.

Runs periodically via systemd timer to prevent worktree/branch accumulation
from stopped or crashed jib containers.
"""

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Add shared module to path
SCRIPT_DIR = Path(__file__).parent.resolve()
JIB_REPO_DIR = SCRIPT_DIR.parent.parent.parent
SHARED_DIR = JIB_REPO_DIR / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from jib_config import get_local_repos


WORKTREE_BASE = Path.home() / ".jib-worktrees"


def log(message: str) -> None:
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_docker_containers() -> set[str]:
    """Get set of all docker container names (running and stopped)."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return set(result.stdout.strip().split("\n")) - {""}
    except Exception:
        pass
    return set()


def get_default_branch(repo_path: Path) -> str:
    """Get the default branch for a repository."""
    # Try symbolic ref first
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("/")[-1]

    # Fallback: query remote
    result = subprocess.run(
        ["git", "remote", "show", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        for line in result.stdout.split("\n"):
            if "HEAD branch" in line:
                return line.split(":")[-1].strip()

    return "main"


def get_github_repo(repo_path: Path) -> str | None:
    """Extract owner/repo from git remote URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    url = result.stdout.strip()
    # Match github.com:owner/repo or github.com/owner/repo
    match = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    if match:
        return match.group(1).removesuffix(".git")
    return None


def get_open_pr_branches(github_repo: str) -> set[str]:
    """Get set of branch names that have open PRs."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                github_repo,
                "--state",
                "open",
                "--json",
                "number,headRefName",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            prs = json.loads(result.stdout)
            return {pr["headRefName"] for pr in prs}
    except Exception:
        pass
    return set()


def count_unmerged_commits(repo_path: Path, branch: str, default_branch: str) -> int:
    """Count commits on branch not merged to default branch."""
    # Try origin/default_branch first
    for base in [f"origin/{default_branch}", default_branch]:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", base],
            cwd=repo_path,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            continue

        result = subprocess.run(
            ["git", "cherry", base, branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            # Count lines starting with '+' (unmerged commits)
            return sum(1 for line in result.stdout.split("\n") if line.startswith("+"))

    return 0


def cleanup_orphaned_worktrees() -> None:
    """Clean up worktree directories for containers that no longer exist."""
    log("Starting worktree cleanup check...")

    if not WORKTREE_BASE.exists():
        log(f"No worktrees directory found at {WORKTREE_BASE}")
        return

    # Build repo name -> path lookup
    repos = get_local_repos()
    repo_lookup = {repo.name: repo for repo in repos if repo.is_dir()}

    containers = get_docker_containers()
    total_checked = 0
    total_cleaned = 0

    for container_dir in WORKTREE_BASE.glob("jib-*"):
        if not container_dir.is_dir():
            continue

        total_checked += 1
        container_id = container_dir.name

        if container_id in containers:
            log(f"Container {container_id} still exists, keeping worktree")
            continue

        log(f"Orphaned worktree found: {container_id}")
        worktrees_removed = 0

        for worktree in container_dir.iterdir():
            if not worktree.is_dir():
                continue

            repo_name = worktree.name
            original_repo = repo_lookup.get(repo_name)

            if original_repo and (original_repo / ".git").exists():
                log(f"  Removing worktree: {repo_name}")
                result = subprocess.run(
                    ["git", "worktree", "remove", str(worktree), "--force"],
                    cwd=original_repo,
                    capture_output=True,
                    check=False,
                )
                if result.returncode == 0:
                    worktrees_removed += 1
                else:
                    log(f"  Warning: Could not remove worktree {worktree}")
            else:
                log(f"  Warning: Could not find original repo for {repo_name}")

        # Remove container directory
        log(f"  Removing directory: {container_dir}")
        try:
            shutil.rmtree(container_dir)
            log("  Successfully removed directory")
        except PermissionError:
            log("  Warning: Could not remove all files (permission denied)")
            log(f"  Manual cleanup may be needed: rm -rf {container_dir}")

        total_cleaned += 1
        log(f"  Cleaned up {worktrees_removed} worktree(s) for container {container_id}")

    log(
        f"Cleanup complete: checked {total_checked} container(s), "
        f"cleaned {total_cleaned} orphaned worktree(s)"
    )


def prune_stale_worktree_references() -> None:
    """Run git worktree prune on all configured repos."""
    log("Pruning stale worktree references...")

    repos_pruned = 0
    for repo in get_local_repos():
        if not (repo / ".git").exists():
            continue

        result = subprocess.run(
            ["git", "worktree", "prune", "-v"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if "Removing" in result.stdout or "Removing" in result.stderr:
            log(f"  Pruned stale references in {repo.name}")
            repos_pruned += 1

    if repos_pruned > 0:
        log(f"Pruned stale references in {repos_pruned} repo(s)")
    else:
        log("No stale references found")


def cleanup_orphaned_branches() -> None:
    """Delete jib-temp-* and jib-exec-* branches for containers that no longer exist."""
    log("Checking for orphaned jib-temp/jib-exec branches...")

    containers = get_docker_containers()
    total_deleted = 0
    total_skipped = 0

    for repo in get_local_repos():
        if not (repo / ".git").exists():
            continue

        # Get jib branches
        result = subprocess.run(
            ["git", "branch", "--list", "jib-temp-*", "jib-exec-*"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            continue

        branches = [b.strip().lstrip("* ") for b in result.stdout.split("\n") if b.strip()]
        if not branches:
            continue

        default_branch = get_default_branch(repo)
        github_repo = get_github_repo(repo)
        open_pr_branches = get_open_pr_branches(github_repo) if github_repo else set()

        repo_deleted = 0

        for branch in branches:
            # Extract container ID from branch name
            if branch.startswith("jib-temp-"):
                container_id = branch[9:]  # Remove "jib-temp-" prefix
            elif branch.startswith("jib-exec-"):
                container_id = branch  # jib-exec branches use full name as container ID
            else:
                continue

            # Skip if container still exists
            if container_id in containers:
                continue

            # Skip if worktree directory still exists
            worktree_dir = WORKTREE_BASE / container_id
            if worktree_dir.exists():
                continue

            # Check for unmerged commits
            unmerged = count_unmerged_commits(repo, branch, default_branch)
            has_open_pr = branch in open_pr_branches

            # Only delete if: no unmerged changes OR has an open PR
            if unmerged > 0 and not has_open_pr:
                log(
                    f"  Keeping branch {branch} in {repo.name}: "
                    f"has {unmerged} unmerged commit(s) and no open PR"
                )
                total_skipped += 1
                continue

            # Safe to delete
            reason = "no unmerged changes" if unmerged == 0 else "has open PR"
            log(f"  Deleting orphaned branch in {repo.name}: {branch} ({reason})")

            result = subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=repo,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                repo_deleted += 1
                total_deleted += 1
            else:
                log(f"  Warning: Could not delete branch {branch}")

        if repo_deleted > 0:
            log(f"  Deleted {repo_deleted} branch(es) in {repo.name}")

    if total_deleted > 0 or total_skipped > 0:
        log(
            f"Branch cleanup complete: deleted {total_deleted}, "
            f"skipped {total_skipped} (have unmerged changes without PR)"
        )
    else:
        log("No orphaned branches found")


def main() -> None:
    """Run all cleanup tasks."""
    cleanup_orphaned_worktrees()
    prune_stale_worktree_references()
    cleanup_orphaned_branches()


if __name__ == "__main__":
    main()
