#!/usr/bin/env python3
"""Detection logic for GitHub events (comments, reviews, failures, conflicts)."""

import subprocess

from jib_logging import get_logger

from .config import should_restrict_to_configured_users
from .github_api import gh_json, gh_text


logger = get_logger("github-detection")

# Maximum diff size to include in context
MAX_DIFF_SIZE = 50000

# Patterns indicating GitHub Actions billing exhaustion
BILLING_EXHAUSTION_PATTERNS = [
    "spending limit needs to be increased",
    "recent account payments have failed",
    "the job was not started because",
    "actions usage limit",
    "minutes quota",
]


def truncate_diff(diff: str, max_size: int = MAX_DIFF_SIZE) -> str:
    """Truncate diff at a line boundary."""
    if not diff or len(diff) <= max_size:
        return diff or ""
    return diff[:max_size].rsplit("\n", 1)[0]


def is_billing_exhaustion(failed_checks: list[dict], check_runs: list[dict]) -> bool:
    """Detect if check failures are due to GitHub Actions billing exhaustion."""
    for check in failed_checks:
        description = (check.get("description") or "").lower()
        for pattern in BILLING_EXHAUSTION_PATTERNS:
            if pattern in description:
                return True
        full_log = (check.get("full_log") or "").lower()
        for pattern in BILLING_EXHAUSTION_PATTERNS:
            if pattern in full_log:
                return True

    for run in check_runs:
        output = run.get("output", {})
        summary = (output.get("summary") or "").lower()
        for pattern in BILLING_EXHAUSTION_PATTERNS:
            if pattern in summary:
                return True

    if failed_checks:
        all_cancelled = all(c.get("state", "").upper() == "CANCELLED" for c in failed_checks)
        no_logs = all(not c.get("full_log") for c in failed_checks)
        if all_cancelled and no_logs and len(failed_checks) >= 2:
            return True

    return False


def is_jib_engaged(
    pr_data: dict, bot_username: str, all_comments: list[dict] | None = None
) -> bool:
    """Check if jib is assigned, tagged, or the author of a PR.

    Args:
        pr_data: PR data dict with author, assignees, reviewRequests
        bot_username: Bot's username to check for
        all_comments: Optional list of comments to check for mentions

    Returns:
        True if jib should be engaged with this PR
    """
    bot_lower = bot_username.lower()
    bot_variants = {bot_lower, f"{bot_lower}[bot]", f"app/{bot_lower}"}

    # Check if author
    author = pr_data.get("author", {}).get("login", "").lower()
    if author in bot_variants:
        return True

    # Check if assigned
    assignees = [a.get("login", "").lower() for a in pr_data.get("assignees", [])]
    if any(a in bot_variants for a in assignees):
        return True

    # Check if review requested
    review_requests = pr_data.get("reviewRequests", [])
    for req in review_requests:
        if req.get("__typename") == "User" and req.get("login", "").lower() in bot_variants:
            return True

    # Check if mentioned in comments
    if all_comments:
        mention_patterns = [f"@{bot_username}", f"@{bot_username.lower()}"]
        for comment in all_comments:
            body = comment.get("body", "")
            for pattern in mention_patterns:
                if pattern.lower() in body.lower():
                    return True

    return False


def is_user_directly_requested(pr_data: dict, github_username: str) -> bool:
    """Check if a user is directly requested as a reviewer (not via team)."""
    review_requests = pr_data.get("reviewRequests", [])
    for request in review_requests:
        if (
            request.get("__typename") == "User"
            and request.get("login", "").lower() == github_username.lower()
        ):
            return True
    return False


