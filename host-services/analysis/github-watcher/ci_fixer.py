#!/usr/bin/env python3
"""
CI/Conflict Fixer Service - Fix check failures and merge conflicts.

This service handles:
- Check failures on PRs authored by jib or the configured user
- Merge conflicts on PRs authored by jib or the configured user

This service is AUTOMATIC - it monitors all PRs from jib/user without
needing explicit assignment. This differs from the other services which
are opt-in.

Runs as part of the github-watcher dispatcher.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root))

from jib_logging import ContextScope, get_logger

from gwlib.config import load_config, should_disable_auto_fix
from gwlib.detection import check_pr_for_failures, check_pr_for_merge_conflict
from gwlib.github_api import check_gh_auth, gh_json
from gwlib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from gwlib.tasks import JibTask, execute_tasks_parallel

logger = get_logger("ci-fixer")


def collect_fix_tasks(
    repo: str,
    state: dict,
    github_username: str,
    bot_username: str,
) -> list[JibTask]:
    """Collect CI/conflict fix tasks for a repository.

    Only monitors PRs authored by the bot or configured user.

    Args:
        repo: Repository in owner/repo format
        state: State dict for deduplication
        github_username: User's GitHub username
        bot_username: Bot's username

    Returns:
        List of JibTask objects
    """
    tasks: list[JibTask] = []

    # Check if auto-fix is disabled for this repo
    if should_disable_auto_fix(repo):
        logger.debug("Auto-fix disabled for repo", repo=repo)
        return tasks

    # Fetch all open PRs
    all_prs = gh_json(
        ["pr", "list", "--repo", repo, "--state", "open", "--json",
         "number,title,url,headRefName,baseRefName,headRefOid,author"],
        repo=repo,
    )

    if all_prs is None:
        logger.warning("Failed to fetch PRs", repo=repo)
        return tasks

    # Filter to PRs authored by bot or configured user
    bot_variants = {bot_username.lower(), f"{bot_username.lower()}[bot]", f"app/{bot_username.lower()}"}
    allowed_authors = bot_variants | {github_username.lower()}

    eligible_prs = [
        p for p in all_prs
        if p.get("author", {}).get("login", "").lower() in allowed_authors
    ]

    if not eligible_prs:
        logger.debug("No PRs from bot or user", bot_username=bot_username, github_username=github_username)
        return tasks

    logger.info("Found eligible PRs for CI/conflict monitoring", count=len(eligible_prs))

    for pr in eligible_prs:
        # Check for failures
        failure_ctx = check_pr_for_failures(repo, pr, state)
        if failure_ctx:
            tasks.append(JibTask(
                task_type="check_failure",
                context=failure_ctx,
                signature_key="processed_failures",
                signature_value=failure_ctx["failure_signature"],
                is_readonly=False,
            ))

        # Check for merge conflicts
        conflict_ctx = check_pr_for_merge_conflict(repo, pr, state)
        if conflict_ctx:
            tasks.append(JibTask(
                task_type="merge_conflict",
                context=conflict_ctx,
                signature_key="processed_conflicts",
                signature_value=conflict_ctx["conflict_signature"],
                is_readonly=False,
            ))

    return tasks


def main() -> int:
    """Main entry point for CI/conflict fixer service."""
    current_run_start = utc_now_iso()
    logger.info("CI/Conflict Fixer starting", utc_time=current_run_start)

    if not check_gh_auth():
        return 1

    config = load_config()
    writable_repos = config.get("writable_repos", [])
    github_username = config.get("github_username", "jib")
    bot_username = config.get("bot_username", "jib")

    if not writable_repos:
        logger.warning("No writable repositories configured")
        return 0

    state = load_state()

    all_tasks: list[JibTask] = []

    for repo in writable_repos:
        with ContextScope(repository=repo, service="ci-fixer"):
            tasks = collect_fix_tasks(repo, state, github_username, bot_username)
            all_tasks.extend(tasks)

    if all_tasks:
        logger.info("Fix tasks collected", count=len(all_tasks))
        safe_state = ThreadSafeState(state)
        completed = execute_tasks_parallel(all_tasks, safe_state)
        state = safe_state.get_state()
        logger.info("Fix tasks completed", completed=completed, total=len(all_tasks))
    else:
        logger.info("No fix tasks to execute")

    state["last_run_start"] = current_run_start
    save_state(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
