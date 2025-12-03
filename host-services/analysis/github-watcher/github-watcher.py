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

### Failed task retry behavior:
- When jib fails to process a task (e.g., container crashes, timeout, error), the task is
  tracked in `failed_tasks` state for automatic retry on the next watcher run
- Failed tasks bypass the timestamp filter, ensuring old PRs/comments are not ignored
- Once successfully processed, failed tasks are automatically removed from retry queue
- State is stored in `~/.local/share/github-watcher/state.json`

### Merge conflict detection:
- PRs with mergeable=CONFLICTING or mergeStateStatus=DIRTY are detected
- Each unique (repo, PR, commit SHA) conflict combination is tracked
- Pushing a new commit resets the processed state, allowing fresh retry

### Re-review on new commits:
- Review signatures include the head commit SHA
- When new commits are pushed to a PR branch, the signature changes
- This triggers a re-review so reviewers always see the latest code
- The `is_rereview` flag is set in the context to distinguish re-reviews from initial reviews

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
import os
import secrets
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml


# Add shared modules to path - jib_logging is in /opt/jib-runtime/shared
# Config is loaded from the repo path
sys.path.insert(0, "/opt/jib-runtime/shared")
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from jib_logging import ContextScope, get_logger

from config.repo_config import get_github_token_for_repo


# Initialize logger
logger = get_logger("github-watcher")


# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls
RATE_LIMIT_MAX_RETRIES = 3  # Max retries on rate limit errors
RATE_LIMIT_BASE_WAIT = 60  # Base wait time in seconds for exponential backoff

# Parallel execution configuration
MAX_PARALLEL_JIB = 20  # Max concurrent jib containers

# Host-side notification directory (different from container's ~/sharing/notifications)
# The slack-notifier service monitors this directory for notification files
HOST_NOTIFICATIONS_DIR = Path.home() / ".jib-sharing" / "notifications"

# Maximum diff size to include in context
MAX_DIFF_SIZE = 50000


def truncate_diff(diff: str, max_size: int = MAX_DIFF_SIZE) -> str:
    """Truncate diff at a line boundary to avoid cutting mid-line.

    Args:
        diff: The diff content to truncate
        max_size: Maximum size in characters

    Returns:
        Truncated diff ending at a line boundary
    """
    if not diff or len(diff) <= max_size:
        return diff or ""
    # Find last newline before limit to avoid cutting mid-line
    truncated = diff[:max_size].rsplit("\n", 1)[0]
    return truncated


@dataclass
class JibTask:
    """A task to be executed by jib.

    Attributes:
        task_type: One of 'check_failure', 'comment', 'merge_conflict', 'review_request'
        context: Task-specific context dict
        signature_key: Key for processed_* dict (e.g., 'processed_failures')
        signature_value: The signature to mark as processed
        is_readonly: If True, send notification instead of invoking jib (for read-only repos)
    """

    task_type: str
    context: dict
    signature_key: str
    signature_value: str
    is_readonly: bool = False


class ThreadSafeState:
    """Thread-safe wrapper for state management."""

    def __init__(self, state: dict):
        self._state = state
        self._lock = threading.Lock()

    def mark_processed(self, key: str, signature: str) -> None:
        """Mark a task as processed (thread-safe).

        Also removes from failed_tasks if present (successful retry).
        """
        with self._lock:
            self._state.setdefault(key, {})[signature] = utc_now_iso()
            # Remove from failed_tasks if this was a retry
            if signature in self._state.get("failed_tasks", {}):
                del self._state["failed_tasks"][signature]
            self._save()

    def mark_failed(self, signature: str, task_type: str, context: dict) -> None:
        """Mark a task as failed for later retry (thread-safe).

        Stores minimal context needed to retry the task on the next run.
        """
        with self._lock:
            self._state.setdefault("failed_tasks", {})[signature] = {
                "failed_at": utc_now_iso(),
                "task_type": task_type,
                "repository": context.get("repository", "unknown"),
                "pr_number": context.get("pr_number"),
            }
            self._save()

    def _save(self) -> None:
        """Save state to disk (must be called with lock held)."""
        self._state["last_run_start"] = utc_now_iso()
        state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with state_file.open("w") as f:
            json.dump(self._state, f, indent=2)

    def get_state(self) -> dict:
        """Get a copy of current state (for reading)."""
        with self._lock:
            return self._state.copy()