def check_pr_for_failures(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for check failures.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict
        state: State dict for deduplication

    Returns:
        Context dict if failures found, None otherwise
    """
    pr_num = pr_data["number"]
    head_sha = pr_data.get("headRefOid")

    if not head_sha:
        return None

    check_runs_response = gh_json(
        ["api", f"repos/{repo}/commits/{head_sha}/check-runs"],
        repo=repo,
    )

    if check_runs_response is None:
        return None

    check_runs = check_runs_response.get("check_runs", [])
    if not check_runs:
        return None

    failed_checks = [
        {
            "name": c.get("name", ""),
            "state": c.get("conclusion", "").upper(),
            "startedAt": c.get("started_at", ""),
            "completedAt": c.get("completed_at", ""),
            "link": c.get("html_url", ""),
            "description": c.get("output", {}).get("summary", ""),
            "workflow": c.get("app", {}).get("name", ""),
        }
        for c in check_runs
        if c.get("conclusion", "").lower() in ("failure", "cancelled", "timed_out")
    ]

    if not failed_checks:
        return None

    failed_names = sorted([c["name"] for c in failed_checks])
    failure_signature = f"{repo}-{pr_num}-{head_sha}:" + ",".join(failed_names)

    if failure_signature in state.get("processed_failures", {}):
        return None

    # Fetch logs for failed checks
    for check in failed_checks:
        log = _fetch_check_logs(repo, check)
        if log:
            check["full_log"] = log

    if is_billing_exhaustion(failed_checks, check_runs):
        logger.warning("Skipping check failures due to billing exhaustion", pr_number=pr_num)
        return None

    pr_details = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "number,title,body,url,headRefName,baseRefName,state",
        ],
        repo=repo,
    )

    return {
        "type": "check_failure",
        "repository": repo,
        "pr_number": pr_num,
        "pr_title": pr_data.get("title", ""),
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("headRefName", ""),
        "base_branch": pr_data.get("baseRefName", ""),
        "pr_body": pr_details.get("body", "") if pr_details else "",
        "failed_checks": failed_checks,
        "failure_signature": failure_signature,
    }


def _fetch_check_logs(repo: str, check: dict) -> str | None:
    """Fetch full logs for a failed check."""
    details_url = check.get("link", "")
    if "/actions/runs/" in details_url:
        try:
            run_id = details_url.split("/runs/")[-1].split("/")[0].split("?")[0]
            result = subprocess.run(
                ["gh", "run", "view", run_id, "--repo", repo, "--log-failed"],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except (subprocess.TimeoutExpired, Exception):
            pass
    return None


def check_pr_for_merge_conflict(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for merge conflicts.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict
        state: State dict for deduplication

    Returns:
        Context dict if conflict detected, None otherwise
    """
    pr_num = pr_data["number"]
    head_sha = pr_data.get("headRefOid", "")

    pr_details = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "number,title,body,url,headRefName,baseRefName,mergeable,mergeStateStatus",
        ],
        repo=repo,
    )

    if pr_details is None:
        return None

    mergeable = pr_details.get("mergeable", "UNKNOWN")
    merge_state = pr_details.get("mergeStateStatus", "UNKNOWN")

    if mergeable != "CONFLICTING" and merge_state != "DIRTY":
        return None

    conflict_signature = f"{repo}-{pr_num}-{head_sha}:conflict"

    if conflict_signature in state.get("processed_conflicts", {}):
        return None

    logger.info(
        "Merge conflict detected", pr_number=pr_num, mergeable=mergeable, merge_state=merge_state
    )

    return {
        "type": "merge_conflict",
        "repository": repo,
        "pr_number": pr_num,
        "pr_title": pr_data.get("title", ""),
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("headRefName", ""),
        "base_branch": pr_details.get("baseRefName", "main"),
        "pr_body": pr_details.get("body", ""),
        "conflict_signature": conflict_signature,
    }


