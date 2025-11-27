#!/usr/bin/env python3
"""
GitHub Watcher - Host-side service that monitors GitHub and triggers jib container analysis.

This service runs on the host (NOT in the container) and:
1. Queries GitHub directly via gh CLI for PR/issue status
2. Detects check failures, new comments, and review requests
3. Triggers jib container via `jib --exec github-processor.py --context <json>`

The container should ONLY be called via `jib --exec`. No watching/polling logic lives in the container.

Per ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B: Scheduled Analysis with MCP"
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


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
                state.setdefault("last_run", None)
                return state
        except Exception:
            pass
    return {
        "processed_failures": {},
        "processed_comments": {},
        "processed_reviews": {},
        "last_run": None,
    }


def save_state(state: dict):
    """Save notification state."""
    state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open("w") as f:
        json.dump(state, f, indent=2)


def gh_json(args: list[str]) -> dict | list | None:
    """Run gh CLI command and return JSON output."""
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
        print(f"  gh command failed: {' '.join(args)}")
        print(f"  stderr: {e.stderr}")
        return None
    except json.JSONDecodeError:
        return None
    except subprocess.TimeoutExpired:
        print(f"  gh command timed out: {' '.join(args)}")
        return None


def gh_text(args: list[str]) -> str | None:
    """Run gh CLI command and return text output."""
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
        print(f"  gh command failed: {' '.join(args)}")
        print(f"  stderr: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"  gh command timed out: {' '.join(args)}")
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

    print(f"  Invoking jib: {task_type} for {context.get('repository', 'unknown')}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,  # 10 minute timeout for complex analysis
        )

        if result.returncode == 0:
            print("  jib completed successfully")
            return True
        else:
            print(f"  jib failed with code {result.returncode}")
            # Show last 2000 chars of stderr to capture actual error (not just Docker build progress)
            stderr_tail = result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr
            if stderr_tail:
                print(f"  stderr (last 2000 chars): {stderr_tail}")
            # Also show stdout if there's useful output
            if result.stdout:
                stdout_tail = result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout
                print(f"  stdout (last 1000 chars): {stdout_tail}")
            return False

    except subprocess.TimeoutExpired:
        print("  jib timed out after 10 minutes")
        return False
    except FileNotFoundError:
        print("  jib command not found - is it in PATH?")
        return False
    except Exception as e:
        print(f"  Error invoking jib: {e}")
        return False


def check_pr_for_failures(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for check failures.

    Returns context dict if failures found and not already processed.
    """
    pr_num = pr_data["number"]
    head_sha = pr_data.get("headRefOid")

    if not head_sha:
        print(f"  PR #{pr_num}: No head SHA available, skipping check status")
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
        return None

    # Create signature to detect if we've already processed this exact failure set
    failed_names = sorted([c["name"] for c in failed_checks])
    failure_signature = f"{repo}-{pr_num}:" + ",".join(failed_names)

    if failure_signature in state.get("processed_failures", {}):
        return None  # Already processed

    print(f"  PR #{pr_num}: {len(failed_checks)} check(s) failing")

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
            print(f"    Log fetch timed out for {check['name']}")
        except Exception as e:
            print(f"    Error fetching logs: {e}")

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
        return None

    # Filter by since_timestamp if provided (only show comments newer than last run)
    if since_timestamp:
        other_comments = [c for c in other_comments if c.get("created_at", "") > since_timestamp]
        if not other_comments:
            return None  # No new comments since last run

    # Create signature based on latest comment timestamp
    latest_comment = max(other_comments, key=lambda c: c.get("created_at", ""))
    comment_signature = f"{repo}-{pr_num}:{latest_comment['id']}"

    if comment_signature in state.get("processed_comments", {}):
        return None  # Already processed

    print(f"  PR #{pr_num}: {len(other_comments)} new comment(s) from others")

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