def load_config() -> dict:
    """Load repository configuration.

    Returns dict with:
        - writable_repos: List of repos jib can modify
        - readable_repos: List of repos jib can only read (notify via Slack)
        - github_username: Configured GitHub username (for filtering)
    """
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                # Ensure readable_repos exists
                config.setdefault("readable_repos", [])
                return config

    return {"writable_repos": [], "readable_repos": [], "github_username": "jib"}


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
                state.setdefault("processed_review_responses", {})
                state.setdefault("failed_tasks", {})
                state.setdefault("last_run_start", None)
                logger.debug(
                    "State loaded successfully",
                    state_file=str(state_file),
                    processed_failures_count=len(state["processed_failures"]),
                    processed_comments_count=len(state["processed_comments"]),
                    failed_tasks_count=len(state["failed_tasks"]),
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
        "processed_review_responses": {},
        "failed_tasks": {},
        "last_run_start": None,
    }


def save_state(state: dict, update_last_run: bool = False):
    """Save notification state.

    Args:
        state: The state dict to save
        update_last_run: If True, also update last_run_start to current time.
                        This creates a checkpoint so if the process is killed,
                        the next run resumes from a reasonable point.
    """
    if update_last_run:
        state["last_run_start"] = utc_now_iso()

    state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open("w") as f:
        json.dump(state, f, indent=2)


def gh_json(
    args: list[str], repo: str | None = None, token: str | None = None
) -> dict | list | None:
    """Run gh CLI command and return JSON output with rate limit handling.

    Implements exponential backoff on rate limit errors and basic throttling
    between calls to prevent hitting rate limits.

    Args:
        args: Arguments to pass to gh CLI
        repo: Optional repository context for logging and token selection
        token: Optional explicit GitHub token (overrides auto-selection)

    If repo is provided and token is not, automatically selects the appropriate
    token based on repo access level (writable vs readable).
    """
    # Basic throttling between calls
    time.sleep(RATE_LIMIT_DELAY)

    # Build logging context
    log_ctx = {"command": " ".join(args)}
    if repo:
        log_ctx["repo"] = repo

    # Auto-select token based on repo if not explicitly provided
    if token is None and repo:
        token = get_github_token_for_repo(repo)

    # Prepare environment with token if available
    env = None
    if token:
        env = os.environ.copy()
        env["GH_TOKEN"] = token

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
                env=env,
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
                        **log_ctx,
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        "Rate limit exceeded after max retries",
                        retries=RATE_LIMIT_MAX_RETRIES,
                        **log_ctx,
                    )
                    return None
            else:
                # Include full stderr for debugging - common issues:
                # - "gh: command not found" - gh CLI not installed
                # - "authentication required" - not logged in
                # - "HTTP 404" - repo doesn't exist or no access
                # - "HTTP 403" - rate limit or permission denied
                stderr_msg = e.stderr.strip() if e.stderr else "(no stderr)"
                logger.error(
                    "gh command failed",
                    return_code=e.returncode,
                    stderr=stderr_msg,
                    **log_ctx,
                )
                return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse gh output as JSON",
                error=str(e),
                **log_ctx,
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out", **log_ctx)
            return None

    return None


def gh_text(args: list[str], repo: str | None = None, token: str | None = None) -> str | None:
    """Run gh CLI command and return text output with rate limit handling.

    Implements exponential backoff on rate limit errors and basic throttling
    between calls to prevent hitting rate limits.

    Args:
        args: Arguments to pass to gh CLI
        repo: Optional repository context for token selection
        token: Optional explicit GitHub token (overrides auto-selection)

    If repo is provided and token is not, automatically selects the appropriate
    token based on repo access level (writable vs readable).
    """
    # Basic throttling between calls
    time.sleep(RATE_LIMIT_DELAY)

    # Auto-select token based on repo if not explicitly provided
    if token is None and repo:
        token = get_github_token_for_repo(repo)

    # Prepare environment with token if available
    env = None
    if token:
        env = os.environ.copy()
        env["GH_TOKEN"] = token

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
                env=env,
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
    # Generate unique workflow ID for this invocation
    # Format: gw-{task_type}-{timestamp}-{random_hex}
    # - timestamp provides second-level uniqueness (YYYYMMDD-HHMMSS)
    # - secrets.token_hex(4) generates 8 hex chars (4 bytes = 32 bits of randomness)
    # - Collision probability: ~1 in 4 billion for same-second invocations
    # - Given timestamp prefix, practical collision risk is negligible
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    workflow_id = f"gw-{task_type}-{timestamp}-{secrets.token_hex(4)}"

    # Add workflow context to the task context
    context["workflow_id"] = workflow_id
    context["workflow_type"] = task_type

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
        log_extra["is_rereview"] = context.get("is_rereview", False)
    elif task_type == "pr_review_response":
        log_extra["pr_number"] = context.get("pr_number")
        log_extra["pr_title"] = context.get("pr_title", "")[:60]
        log_extra["review_count"] = len(context.get("reviews", []))
        log_extra["line_comment_count"] = len(context.get("line_comments", []))

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
                    if any(
                        kw in line_lower for kw in ["error:", "failed:", "exception:", "traceback"]
                    ):
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


