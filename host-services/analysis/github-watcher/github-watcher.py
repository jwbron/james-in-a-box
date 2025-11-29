#!/usr/bin/env python3
"""
GitHub Watcher - Host-side service that monitors GitHub and triggers jib container analysis.

This service runs on the host (NOT in the container) and:
1. Queries GitHub directly via gh CLI for PR/issue status
2. Detects check failures, new comments, and review requests
3. Triggers jib container via `jib --exec github-processor.py --context <json>`

The container should ONLY be called via `jib --exec`. No watching/polling logic lives in the container.

Per ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B: Scheduled Analysis with MCP"

## PR and Comment Handling Behavior

### Which PRs are monitored:
1. **User's PRs** (authored by `github_username` from config):
   - Check failures: Detects and triggers fixes for failing CI checks
   - Comments: Responds to comments from others (not from bot)

2. **Bot's PRs** (authored by `bot_username[bot]`):
   - Check failures: Detects and triggers fixes for failing CI checks
   - Comments: Responds to comments from the user and others (not from bot itself)

### Which comments are handled:
- Comments from the configured `github_username` (e.g., jwbron) ARE processed
- Comments from the `bot_username` and common bots (github-actions, dependabot) are IGNORED
- Only comments newer than the last watcher run are processed (to avoid re-processing)

### Check failure retry behavior:
- Each unique (repo, PR, commit SHA, failing check names) combination is tracked
- If a commit's failures have been processed, they won't be retried for that same commit
- Pushing a new commit resets the processed state, allowing fresh retry attempts

### Merge conflict detection:
- PRs with mergeable=CONFLICTING or mergeStateStatus=DIRTY are detected
- Each unique (repo, PR, commit SHA) conflict combination is tracked
- Pushing a new commit resets the processed state, allowing fresh retry

### What happens when jib is invoked:
- jib runs Claude with the task context (check failures, comments, or review request)
- Claude analyzes the issue and takes action (fix code, respond to comments, etc.)
- Claude uses `gh pr comment` to post responses
- Claude commits and pushes fixes for check failures

### Configuration (config/repositories.yaml):
- `github_username`: Your GitHub username (for identifying your PRs)
- `bot_username`: The bot's GitHub identity (for filtering out its own comments)
- `writable_repos`: List of repos where jib has write access
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


# Add shared directory to path for jib_logging
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from jib_logging import ContextScope, get_logger


# Initialize logger
logger = get_logger("github-watcher")


# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls
RATE_LIMIT_MAX_RETRIES = 3  # Max retries on rate limit errors
RATE_LIMIT_BASE_WAIT = 60  # Base wait time in seconds for exponential backoff


def load_config() -> dict:
    """Load repository configuration.

    Returns dict with:
        - writable_repos: List of repos jib can modify
        - github_username: Configured GitHub username (for filtering)
    """
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)

    return {"writable_repos": [], "github_username": "jib"}


def load_state() -> dict:
    """Load previous notification state to avoid duplicate processing."""
    state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
    if state_file.exists():
        try:
            with state_file.open() as f:
                state = json.load(f)
                # Ensure all expected keys exist
                state.setdefault("processed_failures", {})
                state.setdefault("processed_comments", {})
                state.setdefault("processed_reviews", {})
                state.setdefault("processed_conflicts", {})
                state.setdefault("last_run_start", None)
                logger.debug(
                    "State loaded successfully",
                    state_file=str(state_file),
                    processed_failures_count=len(state["processed_failures"]),
                    processed_comments_count=len(state["processed_comments"]),
                    last_run_start=state["last_run_start"],
                )
                return state
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse state file (JSON decode error)",
                state_file=str(state_file),
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "Failed to load state file",
                state_file=str(state_file),
                error=str(e),
                error_type=type(e).__name__,
            )
    else:
        logger.debug("No existing state file found, starting fresh", state_file=str(state_file))

    return {
        "processed_failures": {},
        "processed_comments": {},
        "processed_reviews": {},
        "processed_conflicts": {},
        "last_run_start": None,
    }


def save_state(state: dict):
    """Save notification state."""
    state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open("w") as f:
        json.dump(state, f, indent=2)


def gh_json(args: list[str]) -> dict | list | None:
    """Run gh CLI command and return JSON output with rate limit handling.

    Implements exponential backoff on rate limit errors and basic throttling
    between calls to prevent hitting rate limits.
    """
    # Basic throttling between calls
    time.sleep(RATE_LIMIT_DELAY)

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            # Check for rate limiting
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning(
                        "Rate limited, retrying",
                        wait_seconds=wait_time,
                        attempt=attempt + 1,
                        command=" ".join(args),
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "Rate limit exceeded after max retries",
                        retries=RATE_LIMIT_MAX_RETRIES,
                        command=" ".join(args),
                    )
                    return None
            else:
                logger.error(
                    "gh command failed",
                    command=" ".join(args),
                    stderr=e.stderr,
                )
                return None
        except json.JSONDecodeError:
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out", command=" ".join(args))
            return None

    return None


def gh_text(args: list[str]) -> str | None:
    """Run gh CLI command and return text output with rate limit handling.

    Implements exponential backoff on rate limit errors and basic throttling
    between calls to prevent hitting rate limits.
    """
    # Basic throttling between calls
    time.sleep(RATE_LIMIT_DELAY)

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            # Check for rate limiting
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning(
                        "Rate limited, retrying",
                        wait_seconds=wait_time,
                        attempt=attempt + 1,
                        command=" ".join(args),
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "Rate limit exceeded after max retries",
                        retries=RATE_LIMIT_MAX_RETRIES,
                        command=" ".join(args),
                    )
                    return None
            else:
                logger.error(
                    "gh command failed",
                    command=" ".join(args),
                    stderr=e.stderr,
                )
                return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out", command=" ".join(args))
            return None

    return None


def invoke_jib(task_type: str, context: dict) -> bool:
    """Invoke jib container with context via jib --exec.

    Args:
        task_type: One of 'check_failure', 'comment', 'review_request'
        context: Dict containing task-specific context

    Returns:
        True if invocation succeeded
    """
    context_json = json.dumps(context)

    # Container path is fixed - jib always mounts to /home/jwies/khan/
    processor_path = (
        "/home/jwies/khan/james-in-a-box/jib-container/jib-tasks/github/github-processor.py"
    )

    # Build command
    cmd = [
        "jib",
        "--exec",
        "python3",
        processor_path,
        "--task",
        task_type,
        "--context",
        context_json,
    ]

    # Build detailed context for logging based on task type
    log_extra = {
        "task_type": task_type,
        "repository": context.get("repository", "unknown"),
    }

    if task_type == "check_failure":
        log_extra["pr_number"] = context.get("pr_number")
        log_extra["pr_title"] = context.get("pr_title", "")[:60]
        log_extra["failed_checks"] = [c.get("name") for c in context.get("failed_checks", [])]
    elif task_type == "comment":
        log_extra["pr_number"] = context.get("pr_number")
        log_extra["pr_title"] = context.get("pr_title", "")[:60]
        log_extra["comment_count"] = len(context.get("comments", []))
        if context.get("comments"):
            log_extra["comment_authors"] = list({c.get("author") for c in context["comments"]})
    elif task_type == "merge_conflict":
        log_extra["pr_number"] = context.get("pr_number")
        log_extra["pr_title"] = context.get("pr_title", "")[:60]
        log_extra["pr_branch"] = context.get("pr_branch")
        log_extra["base_branch"] = context.get("base_branch")
    elif task_type == "review_request":
        log_extra["pr_number"] = context.get("pr_number")
        log_extra["pr_title"] = context.get("pr_title", "")[:60]
        log_extra["author"] = context.get("author")

    logger.info("Invoking jib", **log_extra)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            # No timeout - let the container handle its own timeout via shared/claude/runner.py
        )

        if result.returncode == 0:
            logger.info(
                "jib completed successfully",
                task_type=task_type,
                repository=context.get("repository", "unknown"),
                pr_number=context.get("pr_number"),
            )
            return True
        else:
            # Show last 2000 chars of stderr to capture actual error (not just Docker build progress)
            stderr_tail = result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr
            stdout_tail = result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout

            # Try to extract the most relevant error message from stderr
            error_summary = None
            if stderr_tail:
                # Look for common error patterns
                for line in stderr_tail.split("\n"):
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in ["error:", "failed:", "exception:", "traceback"]):
                        error_summary = line.strip()[:200]
                        break

            logger.error(
                "jib failed",
                task_type=task_type,
                repository=context.get("repository", "unknown"),
                pr_number=context.get("pr_number"),
                return_code=result.returncode,
                error_summary=error_summary,
                stderr=stderr_tail if stderr_tail else None,
                stdout=stdout_tail if stdout_tail else None,
            )
            return False
    except FileNotFoundError:
        logger.error(
            "jib command not found - is it in PATH?",
            task_type=task_type,
            repository=context.get("repository", "unknown"),
            pr_number=context.get("pr_number"),
        )
        return False
    except Exception as e:
        logger.error(
            "Error invoking jib",
            error=str(e),
            error_type=type(e).__name__,
            task_type=task_type,
            repository=context.get("repository", "unknown"),
            pr_number=context.get("pr_number"),
        )
        return False


def check_pr_for_failures(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for check failures.

    Returns context dict if failures found and not already processed.
    """
    pr_num = pr_data["number"]
    head_sha = pr_data.get("headRefOid")

    if not head_sha:
        logger.debug("PR has no head SHA, skipping check status", pr_number=pr_num)
        return None

    # Get check runs via GitHub API (more reliable than gh pr checks)
    # gh pr checks only shows "required" checks; this gets all check runs
    check_runs_response = gh_json(
        [
            "api",
            f"repos/{repo}/commits/{head_sha}/check-runs",
        ]
    )

    if check_runs_response is None:
        return None

    check_runs = check_runs_response.get("check_runs", [])
    if not check_runs:
        return None  # No checks have run (e.g., PR created before workflows existed)

    # Find failed checks (conclusion: "failure" or "cancelled" or "timed_out")
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
        # Show check status for debugging
        statuses = [c.get("conclusion", "pending") for c in check_runs]
        logger.debug(
            "PR checks all passing",
            pr_number=pr_num,
            check_count=len(check_runs),
            statuses=list(set(statuses)),
        )
        return None

    # Create signature to detect if we've already processed this exact failure set
    # Include head_sha so new commits get a fresh retry opportunity
    failed_names = sorted([c["name"] for c in failed_checks])
    failure_signature = f"{repo}-{pr_num}-{head_sha}:" + ",".join(failed_names)

    if failure_signature in state.get("processed_failures", {}):
        processed_at = state["processed_failures"].get(failure_signature, "unknown")
        logger.debug(
            "PR check failures already processed",
            pr_number=pr_num,
            failed_count=len(failed_checks),
            processed_at=processed_at,
            failed_checks=failed_names,
        )
        return None  # Already processed

    # Extract failure reasons for more informative logging
    failure_details = []
    for check in failed_checks:
        detail = check["name"]
        if check.get("workflow"):
            detail = f"{check['workflow']}/{check['name']}"
        state = check.get("state", "FAILED")
        if state:
            detail = f"{detail} ({state})"
        failure_details.append(detail)

    logger.info(
        "PR has failing checks",
        pr_number=pr_num,
        pr_title=pr_data.get("title", "")[:80],
        failed_count=len(failed_checks),
        failed_checks=failed_names,
        failure_details=failure_details,
    )

    # Fetch logs for failed checks
    for check in failed_checks:
        log = fetch_check_logs(repo, check)
        if log:
            check["full_log"] = log

    # Get PR details
    pr_details = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "number,title,body,url,headRefName,baseRefName,state",
        ]
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