def check_pr_for_comments(
    repo: str,
    pr_data: dict,
    state: dict,
    bot_username: str,
    github_username: str,
    since_timestamp: str | None = None,
) -> dict | None:
    """Check a PR for new comments that need response.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict
        state: State dict for deduplication
        bot_username: Bot's username (to filter out)
        github_username: Configured GitHub username
        since_timestamp: Filter comments newer than this

    Returns:
        Context dict if new comments found, None otherwise
    """
    pr_num = pr_data["number"]

    comments = gh_json(
        ["pr", "view", str(pr_num), "--repo", repo, "--json", "comments,reviews"], repo=repo
    )
    if comments is None:
        return None

    all_comments = []

    # Issue comments
    for c in comments.get("comments", []):
        all_comments.append(
            {
                "id": c.get("id", ""),
                "author": c.get("author", {}).get("login", "unknown"),
                "body": c.get("body", ""),
                "created_at": c.get("createdAt", ""),
                "type": "comment",
            }
        )

    # Review body comments
    for r in comments.get("reviews", []):
        if r.get("body"):
            all_comments.append(
                {
                    "id": r.get("id", ""),
                    "author": r.get("author", {}).get("login", "unknown"),
                    "body": r.get("body", ""),
                    "created_at": r.get("submittedAt", ""),
                    "type": "review",
                    "state": r.get("state", ""),
                }
            )

    # Line-level review comments
    review_comments = gh_json(["api", f"repos/{repo}/pulls/{pr_num}/comments"], repo=repo)
    if review_comments:
        for rc in review_comments:
            all_comments.append(
                {
                    "id": str(rc.get("id", "")),
                    "author": rc.get("user", {}).get("login", "unknown"),
                    "body": rc.get("body", ""),
                    "created_at": rc.get("created_at", ""),
                    "type": "review_comment",
                    "path": rc.get("path", ""),
                    "line": rc.get("line"),
                    "diff_hunk": rc.get("diff_hunk", ""),
                }
            )

    if not all_comments:
        return None

    # Filter out bot's comments
    excluded_authors = {
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
        "github-actions[bot]",
        "dependabot[bot]",
    }
    other_comments = [c for c in all_comments if c["author"].lower() not in excluded_authors]

    if not other_comments:
        return None

    # Apply restrict_to_configured_users filter
    if should_restrict_to_configured_users(repo):
        allowed_users = {github_username.lower()}
        other_comments = [c for c in other_comments if c["author"].lower() in allowed_users]
        if not other_comments:
            return None

    # Filter by timestamp
    failed_tasks = state.get("failed_tasks", {})
    has_failed_task = any(
        info.get("task_type") == "comment"
        and info.get("repository") == repo
        and info.get("pr_number") == pr_num
        for info in failed_tasks.values()
    )

    if since_timestamp and not has_failed_task:
        other_comments = [c for c in other_comments if c.get("created_at", "") >= since_timestamp]
        if not other_comments:
            return None

    latest_comment = max(other_comments, key=lambda c: c.get("created_at", ""))
    comment_signature = f"{repo}-{pr_num}:{latest_comment['id']}"

    if comment_signature in state.get("processed_comments", {}):
        return None

    logger.info("New comments on PR", pr_number=pr_num, comment_count=len(other_comments))

    return {
        "type": "comment",
        "repository": repo,
        "pr_number": pr_num,
        "pr_title": pr_data.get("title", ""),
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("headRefName", ""),
        "comments": other_comments,
        "comment_signature": comment_signature,
    }


def check_pr_for_review_response(
    repo: str,
    pr_data: dict,
    state: dict,
    bot_username: str,
    github_username: str,
    since_timestamp: str | None = None,
) -> dict | None:
    """Check a bot's PR for reviews that need response.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict (must be a bot-authored PR)
        state: State dict for deduplication
        bot_username: Bot's username
        github_username: Configured GitHub username
        since_timestamp: Filter reviews newer than this

    Returns:
        Context dict if new reviews found, None otherwise
    """
    pr_num = pr_data["number"]

    reviews_data = gh_json(
        ["pr", "view", str(pr_num), "--repo", repo, "--json", "reviews,reviewRequests"],
        repo=repo,
    )

    if reviews_data is None:
        return None

    reviews = reviews_data.get("reviews", [])
    if not reviews:
        return None

    bot_variants = {
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
        f"app/{bot_username.lower()}",
    }
    other_reviews = [
        r for r in reviews if r.get("author", {}).get("login", "").lower() not in bot_variants
    ]

    if not other_reviews:
        return None

    if should_restrict_to_configured_users(repo):
        allowed_users = {github_username.lower()}
        other_reviews = [
            r
            for r in other_reviews
            if r.get("author", {}).get("login", "").lower() in allowed_users
        ]
        if not other_reviews:
            return None

    if since_timestamp:
        other_reviews = [r for r in other_reviews if r.get("submittedAt", "") >= since_timestamp]
        if not other_reviews:
            return None

    other_reviews.sort(key=lambda r: r.get("submittedAt", ""), reverse=True)
    latest_review = other_reviews[0]

    review_id = latest_review.get("id", "")
    review_response_signature = f"{repo}-{pr_num}:review_response:{review_id}"

    if review_response_signature in state.get("processed_review_responses", {}):
        return None

    # Get line-level review comments
    review_comments = gh_json(["api", f"repos/{repo}/pulls/{pr_num}/comments"], repo=repo)
    line_comments = []
    if review_comments:
        for rc in review_comments:
            rc_author = rc.get("user", {}).get("login", "").lower()
            if rc_author not in bot_variants:
                line_comments.append(
                    {
                        "id": str(rc.get("id", "")),
                        "author": rc.get("user", {}).get("login", "unknown"),
                        "body": rc.get("body", ""),
                        "path": rc.get("path", ""),
                        "line": rc.get("line"),
                        "original_line": rc.get("original_line"),
                        "diff_hunk": rc.get("diff_hunk", ""),
                        "created_at": rc.get("created_at", ""),
                    }
                )

    review_info = [
        {
            "id": r.get("id", ""),
            "author": r.get("author", {}).get("login", "unknown"),
            "state": r.get("state", "COMMENTED"),
            "body": r.get("body", ""),
            "submitted_at": r.get("submittedAt", ""),
        }
        for r in other_reviews
    ]

    logger.info(
        "Bot PR has reviews needing response", pr_number=pr_num, review_count=len(review_info)
    )

    diff = gh_text(["pr", "diff", str(pr_num), "--repo", repo], repo=repo)

    return {
        "type": "pr_review_response",
        "repository": repo,
        "pr_number": pr_num,
        "pr_title": pr_data.get("title", ""),
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("headRefName", ""),
        "base_branch": pr_data.get("baseRefName", "main"),
        "reviews": review_info,
        "line_comments": line_comments,
        "diff": truncate_diff(diff),
        "review_response_signature": review_response_signature,
    }