VALID_READONLY_TASK_TYPES = [
    "check_failure",
    "comment",
    "review_request",
    "merge_conflict",
    "pr_review_response",
]


def send_readonly_notification(task_type: str, context: dict) -> bool:
    """Send a Slack notification for a read-only repo event.

    For read-only repos, we don't invoke jib to make changes.
    Instead, we send a Slack notification with the event details.

    Args:
        task_type: One of 'check_failure', 'comment', 'review_request', 'merge_conflict'
        context: Dict containing task-specific context

    Returns:
        True if notification was sent successfully
    """
    HOST_NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)

    repo = context.get("repository", "unknown")
    pr_number = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")

    # Generate task ID for threading
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_id = f"readonly-{task_type}-{repo.replace('/', '-')}-{pr_number}-{timestamp}"

    # Build notification content based on task type
    if task_type == "check_failure":
        failed_checks = context.get("failed_checks", [])
        check_list = "\n".join(f"- {c.get('name', 'Unknown')}" for c in failed_checks)

        title = f"Check Failures in {repo} PR #{pr_number}"
        body = f"""**Repository**: {repo} _(read-only)_
**PR**: [{pr_title}]({pr_url}) (#{pr_number})
**Branch**: `{pr_branch}` -> `{base_branch}`

## Failed Checks

{check_list}

## Note

This is a **read-only repository**. jib cannot push fixes directly.
Please review the failures and make changes manually."""

    elif task_type == "comment":
        comments = context.get("comments", [])
        # Format comments (limit to 5)
        comment_sections = []
        for c in comments[:5]:
            author = c.get("author", "Unknown")
            body_preview = c.get("body", "")[:300]
            if len(c.get("body", "")) > 300:
                body_preview += "..."
            comment_type = c.get("type", "comment")
            comment_sections.append(f"**{author}** ({comment_type}):\n> {body_preview}")
        comments_text = "\n\n".join(comment_sections)

        title = f"New Comments in {repo} PR #{pr_number}"
        body = f"""**Repository**: {repo} _(read-only)_
**PR**: [{pr_title}]({pr_url}) (#{pr_number})

## New Comments ({len(comments)} total)

{comments_text}

## Note

This is a **read-only repository**. jib cannot respond on GitHub.
If you'd like jib to respond, please paste your response in this thread."""

    elif task_type == "review_request":
        author = context.get("author", "unknown")
        additions = context.get("additions", 0)
        deletions = context.get("deletions", 0)
        files = context.get("files", [])
        is_rereview = context.get("is_rereview", False)

        # Format files list (limit to 10)
        files_preview = files[:10]
        files_text = "\n".join(f"- `{f}`" for f in files_preview)
        if len(files) > 10:
            files_text += f"\n- ... and {len(files) - 10} more files"

        if is_rereview:
            title = f"PR Re-Review Request: {repo} #{pr_number}"
            review_type_note = "**Type**: Re-review (new commits since last review)"
        else:
            title = f"PR Review Request: {repo} #{pr_number}"
            review_type_note = ""

        body = f"""**Repository**: {repo} _(read-only)_
**PR**: [{pr_title}]({pr_url}) (#{pr_number})
**Author**: @{author}
**Branch**: `{pr_branch}` -> `{base_branch}`
**Changes**: +{additions} / -{deletions}
{review_type_note}

## Files Changed

{files_text}

## Note

This is a **read-only repository**. jib cannot post review comments on GitHub.
Feedback is provided in this Slack thread instead."""

    elif task_type == "merge_conflict":
        title = f"Merge Conflict in {repo} PR #{pr_number}"
        body = f"""**Repository**: {repo} _(read-only)_
**PR**: [{pr_title}]({pr_url}) (#{pr_number})
**Branch**: `{pr_branch}` -> `{base_branch}`

## Merge Conflict Detected

This PR has merge conflicts that need to be resolved.

## Note

This is a **read-only repository**. jib cannot resolve conflicts automatically.
Please resolve the conflicts manually by merging `{base_branch}` into `{pr_branch}`."""

    elif task_type == "pr_review_response":
        reviews = context.get("reviews", [])
        line_comments = context.get("line_comments", [])

        # Format reviews
        reviews_text = ""
        for r in reviews[:5]:
            reviewer = r.get("author", "Unknown")
            state = r.get("state", "COMMENTED")
            review_body = r.get("body", "")[:300]
            if len(r.get("body", "")) > 300:
                review_body += "..."
            reviews_text += f"\n**{reviewer}** ({state}):\n> {review_body}\n"

        # Format line comments
        comments_text = ""
        for c in line_comments[:5]:
            author = c.get("author", "Unknown")
            path = c.get("path", "unknown")
            line = c.get("line", "?")
            comment_body = c.get("body", "")[:200]
            if len(c.get("body", "")) > 200:
                comment_body += "..."
            comments_text += f"\n**{author}** on `{path}:{line}`:\n> {comment_body}\n"

        if len(line_comments) > 5:
            comments_text += f"\n- ... and {len(line_comments) - 5} more comments"

        title = f"PR Review Feedback: {repo} #{pr_number}"
        body = f"""**Repository**: {repo} _(read-only)_
**PR**: [{pr_title}]({pr_url}) (#{pr_number})
**Branch**: `{pr_branch}` -> `{base_branch}`

## Reviews ({len(reviews)} total)

{reviews_text if reviews_text else "No review body comments."}

## Line Comments ({len(line_comments)} total)

{comments_text if comments_text else "No inline comments."}

## Note

This is a **read-only repository**. jib cannot respond to reviews or push changes.
Please address the feedback manually."""

    else:
        logger.error(
            "Unknown task type for readonly notification",
            task_type=task_type,
            valid_types=VALID_READONLY_TASK_TYPES,
        )
        return False

    # Build notification file content with YAML frontmatter
    file_content = f"""---
task_id: "{task_id}"
---

# {title}

{body}

---
Repo: {repo} | PR: #{pr_number} | Branch: `{pr_branch}` | Source: readonly-watcher
"""

    # Write notification file
    filename = f"{timestamp}-{task_id}.md"
    filepath = HOST_NOTIFICATIONS_DIR / filename

    try:
        filepath.write_text(file_content)
        logger.info(
            "Read-only notification sent",
            task_type=task_type,
            repository=repo,
            pr_number=pr_number,
            notification_file=str(filepath),
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to write readonly notification",
            task_type=task_type,
            repository=repo,
            pr_number=pr_number,
            error=str(e),
        )
        return False