def fetch_check_logs(repo: str, check: dict) -> str | None:
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

        except subprocess.TimeoutExpired:
            logger.warning("Log fetch timed out", check_name=check["name"])
        except Exception as e:
            logger.warning("Error fetching logs", check_name=check["name"], error=str(e))

    return None


def check_pr_for_comments(
    repo: str, pr_data: dict, state: dict, bot_username: str, since_timestamp: str | None = None
) -> dict | None:
    """Check a PR for new comments from others that need response.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict with number, title, url, etc.
        state: State dict with processed_comments
        bot_username: Bot's username (to filter out bot's own comments)
        since_timestamp: ISO timestamp to filter comments (only show newer)

    Returns context dict if new comments found and not already processed.
    """
    pr_num = pr_data["number"]

    # Get PR comments
    comments = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "comments,reviews",
        ]
    )

    if comments is None:
        return None

    all_comments = []

    # Regular comments
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

    # Review comments
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

    if not all_comments:
        return None

    # Debug: show comment count
    logger.debug("Found comments on PR", pr_number=pr_num, comment_count=len(all_comments))

    # Filter to comments from the bot itself or common bots
    # Build list of authors to exclude (case-insensitive)
    # Include both the base username and the [bot] suffix variant
    excluded_authors = {
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
        "github-actions[bot]",
        "dependabot[bot]",
    }

    other_comments = [c for c in all_comments if c["author"].lower() not in excluded_authors]

    if not other_comments:
        logger.debug(
            "No comments from others (all from bot/excluded)",
            pr_number=pr_num,
        )
        return None

    # Filter by since_timestamp if provided (only show comments newer than last run)
    # Use >= to avoid missing comments that occur at exactly the same timestamp
    if since_timestamp:
        pre_filter_count = len(other_comments)
        other_comments = [c for c in other_comments if c.get("created_at", "") >= since_timestamp]
        if not other_comments:
            logger.debug(
                "Comments filtered out (all before last run)",
                pr_number=pr_num,
                filtered_count=pre_filter_count,
                since=since_timestamp,
            )
            return None  # No new comments since last run

    # Create signature based on latest comment timestamp
    latest_comment = max(other_comments, key=lambda c: c.get("created_at", ""))
    comment_signature = f"{repo}-{pr_num}:{latest_comment['id']}"

    if comment_signature in state.get("processed_comments", {}):
        processed_at = state["processed_comments"].get(comment_signature, "unknown")
        logger.debug(
            "Latest comment already processed",
            pr_number=pr_num,
            processed_at=processed_at,
            author=latest_comment["author"],
        )
        return None  # Already processed

    # Extract comment details for more informative logging
    comment_authors = list({c["author"] for c in other_comments})
    # Get a preview of the latest comment
    latest_comment_preview = latest_comment.get("body", "")[:100]
    if len(latest_comment.get("body", "")) > 100:
        latest_comment_preview += "..."

    logger.info(
        "New comments from others on PR",
        pr_number=pr_num,
        pr_title=pr_data.get("title", "")[:80],
        comment_count=len(other_comments),
        comment_authors=comment_authors,
        latest_comment_author=latest_comment["author"],
        latest_comment_preview=latest_comment_preview,
        latest_comment_type=latest_comment.get("type", "comment"),
    )

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


