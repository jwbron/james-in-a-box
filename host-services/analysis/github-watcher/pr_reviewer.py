#!/usr/bin/env python3
"""
PR Reviewer Service - Review PRs where jib is requested.

This service handles:
- PRs where jib is assigned as a reviewer
- PRs where jib is mentioned requesting review
- Re-reviews when new commits are pushed

Key change from current behavior:
- OLD: Proactively reviews ALL PRs from other authors
- NEW: Only reviews PRs where jib is explicitly assigned or tagged (opt-in)

Runs as part of the github-watcher dispatcher.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root))

from jib_logging import ContextScope, get_logger

from gwlib.config import load_config
from gwlib.detection import check_prs_for_review
from gwlib.github_api import check_gh_auth, gh_json
from gwlib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from gwlib.tasks import JibTask, execute_tasks_parallel

logger = get_logger("pr-reviewer")


def collect_review_tasks(
    repo: str,
    state: dict,
    github_username: str,
    bot_username: str,
    since_timestamp: str | None,
    is_readonly: bool = False,
) -> list[JibTask]:
    """Collect PR review tasks for a repository.

    Args:
        repo: Repository in owner/repo format
        state: State dict for deduplication
        github_username: User's GitHub username
        bot_username: Bot's username
        since_timestamp: Filter PRs created after this
        is_readonly: If True, output review to Slack instead of GitHub

    Returns:
        List of JibTask objects
    """
    # Fetch all open PRs
    all_prs = gh_json(
        ["pr", "list", "--repo", repo, "--state", "open", "--json",
         "number,title,url,headRefName,baseRefName,headRefOid,author,createdAt,additions,deletions,files"],
        repo=repo,
    )

    if all_prs is None:
        logger.warning("Failed to fetch PRs", repo=repo)
        return []

    # Use new opt-in behavior: require explicit assignment/tagging
    review_contexts = check_prs_for_review(
        repo, all_prs, state, github_username, bot_username, since_timestamp,
        is_readonly=is_readonly,
        require_explicit_request=True,  # KEY: This enables the new opt-in behavior
    )

    return [
        JibTask(
            task_type="review_request",
            context=ctx,
            signature_key="processed_reviews",
            signature_value=ctx["review_signature"],
            is_readonly=is_readonly,
        )
        for ctx in review_contexts
    ]


def main() -> int:
    """Main entry point for PR reviewer service."""
    current_run_start = utc_now_iso()
    logger.info("PR Reviewer starting", utc_time=current_run_start)

    if not check_gh_auth():
        return 1

    config = load_config()
    writable_repos = config.get("writable_repos", [])
    readable_repos = config.get("readable_repos", [])
    github_username = config.get("github_username", "jib")
    bot_username = config.get("bot_username", "jib")

    state = load_state()
    since_timestamp = state.get("last_run_start")

    all_tasks: list[JibTask] = []

    # Process writable repos (post reviews to GitHub)
    for repo in writable_repos:
        with ContextScope(repository=repo, service="pr-reviewer", access_level="writable"):
            tasks = collect_review_tasks(repo, state, github_username, bot_username, since_timestamp, is_readonly=False)
            all_tasks.extend(tasks)

    # Process readable repos (output to Slack)
    for repo in readable_repos:
        with ContextScope(repository=repo, service="pr-reviewer", access_level="readable"):
            tasks = collect_review_tasks(repo, state, github_username, bot_username, since_timestamp, is_readonly=True)
            all_tasks.extend(tasks)

    if all_tasks:
        logger.info("Review tasks collected", count=len(all_tasks))
        safe_state = ThreadSafeState(state)
        completed = execute_tasks_parallel(all_tasks, safe_state)
        state = safe_state.get_state()
        logger.info("Review tasks completed", completed=completed, total=len(all_tasks))
    else:
        logger.info("No review tasks to execute")

    state["last_run_start"] = current_run_start
    save_state(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