def execute_task(task: JibTask, safe_state: ThreadSafeState) -> bool:
    """Execute a single jib task and update state (thread-safe).

    For writable repos, invokes jib to handle the task (push fixes, post comments).
    For read-only repos, sends a Slack notification instead.

    Args:
        task: The JibTask to execute
        safe_state: Thread-safe state manager

    Returns:
        True if task completed successfully
    """
    if task.is_readonly:
        # Read-only repo: send notification instead of invoking jib
        success = send_readonly_notification(task.task_type, task.context)
    else:
        # Writable repo: invoke jib to handle the task
        success = invoke_jib(task.task_type, task.context)

    if success:
        safe_state.mark_processed(task.signature_key, task.signature_value)
    else:
        # Mark as failed for retry on next run
        safe_state.mark_failed(task.signature_value, task.task_type, task.context)
    return success


def execute_tasks_parallel(tasks: list[JibTask], safe_state: ThreadSafeState) -> int:
    """Execute multiple jib tasks in parallel.

    Args:
        tasks: List of JibTask objects to execute
        safe_state: Thread-safe state manager

    Returns:
        Number of successfully completed tasks
    """
    if not tasks:
        return 0

    completed = 0
    max_workers = min(MAX_PARALLEL_JIB, len(tasks))

    logger.info(
        "Executing tasks in parallel",
        task_count=len(tasks),
        max_workers=max_workers,
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {executor.submit(execute_task, task, safe_state): task for task in tasks}

        # Process completed tasks as they finish
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                if future.result():
                    completed += 1
            except Exception as e:
                logger.error(
                    "Task execution failed with exception",
                    task_type=task.task_type,
                    repository=task.context.get("repository", "unknown"),
                    pr_number=task.context.get("pr_number"),
                    error=str(e),
                )

    logger.info(
        "Parallel execution completed",
        completed=completed,
        total=len(tasks),
    )

    return completed


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
        ],
        repo=repo,
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

    Note: There are THREE types of comments on a PR:
    1. Issue comments (comments field) - general PR discussion
    2. Review body comments (reviews field) - summary text when submitting a review
    3. Line-level review comments - comments on specific lines of code in the diff
       These are NOT included in gh pr view output, must use gh api separately.
    """
    pr_num = pr_data["number"]

    # Get PR issue comments and review body comments
    comments = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "comments,reviews",
        ],
        repo=repo,
    )

    if comments is None:
        return None

    all_comments = []

    # Regular issue comments (general PR discussion)
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

    # Review body comments (summary text when submitting a review)
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

    # Line-level review comments (comments on specific lines of code)
    # These are NOT included in gh pr view, must fetch via API separately
    review_comments = gh_json(
        [
            "api",
            f"repos/{repo}/pulls/{pr_num}/comments",
        ],
        repo=repo,
    )

    if review_comments:
        for rc in review_comments:
            # Note: API returns created_at (snake_case), not createdAt (camelCase)
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

    # Debug: show comment count by type
    comment_types = {}
    for c in all_comments:
        ctype = c.get("type", "unknown")
        comment_types[ctype] = comment_types.get(ctype, 0) + 1
    logger.debug(
        "Found comments on PR",
        pr_number=pr_num,
        comment_count=len(all_comments),
        comment_types=comment_types,
    )

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

    # Check if there are failed tasks for this PR that need retry
    failed_tasks = state.get("failed_tasks", {})
    has_failed_comment_task = any(
        info.get("task_type") == "comment"
        and info.get("repository") == repo
        and info.get("pr_number") == pr_num
        for info in failed_tasks.values()
    )

    # Filter by since_timestamp if provided (only show comments newer than last run)
    # UNLESS there's a failed task that needs retry for this PR
    # Use >= to avoid missing comments that occur at exactly the same timestamp
    if since_timestamp and not has_failed_comment_task:
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
    elif has_failed_comment_task:
        logger.info(
            "Skipping timestamp filter due to failed task retry",
            pr_number=pr_num,
            repository=repo,
        )

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
        ],
        repo=repo,
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


def check_pr_for_review_response(
    repo: str,
    pr_data: dict,
    state: dict,
    bot_username: str,
    since_timestamp: str | None = None,
) -> dict | None:
    """Check a bot's PR for reviews that need response.

    This function detects when someone reviews a PR created by the bot,
    and creates a task for the bot to respond to the review feedback.

    Args:
        repo: Repository in owner/repo format
        pr_data: PR data dict with number, title, url, etc.
        state: State dict with processed_review_responses
        bot_username: Bot's username (to identify bot's own PRs)
        since_timestamp: ISO timestamp to filter reviews (only show newer)

    Returns context dict if new reviews found that need response.
    """
    pr_num = pr_data["number"]

    # Get reviews on this PR
    reviews_data = gh_json(
        [
            "pr",
            "view",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "reviews,reviewRequests",
        ],
        repo=repo,
    )

    if reviews_data is None:
        return None

    reviews = reviews_data.get("reviews", [])
    if not reviews:
        return None

    # Filter to reviews NOT from the bot
    bot_variants = {
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
        f"app/{bot_username.lower()}",
    }

    # Find reviews that aren't from the bot
    other_reviews = [
        r for r in reviews if r.get("author", {}).get("login", "").lower() not in bot_variants
    ]

    if not other_reviews:
        logger.debug(
            "No reviews from others on bot PR",
            pr_number=pr_num,
        )
        return None

    # Filter by since_timestamp if provided
    if since_timestamp:
        other_reviews = [r for r in other_reviews if r.get("submittedAt", "") >= since_timestamp]
        if not other_reviews:
            return None  # No new reviews since last run

    # Get the most recent review
    # Sort by submittedAt descending
    other_reviews.sort(key=lambda r: r.get("submittedAt", ""), reverse=True)
    latest_review = other_reviews[0]

    # Create signature based on latest review
    review_id = latest_review.get("id", "")
    review_response_signature = f"{repo}-{pr_num}:review_response:{review_id}"

    if review_response_signature in state.get("processed_review_responses", {}):
        processed_at = state["processed_review_responses"].get(review_response_signature, "unknown")
        logger.debug(
            "Review already processed for response",
            pr_number=pr_num,
            processed_at=processed_at,
            reviewer=latest_review.get("author", {}).get("login", "unknown"),
        )
        return None  # Already processed

    # Get line-level review comments for this PR
    review_comments = gh_json(
        [
            "api",
            f"repos/{repo}/pulls/{pr_num}/comments",
        ],
        repo=repo,
    )

    # Compile review information
    review_info = []
    for r in other_reviews:
        review_entry = {
            "id": r.get("id", ""),
            "author": r.get("author", {}).get("login", "unknown"),
            "state": r.get(
                "state", "COMMENTED"
            ),  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
            "body": r.get("body", ""),
            "submitted_at": r.get("submittedAt", ""),
        }
        review_info.append(review_entry)

    # Parse line-level comments
    line_comments = []
    if review_comments:
        for rc in review_comments:
            # Only include comments from non-bot users
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

    logger.info(
        "Bot PR has reviews needing response",
        pr_number=pr_num,
        pr_title=pr_data.get("title", "")[:80],
        review_count=len(review_info),
        line_comment_count=len(line_comments),
        latest_reviewer=latest_review.get("author", {}).get("login", "unknown"),
        latest_state=latest_review.get("state", "COMMENTED"),
    )

    # Get PR diff for context
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

    Note: Review signatures include head_sha to trigger re-reviews when new commits
    are pushed to a PR branch. This ensures the reviewer sees the latest code.
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

    # Check for failed review tasks that need retry
    failed_tasks = state.get("failed_tasks", {})
    failed_review_pr_numbers = {
        info.get("pr_number")
        for info in failed_tasks.values()
        if info.get("task_type") == "review_request" and info.get("repository") == repo
    }

    # Filter by since_timestamp if provided (only show PRs created after last run)
    # UNLESS the PR has a failed task that needs retry
    # Use >= to avoid missing PRs that occur at exactly the same timestamp
    if since_timestamp:
        other_prs = [
            p
            for p in other_prs
            if p.get("createdAt", "") >= since_timestamp or p["number"] in failed_review_pr_numbers
        ]
        if not other_prs:
            return []  # No new PRs since last run

    results = []
    for pr in other_prs:
        pr_num = pr["number"]
        head_sha = pr.get("headRefOid", "")

        # Include head_sha in signature so new commits trigger re-reviews
        # This mirrors the pattern used for processed_failures
        review_signature = f"{repo}-{pr_num}-{head_sha}:review"

        # Check if this specific commit has already been reviewed
        if review_signature in state.get("processed_reviews", {}):
            processed_at = state["processed_reviews"].get(review_signature, "unknown")
            logger.debug(
                "PR commit already reviewed",
                pr_number=pr_num,
                commit=head_sha[:8] if head_sha else "unknown",
                processed_at=processed_at,
            )
            continue

        # Determine if this is a re-review (different commit was previously reviewed)
        # Check if any previous review exists for this PR (regardless of commit)
        pr_review_prefix = f"{repo}-{pr_num}-"
        is_rereview = any(
            sig.startswith(pr_review_prefix) and sig.endswith(":review")
            for sig in state.get("processed_reviews", {})
        )

        if is_rereview:
            logger.info(
                "PR has new commits since last review - triggering re-review",
                pr_number=pr_num,
                pr_title=pr.get("title", "")[:80],
                author=pr.get("author", {}).get("login", "unknown"),
                new_commit=head_sha[:8] if head_sha else "unknown",
            )
        else:
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


def process_repo_prs(
    repo: str,
    state: dict,
    github_username: str,
    bot_username: str,
    since_timestamp: str | None,
    is_readonly: bool = False,
) -> list[JibTask]:
    """Process a single repository's PRs and collect tasks.

    This is shared logic for both writable and readable repos.

    Args:
        repo: Repository in owner/repo format
        state: State dict for deduplication
        github_username: User's GitHub username
        bot_username: Bot's GitHub username
        since_timestamp: Filter for comments since this timestamp
        is_readonly: If True, tasks will be marked for notification instead of jib invocation

    Returns:
        List of JibTask objects for this repo
    """
    tasks: list[JibTask] = []

    # Fetch ALL open PRs in a single API call
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
        ],
        repo=repo,
    )

    if all_prs is None:
        logger.warning("Failed to fetch PRs, skipping repository")
        return tasks

    logger.info("Fetched open PRs", count=len(all_prs))

    # Filter PRs locally by author
    my_prs = [
        p
        for p in all_prs
        if p.get("author", {}).get("login", "").lower() == github_username.lower()
    ]

    # Bot PRs can have author login in different formats
    bot_author_variants = {
        bot_username.lower(),
        f"{bot_username.lower()}[bot]",
        f"app/{bot_username.lower()}",
    }
    bot_prs = [
        p for p in all_prs if p.get("author", {}).get("login", "").lower() in bot_author_variants
    ]

    # Collect tasks from user's PRs
    if my_prs:
        logger.info(
            "Found user's open PRs",
            count=len(my_prs),
            username=github_username,
        )

        for pr in my_prs:
            # Check for failures
            failure_ctx = check_pr_for_failures(repo, pr, state)
            if failure_ctx:
                tasks.append(
                    JibTask(
                        task_type="check_failure",
                        context=failure_ctx,
                        signature_key="processed_failures",
                        signature_value=failure_ctx["failure_signature"],
                        is_readonly=is_readonly,
                    )
                )

            # Check for comments
            comment_ctx = check_pr_for_comments(repo, pr, state, bot_username, since_timestamp)
            if comment_ctx:
                tasks.append(
                    JibTask(
                        task_type="comment",
                        context=comment_ctx,
                        signature_key="processed_comments",
                        signature_value=comment_ctx["comment_signature"],
                        is_readonly=is_readonly,
                    )
                )

            # Check for merge conflicts
            conflict_ctx = check_pr_for_merge_conflict(repo, pr, state)
            if conflict_ctx:
                tasks.append(
                    JibTask(
                        task_type="merge_conflict",
                        context=conflict_ctx,
                        signature_key="processed_conflicts",
                        signature_value=conflict_ctx["conflict_signature"],
                        is_readonly=is_readonly,
                    )
                )
    else:
        logger.debug("No open PRs authored by user", username=github_username)

    # Collect tasks from bot's PRs (only for writable repos - bot doesn't create PRs in readonly)
    if bot_prs and not is_readonly:
        logger.info(
            "Found bot's open PRs",
            count=len(bot_prs),
            bot_username=bot_username,
        )

        for pr in bot_prs:
            # Check for failures on bot's PRs
            failure_ctx = check_pr_for_failures(repo, pr, state)
            if failure_ctx:
                tasks.append(
                    JibTask(
                        task_type="check_failure",
                        context=failure_ctx,
                        signature_key="processed_failures",
                        signature_value=failure_ctx["failure_signature"],
                        is_readonly=False,
                    )
                )

            # Check for comments on bot's PRs
            comment_ctx = check_pr_for_comments(repo, pr, state, bot_username, since_timestamp)
            if comment_ctx:
                tasks.append(
                    JibTask(
                        task_type="comment",
                        context=comment_ctx,
                        signature_key="processed_comments",
                        signature_value=comment_ctx["comment_signature"],
                        is_readonly=False,
                    )
                )

            # Check for merge conflicts on bot's PRs
            conflict_ctx = check_pr_for_merge_conflict(repo, pr, state)
            if conflict_ctx:
                tasks.append(
                    JibTask(
                        task_type="merge_conflict",
                        context=conflict_ctx,
                        signature_key="processed_conflicts",
                        signature_value=conflict_ctx["conflict_signature"],
                        is_readonly=False,
                    )
                )

            # Check for reviews on bot's PRs that need response
            review_response_ctx = check_pr_for_review_response(
                repo, pr, state, bot_username, since_timestamp
            )
            if review_response_ctx:
                tasks.append(
                    JibTask(
                        task_type="pr_review_response",
                        context=review_response_ctx,
                        signature_key="processed_review_responses",
                        signature_value=review_response_ctx["review_response_signature"],
                        is_readonly=False,
                    )
                )

    # Collect review tasks for PRs from others
    review_contexts = check_prs_for_review(
        repo, all_prs, state, github_username, bot_username, since_timestamp
    )
    for review_ctx in review_contexts:
        tasks.append(
            JibTask(
                task_type="review_request",
                context=review_ctx,
                signature_key="processed_reviews",
                signature_value=review_ctx["review_signature"],
                is_readonly=is_readonly,
            )
        )

    return tasks


def main():
    """Main entry point - scan configured repos and trigger jib as needed.

    Tasks are collected first, then executed in parallel for faster processing.
    Writable repos get full jib handling (push, comment, PR creation).
    Readable repos get Slack notifications only.
    """
    # Record when this run STARTS - this is what we'll use for next run's "since"
    current_run_start = utc_now_iso()

    logger.info(
        "GitHub Watcher starting",
        local_time=datetime.now().isoformat(),
        utc_time=current_run_start,
        max_parallel=MAX_PARALLEL_JIB,
    )

    # Load config
    config = load_config()
    writable_repos = config.get("writable_repos", [])
    readable_repos = config.get("readable_repos", [])
    github_username = config.get("github_username", "jib")
    bot_username = config.get("bot_username", "jib")

    all_repos = writable_repos + readable_repos
    if not all_repos:
        logger.warning("No repositories configured - check config/repositories.yaml")
        return 0

    logger.info(
        "Configuration loaded",
        github_username=github_username,
        bot_username=bot_username,
        writable_repo_count=len(writable_repos),
        readable_repo_count=len(readable_repos),
        writable_repos=writable_repos,
        readable_repos=readable_repos,
    )

    # Load state
    state = load_state()

    # Check for failed tasks that need retry
    failed_tasks = state.get("failed_tasks", {})
    if failed_tasks:
        logger.info(
            "Found failed tasks from previous runs - will retry",
            failed_task_count=len(failed_tasks),
            failed_tasks=[
                f"{info.get('repository', 'unknown')}#{info.get('pr_number', '?')} ({info.get('task_type', 'unknown')})"
                for info in failed_tasks.values()
            ],
        )

    # Get the timestamp from when the PREVIOUS run started (for comment filtering)
    since_timestamp = get_since_timestamp(state)
    if since_timestamp:
        logger.info("Checking for comments since last run", since=since_timestamp)
    else:
        logger.info("First run - checking all open items")
    logger.debug("PR check failures: checking ALL open PRs unconditionally")

    logger.info(
        "Scanning repositories",
        total=len(all_repos),
        writable=len(writable_repos),
        readable=len(readable_repos),
    )

    # Collect all tasks first, then execute in parallel
    all_tasks: list[JibTask] = []

    # Process writable repos (full jib handling)
    for repo in writable_repos:
        with ContextScope(repository=repo, access_level="writable"):
            logger.info("Processing writable repository")
            tasks = process_repo_prs(
                repo, state, github_username, bot_username, since_timestamp, is_readonly=False
            )
            all_tasks.extend(tasks)

    # Process readable repos (notification only)
    for repo in readable_repos:
        with ContextScope(repository=repo, access_level="readable"):
            logger.info("Processing read-only repository")
            tasks = process_repo_prs(
                repo, state, github_username, bot_username, since_timestamp, is_readonly=True
            )
            all_tasks.extend(tasks)

    # Log task summary
    if all_tasks:
        task_types = {}
        readonly_count = 0
        for task in all_tasks:
            task_types[task.task_type] = task_types.get(task.task_type, 0) + 1
            if task.is_readonly:
                readonly_count += 1
        logger.info(
            "Tasks collected",
            total=len(all_tasks),
            by_type=task_types,
            readonly_tasks=readonly_count,
            writable_tasks=len(all_tasks) - readonly_count,
        )

        # Execute all tasks in parallel
        safe_state = ThreadSafeState(state)
        tasks_completed = execute_tasks_parallel(all_tasks, safe_state)
        state = safe_state.get_state()
    else:
        logger.info("No tasks to execute")
        tasks_completed = 0

    # Update last run START timestamp and save state
    # We store when this run STARTED so next run checks for comments since then
    state["last_run_start"] = current_run_start
    save_state(state)

    # Summary statistics for completed run
    logger.info(
        "GitHub Watcher completed",
        tasks_completed=tasks_completed,
        tasks_collected=len(all_tasks),
        repositories_scanned=len(all_repos),
        writable_repos_scanned=len(writable_repos),
        readable_repos_scanned=len(readable_repos),
        next_check_since=current_run_start,
        processed_failures_count=len(state.get("processed_failures", {})),
        processed_comments_count=len(state.get("processed_comments", {})),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