def check_prs_for_review(
    repo: str, state: dict, bot_username: str, since_timestamp: str | None = None
) -> list[dict]:
    """Check for PRs from others that need review.

    Args:
        repo: Repository in owner/repo format
        state: State dict with processed_reviews
        bot_username: Bot's username (to filter out bot's own PRs)
        since_timestamp: ISO timestamp to filter PRs (only show newer)

    Returns list of context dicts for PRs needing review.
    """
    # Get open PRs NOT authored by @me
    prs = gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--json",
            "number,title,url,headRefName,baseRefName,author,createdAt,additions,deletions,files",
        ]
    )

    if prs is None:
        return []

    # Filter to PRs from others (not from the bot)
    excluded_authors = {
        bot_username.lower(),
    }

    other_prs = [
        p for p in prs if p.get("author", {}).get("login", "").lower() not in excluded_authors
    ]

    if not other_prs:
        return []

    # Filter by since_timestamp if provided (only show PRs created after last run)
    if since_timestamp:
        other_prs = [p for p in other_prs if p.get("createdAt", "") > since_timestamp]
        if not other_prs:
            return []  # No new PRs since last run

    results = []
    for pr in other_prs:
        pr_num = pr["number"]
        review_signature = f"{repo}-{pr_num}:review"

        # Check if already reviewed
        if review_signature in state.get("processed_reviews", {}):
            continue

        print(
            f"  PR #{pr_num}: New PR from {pr.get('author', {}).get('login', 'unknown')} needs review"
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
    """Get ISO timestamp for 'since' queries based on last run time.

    Returns None if this is the first run or last_run is not set.
    """
    last_run = state.get("last_run")
    if last_run:
        return last_run
    return None


def main():
    """Main entry point - scan configured repos and trigger jib as needed."""
    current_run_time = utc_now_iso()

    print("=" * 60)
    print("GitHub Watcher - Host-side monitoring service")
    print(f"Local time: {datetime.now().isoformat()}")
    print(f"UTC time:   {current_run_time}")
    print("=" * 60)

    # Load config
    config = load_config()
    repos = config.get("writable_repos", [])
    github_username = config.get("github_username", "jib")
    bot_username = config.get("bot_username", "jib")

    if not repos:
        print("No repositories configured - check config/repositories.yaml")
        return 0

    print(f"GitHub username: {github_username}")
    print(f"Bot username: {bot_username}")

    # Load state
    state = load_state()

    # Get the timestamp from last run for filtering queries
    since_timestamp = get_since_timestamp(state)
    if since_timestamp:
        print(f"Checking for events since last run: {since_timestamp}")
    else:
        print("First run - checking all open items")

    print(f"Scanning {len(repos)} repository(ies)...")

    tasks_queued = 0

    for repo in repos:
        print(f"\n[{repo}]")

        # Get open PRs authored by configured user (for check failures and comments)
        my_prs = gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--author",
                github_username,
                "--json",
                "number,title,url,headRefName,baseRefName,headRefOid",
            ]
        )

        if my_prs:
            print(f"  Found {len(my_prs)} open PR(s) authored by {github_username}")

            for pr in my_prs:
                # Check for failures
                failure_ctx = check_pr_for_failures(repo, pr, state)
                if failure_ctx and invoke_jib("check_failure", failure_ctx):
                    state.setdefault("processed_failures", {})[failure_ctx["failure_signature"]] = (
                        utc_now_iso()
                    )
                    tasks_queued += 1

                # Check for comments (filter out bot's own comments, not human's)
                comment_ctx = check_pr_for_comments(
                    repo, pr, state, bot_username, since_timestamp
                )
                if comment_ctx and invoke_jib("comment", comment_ctx):
                    state.setdefault("processed_comments", {})[comment_ctx["comment_signature"]] = (
                        utc_now_iso()
                    )
                    tasks_queued += 1
        else:
            print(f"  No open PRs authored by {github_username}")

        # Also check PRs authored by the bot (for check failures and comments)
        # The bot creates PRs via GitHub App, so its PRs need monitoring too
        bot_author = f"{bot_username}[bot]"
        bot_prs = gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--author",
                f"app/{bot_username}",
                "--json",
                "number,title,url,headRefName,baseRefName,headRefOid",
            ]
        )

        if bot_prs:
            print(f"  Found {len(bot_prs)} open PR(s) authored by {bot_author}")

            for pr in bot_prs:
                # Check for failures on bot's PRs
                failure_ctx = check_pr_for_failures(repo, pr, state)
                if failure_ctx and invoke_jib("check_failure", failure_ctx):
                    state.setdefault("processed_failures", {})[failure_ctx["failure_signature"]] = (
                        utc_now_iso()
                    )
                    tasks_queued += 1

                # Check for comments on bot's PRs (filter out bot's own comments)
                comment_ctx = check_pr_for_comments(
                    repo, pr, state, bot_username, since_timestamp
                )
                if comment_ctx and invoke_jib("comment", comment_ctx):
                    state.setdefault("processed_comments", {})[comment_ctx["comment_signature"]] = (
                        utc_now_iso()
                    )
                    tasks_queued += 1

        # Check for PRs from others that need review (filter out bot's PRs)
        review_contexts = check_prs_for_review(repo, state, bot_username, since_timestamp)
        for review_ctx in review_contexts:
            if invoke_jib("review_request", review_ctx):
                state.setdefault("processed_reviews", {})[review_ctx["review_signature"]] = (
                    utc_now_iso()
                )
                tasks_queued += 1

    # Update last run timestamp and save state
    state["last_run"] = current_run_time
    save_state(state)

    print("\n" + "=" * 60)
    print(f"GitHub Watcher completed - {tasks_queued} task(s) triggered")
    print(f"Next run will check for events since: {current_run_time}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
