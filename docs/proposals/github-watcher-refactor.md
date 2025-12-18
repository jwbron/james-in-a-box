# GitHub Watcher Refactor: Splitting into Three Services

## Summary

Refactor the monolithic `github-watcher.py` into three distinct services with clear responsibilities:

1. **Comment Responder** - Respond to PR comments
2. **PR Reviewer** - Review PRs using collaborative development framework
3. **CI/Conflict Fixer** - Fix check failures and merge conflicts

## Current State Analysis

### Existing Architecture

The current `github-watcher.py` (~2300 lines) handles all GitHub PR monitoring in a single service:
- Check failure detection and fixing
- Comment detection and response
- Merge conflict detection and resolution
- PR review requests (from others)
- Review response handling (on bot's own PRs)

**Current Scope Logic:**
- **Writable repos**: Full functionality for user's PRs, bot's PRs, and reviewing other authors' PRs
- **Read-only repos**: Notification-only mode, limited functionality

### Current Trigger Conditions

| Task Type | Current Trigger | Proposed Service |
|-----------|-----------------|------------------|
| `check_failure` | User's PRs + Bot's PRs (writable repos) | CI/Conflict Fixer |
| `merge_conflict` | User's PRs + Bot's PRs (writable repos) | CI/Conflict Fixer |
| `comment` | User's PRs + Bot's PRs | Comment Responder |
| `review_request` | All PRs from other authors (proactive) | PR Reviewer |
| `pr_review_response` | Bot's PRs receiving reviews | Comment Responder |

---

## Proposed Architecture

### Service 1: Comment Responder (`comment-responder`)

**Purpose**: Respond to comments and review feedback on PRs where jib is engaged.

**Trigger Conditions:**
- PRs where `james-in-a-box` is **assigned**
- PRs where `james-in-a-box` is **tagged** (mentioned in comment)
- PRs where `james-in-a-box` is the **author**

**Task Types:**
- `comment` - Respond to new comments
- `pr_review_response` - Address review feedback on bot's PRs

**Capabilities:**
- Post comments via `gh pr comment`
- Push code changes to address feedback
- Update PR descriptions

**Repos:** All configured `writable_repos`

---

### Service 2: PR Reviewer (`pr-reviewer`)

**Purpose**: Review PRs where jib's review is requested, using collaborative development framework.

**Trigger Conditions:**
- PRs where `james-in-a-box` is **assigned** (as reviewer)
- PRs where `james-in-a-box` is **tagged** (mentioned requesting review)

**Task Types:**
- `review_request` - Perform code review

**Capabilities:**
- Post reviews via `gh pr review`
- Post inline comments
- (Future) Apply collaborative development framework methodology

**Repos:** All configured `writable_repos` + `readable_repos` (for read-only, output to Slack)

**Note:** This is a change from current behavior, which proactively reviews *all* PRs from other authors. The new behavior is opt-in (jib must be explicitly assigned/tagged).

---

### Service 3: CI/Conflict Fixer (`ci-fixer`)

**Purpose**: Automatically fix check failures and merge conflicts on PRs authored by jib or the configured user.

**Trigger Conditions:**
- PRs authored by `james-in-a-box` (bot)
- PRs authored by `github_username` (configured user, e.g., `jwbron`)

**Task Types:**
- `check_failure` - Detect and fix failing CI checks
- `merge_conflict` - Detect and resolve merge conflicts

**Capabilities:**
- Push code fixes
- Merge base branch
- Post status comments

**Repos:** All configured `writable_repos`

**Note:** This service is automatic - it monitors all PRs from jib/user without needing assignment.

---

## Configuration Changes

### `repositories.yaml` Additions

```yaml
# Existing config...
github_username: jwbron
bot_username: james-in-a-box

writable_repos:
  - jwbron/james-in-a-box
  - jwbron/collaborative-development-framework

# NEW: Control which services are enabled per repo
repo_settings:
  jwbron/james-in-a-box:
    restrict_to_configured_users: true
    disable_auto_fix: true  # Existing - disable CI fixer
    # NEW options:
    disable_comment_responder: false  # Default: enabled
    disable_pr_reviewer: false        # Default: enabled
    disable_ci_fixer: false           # Default: enabled (overridden by disable_auto_fix)
```

---

## Questions for Review

### Q1: PR Reviewer Scope

**Current behavior:** Reviews ALL PRs from other authors in writable repos (proactive review).

**Proposed behavior:** Only review PRs where jib is explicitly assigned or tagged.

**Question:** Is this change correct? Should jib still proactively review all PRs, or should it wait to be asked?

**Trade-offs:**
- **Opt-in (proposed):** Less noise, more respectful, but requires explicit assignment
- **Proactive (current):** Ensures all PRs get reviewed, but may be unwanted

### Q2: Comment Responder - "Tagged" Definition

**Question:** What constitutes being "tagged"?

Options:
1. **Mentioned in comment body** - e.g., "@james-in-a-box can you look at this?"
2. **Review requested** - Explicitly added as reviewer via GitHub UI
3. **Both** - Respond to either trigger

Recommendation: Start with **both** - respond when mentioned OR when added as reviewer.

### Q3: Service Scheduling

**Current:** Single timer runs every 5 minutes, executes all checks.

**Options:**
1. **Single timer, three services** - Timer triggers a dispatcher that runs all three
2. **Three separate timers** - Each service has its own timer (allows different intervals)
3. **Shared timer, parallel execution** - Single timer runs all three in parallel

**Decision:** **Option 2** - Three separate systemd services and timers for maximum flexibility and isolation.

### Q4: Read-Only Repo Behavior

**Question:** Should the PR Reviewer service work on read-only repos?

**Current behavior:** For read-only repos, review output goes to Slack instead of GitHub.

**Proposed behavior:** Same - if jib is tagged for review in a read-only repo, output review to Slack.

### Q5: State Management

**Current:** Single `~/.local/share/github-watcher/state.json` tracks all processed items.

**Options:**
1. **Keep unified state** - All three services share one state file
2. **Separate state files** - Each service has its own state file
3. **Namespaced state** - Single file with namespaced keys per service

Recommendation: **Option 3** - Single file, but keys prefixed by service (e.g., `comment_responder.processed_comments`).

---

## Detailed Implementation Plan

### Phase 1: Extract Shared Code (Foundation)

#### 1.1 Create Directory Structure

```bash
mkdir -p host-services/analysis/github-watcher/lib
touch host-services/analysis/github-watcher/lib/__init__.py
```

#### 1.2 Extract `lib/github_api.py`

This module encapsulates all GitHub CLI interactions with rate limiting:

```python
#!/usr/bin/env python3
"""GitHub API wrapper using gh CLI with rate limiting."""

import json
import subprocess
import time
from typing import Any

from jib_logging import get_logger

logger = get_logger("github-api")

# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BASE_WAIT = 60  # Base wait for exponential backoff


def gh_json(args: list[str], repo: str | None = None) -> dict | list | None:
    """Run gh CLI command and return JSON output with rate limit handling.

    Args:
        args: Arguments to pass to gh CLI (e.g., ["pr", "view", "123"])
        repo: Optional repository context for logging

    Returns:
        Parsed JSON response, or None on failure

    Example:
        >>> gh_json(["pr", "view", "123", "--repo", "owner/repo", "--json", "number,title"])
        {"number": 123, "title": "My PR"}
    """
    time.sleep(RATE_LIMIT_DELAY)

    log_ctx = {"command": " ".join(args)}
    if repo:
        log_ctx["repo"] = repo

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
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning("Rate limited, retrying", wait_seconds=wait_time, attempt=attempt + 1, **log_ctx)
                    time.sleep(wait_time)
                    continue
                logger.error("Rate limit exceeded after max retries", **log_ctx)
            else:
                logger.error("gh command failed", stderr=e.stderr.strip(), **log_ctx)
            return None
        except json.JSONDecodeError as e:
            logger.error("Failed to parse gh output as JSON", error=str(e), **log_ctx)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out", **log_ctx)
            return None

    return None


def gh_text(args: list[str], repo: str | None = None) -> str | None:
    """Run gh CLI command and return text output with rate limit handling.

    Args:
        args: Arguments to pass to gh CLI
        repo: Optional repository context for logging

    Returns:
        Raw text output, or None on failure

    Example:
        >>> gh_text(["pr", "diff", "123", "--repo", "owner/repo"])
        "diff --git a/file.py b/file.py\\n..."
    """
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
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning("Rate limited, retrying", wait_seconds=wait_time, attempt=attempt + 1)
                    time.sleep(wait_time)
                    continue
                logger.error("Rate limit exceeded after max retries")
            else:
                logger.error("gh command failed", stderr=e.stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out")
            return None

    return None


def check_gh_auth() -> bool:
    """Check if gh CLI is authenticated.

    Returns:
        True if authenticated, False otherwise
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n") + result.stderr.split("\n"):
                if "Logged in to" in line:
                    logger.info("gh CLI authenticated", auth_info=line.strip())
                    return True
            logger.info("gh CLI authenticated")
            return True
        else:
            logger.error("gh CLI is not authenticated. Please run: gh auth login")
            return False
    except FileNotFoundError:
        logger.error("gh CLI not found. Please install GitHub CLI")
        return False
    except subprocess.TimeoutExpired:
        logger.error("gh auth status timed out")
        return False
```

#### 1.3 Extract `lib/state.py`

This module handles persistent state management:

```python
#!/usr/bin/env python3
"""State management for GitHub watcher services."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jib_logging import get_logger

logger = get_logger("github-state")

STATE_DIR = Path.home() / ".local" / "share" / "github-watcher"
STATE_FILE = STATE_DIR / "state.json"


def utc_now_iso() -> str:
    """Get current UTC time in ISO format with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> dict:
    """Load previous notification state to avoid duplicate processing.

    Returns:
        State dict with all expected keys initialized
    """
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open() as f:
                state = json.load(f)
                # Ensure all expected keys exist
                state.setdefault("processed_failures", {})
                state.setdefault("processed_comments", {})
                state.setdefault("processed_reviews", {})
                state.setdefault("processed_conflicts", {})
                state.setdefault("processed_review_responses", {})
                state.setdefault("failed_tasks", {})
                state.setdefault("last_run_start", None)
                return state
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to load state file", error=str(e))

    return {
        "processed_failures": {},
        "processed_comments": {},
        "processed_reviews": {},
        "processed_conflicts": {},
        "processed_review_responses": {},
        "failed_tasks": {},
        "last_run_start": None,
    }


def save_state(state: dict, update_last_run: bool = False) -> None:
    """Save notification state.

    Args:
        state: The state dict to save
        update_last_run: If True, update last_run_start to current time
    """
    if update_last_run:
        state["last_run_start"] = utc_now_iso()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


class ThreadSafeState:
    """Thread-safe wrapper for state management.

    Example:
        >>> state = load_state()
        >>> safe_state = ThreadSafeState(state)
        >>> safe_state.mark_processed("processed_comments", "repo-123:abc")
        >>> safe_state.mark_failed("repo-123:abc", "comment", {"repository": "owner/repo"})
    """

    def __init__(self, state: dict):
        self._state = state
        self._lock = threading.Lock()

    def mark_processed(self, key: str, signature: str) -> None:
        """Mark a task as processed (thread-safe)."""
        with self._lock:
            self._state.setdefault(key, {})[signature] = utc_now_iso()
            # Remove from failed_tasks if this was a retry
            if signature in self._state.get("failed_tasks", {}):
                del self._state["failed_tasks"][signature]
            self._save()

    def mark_failed(self, signature: str, task_type: str, context: dict) -> None:
        """Mark a task as failed for later retry (thread-safe)."""
        with self._lock:
            self._state.setdefault("failed_tasks", {})[signature] = {
                "failed_at": utc_now_iso(),
                "task_type": task_type,
                "repository": context.get("repository", "unknown"),
                "pr_number": context.get("pr_number"),
            }
            self._save()

    def is_processed(self, key: str, signature: str) -> bool:
        """Check if a signature has been processed (thread-safe)."""
        with self._lock:
            return signature in self._state.get(key, {})

    def get_state(self) -> dict:
        """Get a copy of current state."""
        with self._lock:
            return self._state.copy()

    def _save(self) -> None:
        """Save state to disk (must be called with lock held)."""
        self._state["last_run_start"] = utc_now_iso()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w") as f:
            json.dump(self._state, f, indent=2)
```

#### 1.4 Extract `lib/tasks.py`

This module handles task definition and parallel execution:

```python
#!/usr/bin/env python3
"""Task execution for GitHub watcher services."""

import json
import secrets
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jib_logging import get_logger

logger = get_logger("github-tasks")

MAX_PARALLEL_JIB = 20
HOST_NOTIFICATIONS_DIR = Path.home() / ".jib-sharing" / "notifications"


@dataclass
class JibTask:
    """A task to be executed by jib.

    Attributes:
        task_type: One of 'check_failure', 'comment', 'merge_conflict', 'review_request', 'pr_review_response'
        context: Task-specific context dict
        signature_key: Key for processed_* dict (e.g., 'processed_failures')
        signature_value: The signature to mark as processed
        is_readonly: If True, send notification instead of invoking jib
    """

    task_type: str
    context: dict
    signature_key: str
    signature_value: str
    is_readonly: bool = False


def invoke_jib(task_type: str, context: dict) -> bool:
    """Invoke jib container with context via jib --exec.

    Args:
        task_type: One of the supported task types
        context: Dict containing task-specific context

    Returns:
        True if invocation succeeded
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    workflow_id = f"gw-{task_type}-{timestamp}-{secrets.token_hex(4)}"

    context["workflow_id"] = workflow_id
    context["workflow_type"] = task_type
    context_json = json.dumps(context)

    processor_path = "/home/jwies/khan/james-in-a-box/jib-container/jib-tasks/github/github-processor.py"
    cmd = ["jib", "--exec", "python3", processor_path, "--task", task_type, "--context", context_json]

    logger.info("Invoking jib", task_type=task_type, repository=context.get("repository"), pr_number=context.get("pr_number"))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info("jib completed successfully", task_type=task_type)
            return True
        else:
            logger.error("jib failed", task_type=task_type, return_code=result.returncode, stderr=result.stderr[-2000:])
            return False
    except FileNotFoundError:
        logger.error("jib command not found")
        return False
    except Exception as e:
        logger.error("Error invoking jib", error=str(e))
        return False


def send_readonly_notification(task_type: str, context: dict) -> bool:
    """Send a Slack notification for a read-only repo event.

    Args:
        task_type: Type of task (comment, review_request, etc.)
        context: Task context dict

    Returns:
        True if notification was sent successfully
    """
    HOST_NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)

    repo = context.get("repository", "unknown")
    pr_number = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_id = f"readonly-{task_type}-{repo.replace('/', '-')}-{pr_number}-{timestamp}"

    # Build notification content based on task type
    title = f"{task_type.replace('_', ' ').title()} in {repo} PR #{pr_number}"
    body = f"**Repository**: {repo} _(read-only)_\n**PR**: [{pr_title}]({pr_url}) (#{pr_number})\n\n_This is a read-only repository._"

    file_content = f"""---
task_id: "{task_id}"
---

# {title}

{body}
"""

    filepath = HOST_NOTIFICATIONS_DIR / f"{timestamp}-{task_id}.md"

    try:
        filepath.write_text(file_content)
        logger.info("Read-only notification sent", task_type=task_type, repository=repo, pr_number=pr_number)
        return True
    except Exception as e:
        logger.error("Failed to write readonly notification", error=str(e))
        return False


def execute_task(task: JibTask, safe_state) -> bool:
    """Execute a single jib task and update state (thread-safe).

    Args:
        task: The JibTask to execute
        safe_state: ThreadSafeState instance

    Returns:
        True if task completed successfully
    """
    if task.is_readonly:
        if task.task_type == "review_request":
            task.context["is_readonly"] = True
            success = invoke_jib(task.task_type, task.context)
        else:
            success = send_readonly_notification(task.task_type, task.context)
    else:
        success = invoke_jib(task.task_type, task.context)

    if success:
        safe_state.mark_processed(task.signature_key, task.signature_value)
    else:
        safe_state.mark_failed(task.signature_value, task.task_type, task.context)
    return success


def execute_tasks_parallel(tasks: list[JibTask], safe_state) -> int:
    """Execute multiple jib tasks in parallel.

    Args:
        tasks: List of JibTask objects to execute
        safe_state: ThreadSafeState instance

    Returns:
        Number of successfully completed tasks
    """
    if not tasks:
        return 0

    completed = 0
    max_workers = min(MAX_PARALLEL_JIB, len(tasks))

    logger.info("Executing tasks in parallel", task_count=len(tasks), max_workers=max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {executor.submit(execute_task, task, safe_state): task for task in tasks}
        for future in as_completed(future_to_task):
            try:
                if future.result():
                    completed += 1
            except Exception as e:
                task = future_to_task[future]
                logger.error("Task execution failed", task_type=task.task_type, error=str(e))

    logger.info("Parallel execution completed", completed=completed, total=len(tasks))
    return completed
```

#### 1.5 Extract `lib/config.py`

This module handles configuration loading:

```python
#!/usr/bin/env python3
"""Configuration loading for GitHub watcher services."""

from pathlib import Path

import yaml

from jib_logging import get_logger

logger = get_logger("github-config")


def load_config() -> dict:
    """Load repository configuration.

    Returns:
        Config dict with writable_repos, readable_repos, github_username, bot_username
    """
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                config.setdefault("readable_repos", [])
                return config

    return {"writable_repos": [], "readable_repos": [], "github_username": "jib", "bot_username": "jib"}


def should_disable_auto_fix(repo: str) -> bool:
    """Check if auto-fix is disabled for a repo."""
    # Import here to avoid circular dependency
    from config.repo_config import should_disable_auto_fix as _should_disable_auto_fix
    return _should_disable_auto_fix(repo)


def should_restrict_to_configured_users(repo: str) -> bool:
    """Check if repo is restricted to configured users only."""
    from config.repo_config import should_restrict_to_configured_users as _should_restrict
    return _should_restrict(repo)
```

#### 1.6 Extract `lib/detection.py`

This module contains all PR analysis and detection logic:

```python
#!/usr/bin/env python3
"""Detection logic for GitHub events (comments, reviews, failures, conflicts)."""

from jib_logging import get_logger

from .github_api import gh_json, gh_text
from .config import should_disable_auto_fix, should_restrict_to_configured_users

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


def is_jib_engaged(pr_data: dict, bot_username: str, all_comments: list[dict] | None = None) -> bool:
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
        if req.get("__typename") == "User":
            if req.get("login", "").lower() in bot_variants:
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
        if request.get("__typename") == "User" and request.get("login", "").lower() == github_username.lower():
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
        ["pr", "view", str(pr_num), "--repo", repo, "--json", "number,title,body,url,headRefName,baseRefName,state"],
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
    import subprocess

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
        ["pr", "view", str(pr_num), "--repo", repo, "--json", "number,title,body,url,headRefName,baseRefName,mergeable,mergeStateStatus"],
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

    logger.info("Merge conflict detected", pr_number=pr_num, mergeable=mergeable, merge_state=merge_state)

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

    comments = gh_json(["pr", "view", str(pr_num), "--repo", repo, "--json", "comments,reviews"], repo=repo)
    if comments is None:
        return None

    all_comments = []

    # Issue comments
    for c in comments.get("comments", []):
        all_comments.append({
            "id": c.get("id", ""),
            "author": c.get("author", {}).get("login", "unknown"),
            "body": c.get("body", ""),
            "created_at": c.get("createdAt", ""),
            "type": "comment",
        })

    # Review body comments
    for r in comments.get("reviews", []):
        if r.get("body"):
            all_comments.append({
                "id": r.get("id", ""),
                "author": r.get("author", {}).get("login", "unknown"),
                "body": r.get("body", ""),
                "created_at": r.get("submittedAt", ""),
                "type": "review",
                "state": r.get("state", ""),
            })

    # Line-level review comments
    review_comments = gh_json(["api", f"repos/{repo}/pulls/{pr_num}/comments"], repo=repo)
    if review_comments:
        for rc in review_comments:
            all_comments.append({
                "id": str(rc.get("id", "")),
                "author": rc.get("user", {}).get("login", "unknown"),
                "body": rc.get("body", ""),
                "created_at": rc.get("created_at", ""),
                "type": "review_comment",
                "path": rc.get("path", ""),
                "line": rc.get("line"),
                "diff_hunk": rc.get("diff_hunk", ""),
            })

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
        info.get("task_type") == "comment" and info.get("repository") == repo and info.get("pr_number") == pr_num
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

    bot_variants = {bot_username.lower(), f"{bot_username.lower()}[bot]", f"app/{bot_username.lower()}"}
    other_reviews = [r for r in reviews if r.get("author", {}).get("login", "").lower() not in bot_variants]

    if not other_reviews:
        return None

    if should_restrict_to_configured_users(repo):
        allowed_users = {github_username.lower()}
        other_reviews = [r for r in other_reviews if r.get("author", {}).get("login", "").lower() in allowed_users]
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
                line_comments.append({
                    "id": str(rc.get("id", "")),
                    "author": rc.get("user", {}).get("login", "unknown"),
                    "body": rc.get("body", ""),
                    "path": rc.get("path", ""),
                    "line": rc.get("line"),
                    "original_line": rc.get("original_line"),
                    "diff_hunk": rc.get("diff_hunk", ""),
                    "created_at": rc.get("created_at", ""),
                })

    review_info = [{
        "id": r.get("id", ""),
        "author": r.get("author", {}).get("login", "unknown"),
        "state": r.get("state", "COMMENTED"),
        "body": r.get("body", ""),
        "submitted_at": r.get("submittedAt", ""),
    } for r in other_reviews]

    logger.info("Bot PR has reviews needing response", pr_number=pr_num, review_count=len(review_info))

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

    excluded_authors = {github_username.lower(), bot_username.lower(), f"{bot_username.lower()}[bot]"}
    other_prs = [p for p in all_prs if p.get("author", {}).get("login", "").lower() not in excluded_authors]

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
            p for p in other_prs
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

        results.append({
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
        })

    return results
```

---

### Phase 2: Create Comment Responder Service

#### 2.1 `comment-responder.py`

```python
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

from lib.config import load_config, should_disable_auto_fix
from lib.detection import check_pr_for_comments, check_pr_for_review_response, is_jib_engaged
from lib.github_api import check_gh_auth, gh_json
from lib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from lib.tasks import JibTask, execute_tasks_parallel

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
```

---

### Phase 3: Create PR Reviewer Service

#### 3.1 `pr-reviewer.py`

```python
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

from lib.config import load_config
from lib.detection import check_prs_for_review
from lib.github_api import check_gh_auth, gh_json
from lib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from lib.tasks import JibTask, execute_tasks_parallel

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
```

---

### Phase 4: Create CI/Conflict Fixer Service

#### 4.1 `ci-fixer.py`

```python
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

from lib.config import load_config, should_disable_auto_fix
from lib.detection import check_pr_for_failures, check_pr_for_merge_conflict
from lib.github_api import check_gh_auth, gh_json
from lib.state import ThreadSafeState, load_state, save_state, utc_now_iso
from lib.tasks import JibTask, execute_tasks_parallel

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
```

---

### Phase 5: Create Dispatcher

#### 5.1 `dispatcher.py`

```python
#!/usr/bin/env python3
"""
GitHub Watcher Dispatcher - Orchestrates all three services.

This dispatcher runs on a timer (via systemd) and sequentially executes:
1. CI/Conflict Fixer - Fix check failures and merge conflicts
2. Comment Responder - Respond to comments on PRs
3. PR Reviewer - Review PRs where jib is requested

Each service is imported and run directly (not as a subprocess) to share
configuration and state efficiently.

Usage:
    python3 dispatcher.py [--service SERVICE]

Options:
    --service SERVICE  Run only the specified service (comment-responder, pr-reviewer, ci-fixer)
                       If not specified, runs all three services.
"""

import argparse
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "shared"))
sys.path.insert(0, str(_project_root))

from jib_logging import get_logger

logger = get_logger("github-watcher-dispatcher")


def run_all_services() -> int:
    """Run all three services sequentially."""
    from lib.github_api import check_gh_auth
    from lib.state import utc_now_iso

    current_run_start = utc_now_iso()
    logger.info("GitHub Watcher Dispatcher starting", utc_time=current_run_start)

    if not check_gh_auth():
        logger.error("Exiting due to missing gh authentication")
        return 1

    exit_code = 0

    # Run CI/Conflict Fixer first (highest priority - unblock PRs)
    logger.info("Running CI/Conflict Fixer")
    try:
        from ci_fixer import main as ci_fixer_main
        result = ci_fixer_main()
        if result != 0:
            logger.warning("CI/Conflict Fixer returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("CI/Conflict Fixer failed", error=str(e))
        exit_code = 1

    # Run Comment Responder (respond to feedback)
    logger.info("Running Comment Responder")
    try:
        from comment_responder import main as comment_responder_main
        result = comment_responder_main()
        if result != 0:
            logger.warning("Comment Responder returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("Comment Responder failed", error=str(e))
        exit_code = 1

    # Run PR Reviewer (review PRs)
    logger.info("Running PR Reviewer")
    try:
        from pr_reviewer import main as pr_reviewer_main
        result = pr_reviewer_main()
        if result != 0:
            logger.warning("PR Reviewer returned non-zero", exit_code=result)
            exit_code = result
    except Exception as e:
        logger.error("PR Reviewer failed", error=str(e))
        exit_code = 1

    logger.info("GitHub Watcher Dispatcher completed", overall_exit_code=exit_code)
    return exit_code


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GitHub Watcher Dispatcher")
    parser.add_argument(
        "--service",
        choices=["comment-responder", "pr-reviewer", "ci-fixer"],
        help="Run only the specified service",
    )
    args = parser.parse_args()

    if args.service:
        # Run single service
        if args.service == "ci-fixer":
            from ci_fixer import main as service_main
        elif args.service == "comment-responder":
            from comment_responder import main as service_main
        elif args.service == "pr-reviewer":
            from pr_reviewer import main as service_main
        return service_main()
    else:
        # Run all services
        return run_all_services()


if __name__ == "__main__":
    sys.exit(main())
```

---

## File Structure After Refactor

```
host-services/analysis/github-watcher/
├── gwlib/
│   ├── __init__.py           # Package marker
│   ├── github_api.py         # gh CLI wrappers, rate limiting (~100 lines)
│   ├── state.py              # State management, ThreadSafeState (~100 lines)
│   ├── tasks.py              # JibTask, execute_task, execute_tasks_parallel (~150 lines)
│   ├── config.py             # Config loading, repo settings (~50 lines)
│   └── detection.py          # All PR detection logic (~400 lines)
├── comment_responder.py      # Service 1: Comment responses (~150 lines)
├── pr_reviewer.py            # Service 2: PR reviews (~120 lines)
├── ci_fixer.py               # Service 3: CI/conflict fixes (~130 lines)
├── dispatcher.py             # Optional: Run all three services sequentially
├── comment-responder.service # Systemd service for comment responder
├── comment-responder.timer   # Systemd timer for comment responder
├── pr-reviewer.service       # Systemd service for PR reviewer
├── pr-reviewer.timer         # Systemd timer for PR reviewer
├── ci-fixer.service          # Systemd service for CI fixer
├── ci-fixer.timer            # Systemd timer for CI fixer
├── github-watcher.service    # DEPRECATED - legacy unified service
├── github-watcher.timer      # DEPRECATED - legacy unified timer
└── README.md                 # Updated documentation
```

**Line count comparison:**
- **Before:** ~2300 lines in single file
- **After:** ~1200 lines across 9 focused files (48% reduction in total code due to shared utilities)

---

## Service Interaction Diagram

```
    ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
    │  ci-fixer.timer    │   │comment-responder   │   │ pr-reviewer.timer  │
    │  (every 5 min)     │   │     .timer         │   │  (every 5 min)     │
    └─────────┬──────────┘   │  (every 5 min)     │   └─────────┬──────────┘
              │              └─────────┬──────────┘             │
              ▼                        ▼                        ▼
    ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
    │  ci-fixer.service  │   │ comment-responder  │   │pr-reviewer.service │
    │                    │   │     .service       │   │                    │
    │  ci_fixer.py       │   │                    │   │  pr_reviewer.py    │
    │                    │   │comment_responder.py│   │                    │
    │ - check_failure    │   │ - comment          │   │ - review_request   │
    │ - merge_conflict   │   │ - pr_review_resp   │   │                    │
    └─────────┬──────────┘   └─────────┬──────────┘   └─────────┬──────────┘
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   gwlib/ (shared code)  │
                         │ - github_api.py         │
                         │ - state.py              │
                         │ - tasks.py              │
                         │ - detection.py          │
                         │ - config.py             │
                         └───────────┬─────────────┘
                                     │
                         ┌───────────┴───────────┐
                         │                       │
                         ▼                       ▼
                 ┌───────────────┐       ┌───────────────┐
                 │  jib --exec   │       │ Slack notify  │
                 │ (writable)    │       │ (readonly)    │
                 └───────────────┘       └───────────────┘
```

---

## Container-Side Changes

The existing `github-processor.py` in `jib-container/jib-tasks/github/` requires **no changes**. Each host-side service continues to invoke it with the appropriate task type and context.

The task types remain unchanged:
- `check_failure`
- `comment`
- `merge_conflict`
- `review_request`
- `pr_review_response`

---

## Testing Plan

### Unit Tests

Create `tests/test_github_watcher/`:

```python
# test_detection.py
def test_is_jib_engaged_as_author():
    """Test that is_jib_engaged returns True when bot is author."""
    pr_data = {"author": {"login": "james-in-a-box"}}
    assert is_jib_engaged(pr_data, "james-in-a-box") is True

def test_is_jib_engaged_as_assignee():
    """Test that is_jib_engaged returns True when bot is assigned."""
    pr_data = {"author": {"login": "someone"}, "assignees": [{"login": "james-in-a-box"}]}
    assert is_jib_engaged(pr_data, "james-in-a-box") is True

def test_is_jib_engaged_when_mentioned():
    """Test that is_jib_engaged returns True when bot is @mentioned."""
    pr_data = {"author": {"login": "someone"}, "assignees": []}
    comments = [{"body": "Hey @james-in-a-box can you look at this?"}]
    assert is_jib_engaged(pr_data, "james-in-a-box", comments) is True

def test_is_jib_engaged_not_engaged():
    """Test that is_jib_engaged returns False when bot is not engaged."""
    pr_data = {"author": {"login": "someone"}, "assignees": []}
    assert is_jib_engaged(pr_data, "james-in-a-box") is False
```

### Integration Tests

```python
# test_integration.py
def test_comment_responder_skips_unengaged_prs(mocker):
    """Test that comment responder only processes PRs where jib is engaged."""
    mocker.patch("lib.github_api.gh_json", return_value=[
        {"number": 1, "author": {"login": "someone"}, "assignees": []},  # Not engaged
        {"number": 2, "author": {"login": "james-in-a-box"}, "assignees": []},  # Engaged (author)
    ])

    tasks = collect_comment_tasks("owner/repo", {}, "jwbron", "james-in-a-box", None)

    # Should only have tasks for PR #2
    assert all(t.context["pr_number"] == 2 for t in tasks)

def test_pr_reviewer_requires_explicit_request(mocker):
    """Test that PR reviewer only reviews when explicitly requested."""
    mocker.patch("lib.github_api.gh_json", side_effect=[
        [{"number": 1, "author": {"login": "someone"}}],  # PR list
        {"reviewRequests": []},  # No review request for PR 1
    ])

    tasks = collect_review_tasks("owner/repo", {}, "jwbron", "james-in-a-box", None)

    assert len(tasks) == 0  # No tasks because not explicitly requested
```

### Manual Testing Checklist

- [ ] **CI Fixer**: Create a PR with failing tests, verify jib fixes it
- [ ] **Comment Responder**: Comment on a bot's PR, verify jib responds
- [ ] **Comment Responder**: @mention jib on any PR, verify jib responds
- [ ] **PR Reviewer**: Assign jib as reviewer, verify jib reviews
- [ ] **PR Reviewer**: Verify jib does NOT review unassigned PRs (behavior change)
- [ ] **Read-only repos**: Verify Slack notifications work correctly

### Canary Deployment

1. Deploy new services alongside old `github-watcher.py`
2. Run both for 24 hours, compare outputs
3. Verify no duplicate tasks or missed events
4. Switch over once verified

---

## Rollback Plan

If issues arise:

```bash
# 1. Disable new services (dispatcher)
systemctl --user stop github-watcher

# 2. Edit service file to point to old script
# github-watcher.service: ExecStart=... github-watcher.py (not dispatcher.py)

# 3. Re-enable
systemctl --user start github-watcher
```

The old `github-watcher.py` is preserved until new architecture is proven stable (minimum 2 weeks).

---

## Migration Checklist

- [ ] Phase 1: Extract shared code into `lib/`
- [ ] Phase 1: Update `github-watcher.py` to use `lib/` (verify no regression)
- [ ] Phase 2: Create `comment_responder.py`
- [ ] Phase 2: Test comment responder independently
- [ ] Phase 3: Create `pr_reviewer.py`
- [ ] Phase 3: Test PR reviewer independently
- [ ] Phase 4: Create `ci_fixer.py`
- [ ] Phase 4: Test CI fixer independently
- [ ] Phase 5: Create `dispatcher.py`
- [ ] Phase 5: Update systemd service to use dispatcher
- [ ] Testing: Run canary deployment
- [ ] Documentation: Update README.md
- [ ] Cleanup: Mark old `github-watcher.py` as deprecated

---

## Timeline Estimate

| Phase | Description | Time |
|-------|-------------|------|
| Phase 1 | Extract shared code | 2-3 hours |
| Phase 2 | Comment Responder | 2-3 hours |
| Phase 3 | PR Reviewer | 2-3 hours |
| Phase 4 | CI/Conflict Fixer | 1-2 hours |
| Phase 5 | Dispatcher | 1 hour |
| Testing | Unit + Integration + Manual | 3-4 hours |
| Documentation | README updates | 1 hour |

**Total:** ~12-17 hours of implementation work

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| PR Reviewer Scope | Opt-in (explicit request) | Less noise, more respectful, aligns with being a helpful assistant rather than an unsolicited reviewer |
| Tagged Definition | Both mention AND review request | Flexibility - users can @mention or use GitHub UI |
| Service Scheduling | Three separate services | Maximum flexibility, independent scheduling, isolated failure domains |
| State Management | Single file, namespaced keys | Simpler migration, atomic updates |
| Service Execution | Sequential in dispatcher | Avoids race conditions in state management |

---

## References

- Current implementation: `host-services/analysis/github-watcher/github-watcher.py`
- Container processor: `jib-container/jib-tasks/github/github-processor.py`
- Config: `config/repositories.yaml` and `config/repo_config.py`
- ADR: ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B: Scheduled Analysis with MCP"
