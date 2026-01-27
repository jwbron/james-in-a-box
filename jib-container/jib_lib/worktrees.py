"""Git worktree management for jib.

This module handles creating and cleaning up git worktrees
for container isolation.
"""

import errno
import fcntl
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from .config import Config, get_local_repos
from .output import info, success, warn, get_quiet_mode


def get_default_branch(repo_path: Path) -> str:
    """Get the default branch (main or master) for a git repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        The default branch name ('main' or 'master'), or 'main' as fallback
    """
    # Try to get the default branch from git config (set by clone)
    result = subprocess.run(
        ["git", "config", "--get", "init.defaultBranch"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Check if origin/HEAD exists and points to a branch
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        # Format: refs/remotes/origin/main -> main
        return result.stdout.strip().split("/")[-1]

    # Fall back to checking which branches exist
    for branch in ["main", "master"]:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return branch

    # Default to 'main' if nothing found
    return "main"


def _acquire_git_lock(repo_path: Path, timeout: float = 30.0) -> Optional[int]:
    """Acquire an exclusive lock for git operations on a repository.

    Git doesn't handle concurrent operations well. When multiple jib --exec
    containers try to create worktrees simultaneously, they can conflict on
    the same repo's config/index files. This function provides file-based
    locking to serialize git operations per repository.

    Args:
        repo_path: Path to the git repository
        timeout: Maximum time to wait for lock in seconds

    Returns:
        File descriptor for the lock (must be closed to release), or None if failed
    """
    # Create lock file in the repo's .git directory
    git_dir = repo_path / ".git"
    if git_dir.is_file():
        # Worktree - read the actual git dir path
        try:
            content = git_dir.read_text().strip()
            if content.startswith("gitdir:"):
                git_dir = Path(content[7:].strip())
        except Exception:
            pass

    if not git_dir.is_dir():
        return None

    lock_file = git_dir / ".jib-worktree-lock"

    start_time = time.time()
    retry_delay = 0.1

    while True:
        try:
            # Open lock file (create if doesn't exist)
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR)

            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Got the lock
            return fd

        except (OSError, IOError) as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                # Lock held by another process
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    warn(f"Timeout waiting for git lock on {repo_path.name}")
                    if 'fd' in locals():
                        os.close(fd)
                    return None

                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 1.0)  # Exponential backoff, max 1s
                continue
            else:
                # Other error
                if 'fd' in locals():
                    os.close(fd)
                return None


def _release_git_lock(fd: int) -> None:
    """Release a git lock acquired with _acquire_git_lock."""
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception:
            pass


def create_worktrees(container_id: str) -> dict:
    """Create git worktrees for all configured local repositories.

    Worktrees are always based on the default branch (main or master),
    regardless of what branch is currently checked out on the host.

    Uses file-based locking to prevent conflicts when multiple jib --exec
    containers try to create worktrees simultaneously.

    Returns:
        Dictionary mapping repo paths to (worktree_path, repo_name) tuples
    """
    quiet = get_quiet_mode()
    worktree_dir = Config.WORKTREE_BASE / container_id
    worktree_dir.mkdir(parents=True, exist_ok=True)

    worktrees = {}

    # Get configured local repositories
    local_repos = get_local_repos()
    if not local_repos:
        if not quiet:
            info("No local repositories configured. Run ./setup.py to add repositories.")
        return worktrees

    # Iterate through configured repos
    for repo_path in local_repos:
        if not repo_path.is_dir():
            continue

        # Check if it's a git repository with a .git DIRECTORY or file
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            warn(f"  ✗ {repo_path.name} is not a git repository, skipping")
            continue

        repo_name = repo_path.name

        # Note: git worktree add works even when source repo is a worktree
        # It creates a new worktree of the same underlying main repository
        worktree_path = worktree_dir / repo_name

        # Acquire lock to prevent concurrent git operations on same repo
        lock_fd = _acquire_git_lock(repo_path, timeout=60.0)
        if lock_fd is None:
            warn(f"  ✗ Could not acquire lock for {repo_name}, skipping worktree")
            continue

        try:
            # Determine the default branch for this repo
            default_branch = get_default_branch(repo_path)

            if not quiet:
                info(f"Creating worktree for {repo_name} (from {default_branch})...")

            # Create temporary branch for this container, starting from the default branch
            branch_name = f"jib-temp-{container_id}"

            # Create worktree based on the default branch (not current HEAD)
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-b", branch_name, default_branch],
                cwd=repo_path,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Store both worktree path and original repo path for cleanup
                worktrees[repo_name] = {"worktree": worktree_path, "source": repo_path}
                if not quiet:
                    success(f"  ✓ {repo_name} -> {worktree_path}")
            else:
                warn(f"  ✗ Failed to create worktree for {repo_name}: {result.stderr}")

        except Exception as e:
            warn(f"  ✗ Error creating worktree for {repo_name}: {e}")
        finally:
            _release_git_lock(lock_fd)

    return worktrees