def check_pr_for_merge_conflict(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for merge conflicts.

    Returns context dict if merge conflict detected and not already processed.
    """
    pr_num = pr_data["number"]
    head_sha = pr_data.get("headRefOid", "")

    # Get detailed PR info including mergeable status
    # gh pr list doesn't include mergeable, so we need a separate call
    pr_details = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "number,title,body,url,headRefName,baseRefName,mergeable,mergeStateStatus",
        ]
    )

    if pr_details is None:
        return None

    # Check mergeable status
    # mergeable can be: MERGEABLE, CONFLICTING, UNKNOWN
    # mergeStateStatus can be: BEHIND, BLOCKED, CLEAN, DIRTY, DRAFT, HAS_HOOKS, UNKNOWN, UNSTABLE
    mergeable = pr_details.get("mergeable", "UNKNOWN")
    merge_state = pr_details.get("mergeStateStatus", "UNKNOWN")

    # Only trigger on actual conflicts (CONFLICTING or DIRTY state)
    if mergeable != "CONFLICTING" and merge_state != "DIRTY":
        return None

    # Create signature including head_sha so new commits get a fresh retry
    conflict_signature = f"{repo}-{pr_num}-{head_sha}:conflict"

    if conflict_signature in state.get("processed_conflicts", {}):
        processed_at = state["processed_conflicts"].get(conflict_signature, "unknown")
        logger.debug(
            "Merge conflict already processed",
            pr_number=pr_num,
            processed_at=processed_at,
            commit=head_sha[:8],
        )
        return None  # Already processed

    logger.info(
        "Merge conflict detected",
        pr_number=pr_num,
        pr_title=pr_data.get("title", "")[:80],
        pr_branch=pr_data.get("headRefName", ""),
        base_branch=pr_details.get("baseRefName", "main"),
        mergeable=mergeable,
        merge_state=merge_state,
        commit=head_sha[:8] if head_sha else "unknown",
    )

    return {
        "type": "merge_conflict",
        "repository": repo,
        "pr_number": pr_num,
        "pr_title": pr_data.get("title", ""),
        "pr_url": pr_data.get("url", ""),
        "pr_branch": pr_data.get("headRefName", ""),
        "base_branch": pr_data.get("baseRefName", "main"),
        "pr_body": pr_details.get("body", ""),
        "conflict_signature": conflict_signature,
    }


def check_prs_for_review(
    repo: str,
    all_prs: list[dict],
    state: dict,
    github_username: str,
    bot_username: str,
    since_timestamp: str | None = None,
) -> list[dict]:
    """Check for PRs from others that need review.

    Args:
        repo: Repository in owner/repo format
        all_prs: Pre-fetched list of all open PRs (to avoid redundant API calls)
        state: State dict with processed_reviews
        github_username: The user's GitHub username (to exclude their PRs)
        bot_username: Bot's username (to filter out bot's own PRs)
        since_timestamp: ISO timestamp to filter PRs (only show newer)

    Returns list of context dicts for PRs needing review.
    """
    if not all_prs:
        return []

    # Filter to PRs from others (not from the user or bot)
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

    # Filter by since_timestamp if provided (only show PRs created after last run)
    # Use >= to avoid missing PRs that occur at exactly the same timestamp
    if since_timestamp:
        other_prs = [p for p in other_prs if p.get("createdAt", "") >= since_timestamp]
        if not other_prs:
            return []  # No new PRs since last run

    results = []
    for pr in other_prs:
        pr_num = pr["number"]
        review_signature = f"{repo}-{pr_num}:review"

        # Check if already reviewed
        if review_signature in state.get("processed_reviews", {}):
            continue

        logger.info(
            "New PR needs review",
            pr_number=pr_num,
            pr_title=pr.get("title", "")[:80],
            author=pr.get("author", {}).get("login", "unknown"),
            pr_branch=pr.get("headRefName", ""),
            base_branch=pr.get("baseRefName", ""),
            additions=pr.get("additions", 0),
            deletions=pr.get("deletions", 0),
            files_changed=len(pr.get("files", [])),
        )

        # Get PR diff
        diff = gh_text(["pr", "diff", str(pr_num), "--repo", repo])

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
                "diff": diff[:50000] if diff else "",  # Limit diff size
                "review_signature": review_signature,
            }
        )

    return results


def utc_now_iso() -> str:
    """Get current UTC time in ISO format with Z suffix.

    This ensures consistent timestamp format for comparison with GitHub timestamps.
    GitHub returns timestamps like: 2025-11-27T02:01:26Z
    We generate:                    2025-11-27T04:29:21Z (no microseconds for cleaner comparison)
    """
    # Use timezone.utc for Python 3.10 compatibility (host may run Ubuntu 22.04)
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017


def get_since_timestamp(state: dict) -> str | None:
    """Get ISO timestamp for 'since' queries based on last run START time.

    Returns None if this is the first run or last_run_start is not set.

    We use last_run_start (when the previous watcher run began) rather than
    when it ended to ensure we don't miss any events that occurred during
    the previous run's execution.
    """
    return state.get("last_run_start")


def main():
    """Main entry point - scan configured repos and trigger jib as needed."""
    # Record when this run STARTS - this is what we'll use for next run's "since"
    current_run_start = utc_now_iso()

    logger.info(
        "GitHub Watcher starting",
        local_time=datetime.now().isoformat(),
        utc_time=current_run_start,
    )

    # Load config
    config = load_config()
    repos = config.get("writable_repos", [])
    github_username = config.get("github_username", "jib")
    bot_username = config.get("bot_username", "jib")

    if not repos:
        logger.warning("No repositories configured - check config/repositories.yaml")
        return 0

    logger.info(
        "Configuration loaded",
        github_username=github_username,
        bot_username=bot_username,
        repo_count=len(repos),
        repositories=repos,
    )

    # Load state
    state = load_state()

    # Get the timestamp from when the PREVIOUS run started (for comment filtering)
    since_timestamp = get_since_timestamp(state)
    if since_timestamp:
        logger.info("Checking for comments since last run", since=since_timestamp)
    else:
        logger.info("First run - checking all open items")
    logger.debug("PR check failures: checking ALL open PRs unconditionally")

    logger.info("Scanning repositories", count=len(repos))

    tasks_queued = 0

    for repo in repos:
        # Use ContextScope to automatically include repository in all logs within this block
        with ContextScope(repository=repo):
            logger.info("Processing repository")

            # OPTIMIZATION: Fetch ALL open PRs in a single API call, then filter locally
            # This reduces 3 API calls to 1 per repository
            all_prs = gh_json(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,title,url,headRefName,baseRefName,headRefOid,author,createdAt,additions,deletions,files",
                ]
            )

            if all_prs is None:
                logger.warning("Failed to fetch PRs, skipping repository")
                continue

            logger.info("Fetched open PRs", count=len(all_prs))

            # Filter PRs locally by author
            my_prs = [
                p
                for p in all_prs
                if p.get("author", {}).get("login", "").lower() == github_username.lower()
            ]

            # Bot PRs can have author login in different formats depending on the API:
            # - "bot_username" - base name
            # - "bot_username[bot]" - GitHub web UI format
            # - "app/bot_username" - gh CLI format (gh pr list --json author returns this)
            bot_author_variants = {
                bot_username.lower(),
                f"{bot_username.lower()}[bot]",
                f"app/{bot_username.lower()}",
            }
            bot_prs = [
                p
                for p in all_prs
                if p.get("author", {}).get("login", "").lower() in bot_author_variants
            ]

            # Process user's PRs
            if my_prs:
                logger.info(
                    "Found user's open PRs",
                    count=len(my_prs),
                    username=github_username,
                )

                for pr in my_prs:
                    # Check for failures
                    failure_ctx = check_pr_for_failures(repo, pr, state)
                    if failure_ctx and invoke_jib("check_failure", failure_ctx):
                        state.setdefault("processed_failures", {})[
                            failure_ctx["failure_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1

                    # Check for comments (filter out bot's own comments, not human's)
                    comment_ctx = check_pr_for_comments(
                        repo, pr, state, bot_username, since_timestamp
                    )
                    if comment_ctx and invoke_jib("comment", comment_ctx):
                        state.setdefault("processed_comments", {})[
                            comment_ctx["comment_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1

                    # Check for merge conflicts
                    conflict_ctx = check_pr_for_merge_conflict(repo, pr, state)
                    if conflict_ctx and invoke_jib("merge_conflict", conflict_ctx):
                        state.setdefault("processed_conflicts", {})[
                            conflict_ctx["conflict_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1
            else:
                logger.debug("No open PRs authored by user", username=github_username)

            # Process bot's PRs (for check failures and comments)
            # The bot creates PRs via GitHub App, so its PRs need monitoring too
            if bot_prs:
                logger.info(
                    "Found bot's open PRs",
                    count=len(bot_prs),
                    bot_username=bot_username,
                )

                for pr in bot_prs:
                    # Check for failures on bot's PRs
                    failure_ctx = check_pr_for_failures(repo, pr, state)
                    if failure_ctx and invoke_jib("check_failure", failure_ctx):
                        state.setdefault("processed_failures", {})[
                            failure_ctx["failure_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1

                    # Check for comments on bot's PRs (filter out bot's own comments)
                    comment_ctx = check_pr_for_comments(
                        repo, pr, state, bot_username, since_timestamp
                    )
                    if comment_ctx and invoke_jib("comment", comment_ctx):
                        state.setdefault("processed_comments", {})[
                            comment_ctx["comment_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1

                    # Check for merge conflicts on bot's PRs
                    conflict_ctx = check_pr_for_merge_conflict(repo, pr, state)
                    if conflict_ctx and invoke_jib("merge_conflict", conflict_ctx):
                        state.setdefault("processed_conflicts", {})[
                            conflict_ctx["conflict_signature"]
                        ] = utc_now_iso()
                        tasks_queued += 1

            # Check for PRs from others that need review (uses pre-fetched all_prs)
            review_contexts = check_prs_for_review(
                repo, all_prs, state, github_username, bot_username, since_timestamp
            )
            for review_ctx in review_contexts:
                if invoke_jib("review_request", review_ctx):
                    state.setdefault("processed_reviews", {})[review_ctx["review_signature"]] = (
                        utc_now_iso()
                    )
                    tasks_queued += 1

    # Update last run START timestamp and save state
    # We store when this run STARTED so next run checks for comments since then
    state["last_run_start"] = current_run_start
    save_state(state)

    # Summary statistics for completed run
    logger.info(
        "GitHub Watcher completed",
        tasks_triggered=tasks_queued,
        repositories_scanned=len(repos),
        next_check_since=current_run_start,
        processed_failures_count=len(state.get("processed_failures", {})),
        processed_comments_count=len(state.get("processed_comments", {})),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