def check_prs_for_review(
    repo: str,
    all_prs: list[dict],
    state: dict,
    github_username: str,
    bot_username: str,
    since_timestamp: str | None = None,
    is_readonly: bool = False,
    require_explicit_request: bool = True,
) -> list[dict]:
    """Check for PRs that need review.

    Args:
        repo: Repository in owner/repo format
        all_prs: List of all open PRs
        state: State dict for deduplication
        github_username: User's GitHub username
        bot_username: Bot's username
        since_timestamp: Filter PRs created after this
        is_readonly: If True, only review when user is directly requested
        require_explicit_request: If True, bot must be explicitly assigned/tagged (new opt-in behavior)

    Returns:
        List of context dicts for PRs needing review
    """
    if not all_prs:
        return []

    excluded_authors = {
        github_username.lower(),
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
    }
    other_prs = [
        p for p in all_prs if p.get("author", {}).get("login", "").lower() not in excluded_authors
    ]

    if not other_prs:
        return []

    # For read-only repos OR new opt-in behavior, only review when explicitly requested
    if is_readonly or require_explicit_request:
        directly_requested_prs = []
        for pr in other_prs:
            pr_num = pr["number"]
            pr_details = gh_json(
                ["pr", "view", str(pr_num), "--repo", repo, "--json", "reviewRequests,assignees"],
                repo=repo,
            )
            if pr_details:
                # Check if bot is requested as reviewer OR assigned
                if is_jib_engaged(pr_details, bot_username):
                    directly_requested_prs.append(pr)
                    logger.debug("Bot requested/assigned for review", pr_number=pr_num)

        if not directly_requested_prs:
            return []
        other_prs = directly_requested_prs

    # Filter by timestamp
    failed_review_pr_numbers = {
        info.get("pr_number")
        for info in state.get("failed_tasks", {}).values()
        if info.get("task_type") == "review_request" and info.get("repository") == repo
    }

    if since_timestamp:
        other_prs = [
            p
            for p in other_prs
            if p.get("createdAt", "") >= since_timestamp or p["number"] in failed_review_pr_numbers
        ]
        if not other_prs:
            return []

    results = []
    for pr in other_prs:
        pr_num = pr["number"]
        head_sha = pr.get("headRefOid", "")
        review_signature = f"{repo}-{pr_num}-{head_sha}:review"

        if review_signature in state.get("processed_reviews", {}):
            continue

        # Determine if this is a re-review
        pr_review_prefix = f"{repo}-{pr_num}-"
        is_rereview = any(
            sig.startswith(pr_review_prefix) and sig.endswith(":review")
            for sig in state.get("processed_reviews", {})
        )

        diff = gh_text(["pr", "diff", str(pr_num), "--repo", repo], repo=repo)

        results.append(
            {
                "type": "review_request",
                "repository": repo,
                "pr_number": pr_num,
                "pr_title": pr.get("title", ""),
                "pr_url": pr.get("url", ""),
                "pr_branch": pr.get("headRefName", ""),
                "base_branch": pr.get("baseRefName", ""),
                "author": pr.get("author", {}).get("login", ""),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "files": [f.get("path", "") for f in pr.get("files", [])],
                "diff": truncate_diff(diff),
                "review_signature": review_signature,
                "is_rereview": is_rereview,
            }
        )

    return results