def cleanup_worktrees(container_id: str) -> None:
    """Clean up worktrees for a container

    Args:
        container_id: Unique container identifier
    """
    quiet = get_quiet_mode()
    worktree_dir = Config.WORKTREE_BASE / container_id

    if not worktree_dir.exists():
        return

    if not quiet:
        info(f"Cleaning up worktrees for {container_id}...")

    # Get configured local repositories for cleanup
    local_repos = get_local_repos()
    local_repos_by_name = {repo.name: repo for repo in local_repos}

    # Collect repos and their worktree admin directories
    # We need to forcibly remove admin dirs because container modified .git files
    # to point to container-only paths, which breaks git worktree prune
    repos_to_clean = {}  # repo_path -> list of admin dir names
    for worktree_path in worktree_dir.iterdir():
        if worktree_path.is_dir():
            repo_name = worktree_path.name
            original_repo = local_repos_by_name.get(repo_name)
            if original_repo and original_repo.exists():
                # Find the admin directory name from the worktree's .git file
                git_file = worktree_path / ".git"
                if git_file.is_file():
                    try:
                        content = git_file.read_text().strip()
                        # Format: "gitdir: /path/to/.git/worktrees/NAME" or
                        # "gitdir: /path/to/.git-main/repo/worktrees/NAME"
                        if "worktrees/" in content:
                            admin_name = content.split("worktrees/")[-1]
                            if original_repo not in repos_to_clean:
                                repos_to_clean[original_repo] = []
                            repos_to_clean[original_repo].append(admin_name)
                    except Exception:
                        pass

    # Remove container worktree directory first
    try:
        shutil.rmtree(worktree_dir)
        if not quiet:
            info(f"  ✓ Removed worktree directory")
    except Exception as e:
        warn(f"  ✗ Failed to remove directory {worktree_dir}: {e}")

    # Forcibly remove worktree admin directories
    # Don't rely on git worktree prune - it fails when .git files are corrupted
    admin_dirs_removed = 0
    for repo_path, admin_names in repos_to_clean.items():
        worktrees_dir = repo_path / ".git" / "worktrees"
        if worktrees_dir.is_dir():
            for admin_name in admin_names:
                admin_dir = worktrees_dir / admin_name
                if admin_dir.exists():
                    try:
                        shutil.rmtree(admin_dir)
                        admin_dirs_removed += 1
                    except Exception as e:
                        warn(f"  ✗ Failed to remove admin dir {admin_dir}: {e}")

    # Also run git worktree prune as a fallback for any we missed
    for repo_path in repos_to_clean.keys():
        try:
            subprocess.run(
                ["git", "worktree", "prune", "-v"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False  # Don't fail if prune has issues
            )
        except Exception:
            pass

    if admin_dirs_removed > 0 and not quiet:
        info(f"  ✓ Removed {admin_dirs_removed} worktree admin dir(s)")
        info(f"  Commits preserved on branch: jib-temp-{container_id}")
