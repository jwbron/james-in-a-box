#!/usr/bin/env python3
"""
Comment Responder Service - Respond to comments and review feedback on PRs.

This service handles:
- Comments on PRs where jib is the author
- Comments on PRs where jib is assigned
- Comments on PRs where jib is mentioned (@james-in-a-box)
- Review feedback on jib's PRs (pr_review_response)

Runs as part of the github-watcher dispatcher.
"""

import sys
from pathlib import Path

# Add project paths
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root))

from jib_logging import ContextScope, get_logger

from gwlib.config import load_config
from gwlib.detection import check_pr_for_comments, check_pr_for_review_response, is_jib_engaged
from gwlib.github_api import check_gh_auth, gh_json
from gwlib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from gwlib.tasks import JibTask, execute_tasks_parallel

logger = get_logger("comment-responder")


def collect_comment_tasks(
    repo: str,
    state: dict,
    github_username: str,
    bot_username: str,
    since_timestamp: str | None,
) -> list[JibTask]:
    """Collect comment response tasks for a repository.

    Args:
        repo: Repository in owner/repo format
        state: State dict for deduplication
        github_username: User's GitHub username
        bot_username: Bot's username
        since_timestamp: Filter comments newer than this

    Returns:
        List of JibTask objects
    """
    tasks: list[JibTask] = []

    # Fetch all open PRs
    all_prs = gh_json(
        ["pr", "list", "--repo", repo, "--state", "open", "--json",
         "number,title,url,headRefName,baseRefName,headRefOid,author,assignees"],
        repo=repo,
    )

    if all_prs is None:
        logger.warning("Failed to fetch PRs", repo=repo)
        return tasks

    for pr in all_prs:
        pr_num = pr["number"]

        # Fetch comments to check for mentions
        comments_data = gh_json(
            ["pr", "view", str(pr_num), "--repo", repo, "--json", "comments,reviews"],
            repo=repo,
        )
        all_comments = []
        if comments_data:
            for c in comments_data.get("comments", []):
                all_comments.append({"body": c.get("body", "")})
            for r in comments_data.get("reviews", []):
                if r.get("body"):
                    all_comments.append({"body": r.get("body", "")})

        # Only process PRs where jib is engaged
        if not is_jib_engaged(pr, bot_username, all_comments):
            continue

        # Check for comments
        comment_ctx = check_pr_for_comments(repo, pr, state, bot_username, github_username, since_timestamp)
        if comment_ctx:
            tasks.append(JibTask(
                task_type="comment",
                context=comment_ctx,
                signature_key="processed_comments",
                signature_value=comment_ctx["comment_signature"],
                is_readonly=False,
            ))

        # Check for review responses (only on bot's PRs)
        author = pr.get("author", {}).get("login", "").lower()
        bot_variants = {bot_username.lower(), f"{bot_username.lower()}[bot]"}
        if author in bot_variants:
            review_ctx = check_pr_for_review_response(repo, pr, state, bot_username, github_username, since_timestamp)
            if review_ctx:
                tasks.append(JibTask(
                    task_type="pr_review_response",
                    context=review_ctx,
                    signature_key="processed_review_responses",
                    signature_value=review_ctx["review_response_signature"],
                    is_readonly=False,
                ))

    return tasks


def main() -> int:
    """Main entry point for comment responder service."""
    current_run_start = utc_now_iso()
    logger.info("Comment Responder starting", utc_time=current_run_start)

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
    since_timestamp = state.get("last_run_start")

    all_tasks: list[JibTask] = []

    for repo in writable_repos:
        with ContextScope(repository=repo, service="comment-responder"):
            tasks = collect_comment_tasks(repo, state, github_username, bot_username, since_timestamp)
            all_tasks.extend(tasks)

    if all_tasks:
        logger.info("Comment tasks collected", count=len(all_tasks))
        safe_state = ThreadSafeState(state)
        completed = execute_tasks_parallel(all_tasks, safe_state)
        state = safe_state.get_state()
        logger.info("Comment tasks completed", completed=completed, total=len(all_tasks))
    else:
        logger.info("No comment tasks to execute")

    state["last_run_start"] = current_run_start
    save_state(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
