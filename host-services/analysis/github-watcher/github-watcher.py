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
from datetime import datetime
from pathlib import Path

import yaml


def load_config() -> dict:
    """Load repository configuration."""
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)

    return {"writable_repos": []}


def load_state() -> dict:
    """Load previous notification state to avoid duplicate processing."""
    state_file = Path.home() / ".local" / "share" / "github-watcher" / "state.json"
    if state_file.exists():
        try:
            with state_file.open() as f:
                return json.load(f)
        except Exception:
            pass
    return {"processed_failures": {}, "processed_comments": {}, "processed_reviews": {}}


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

    # Build command
    cmd = [
        "jib",
        "--exec",
        "python3",
        "/home/agent/khan/james-in-a-box/jib-container/jib-tasks/github/github-processor.py",
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
            print(f"  stderr: {result.stderr[:500]}")
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

    # Get check status
    checks = gh_json(
        [
            "pr",
            "checks",
            str(pr_num),
            "--repo",
            repo,
            "--json",
            "name,state,startedAt,completedAt,link,description,workflow",
        ]
    )

    if checks is None:
        return None

    # Find failed checks
    failed_checks = [c for c in checks if c.get("state", "").upper() in ("FAILURE", "FAILED")]

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


def check_pr_for_comments(repo: str, pr_data: dict, state: dict) -> dict | None:
    """Check a PR for new comments from others that need response.

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

    # Filter to comments from others (not @me/jib)
    # We'll let the container filter based on who authored the PR
    other_comments = [
        c
        for c in all_comments
        if c["author"].lower() not in ("jib", "github-actions[bot]", "dependabot[bot]")
    ]

    if not other_comments:
        return None

    # Create signature based on latest comment timestamp
    latest_comment = max(other_comments, key=lambda c: c.get("created_at", ""))
    comment_signature = f"{repo}-{pr_num}:{latest_comment['id']}"

    if comment_signature in state.get("processed_comments", {}):
        return None  # Already processed

    print(f"  PR #{pr_num}: {len(other_comments)} comment(s) from others")

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


def check_prs_for_review(repo: str, state: dict) -> list[dict]:
    """Check for PRs from others that need review.

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

    # Filter to PRs from others
    other_prs = [p for p in prs if p.get("author", {}).get("login", "").lower() not in ("jib",)]

    if not other_prs:
        return []

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


def main():
    """Main entry point - scan configured repos and trigger jib as needed."""
    print("=" * 60)
    print("GitHub Watcher - Host-side monitoring service")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Load config
    config = load_config()
    repos = config.get("writable_repos", [])

    if not repos:
        print("No repositories configured - check config/repositories.yaml")
        return 0

    # Load state
    state = load_state()

    print(f"Scanning {len(repos)} repository(ies)...")

    tasks_queued = 0

    for repo in repos:
        print(f"\n[{repo}]")

        # Get open PRs authored by @me (for check failures and comments)
        my_prs = gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--author",
                "@me",
                "--json",
                "number,title,url,headRefName,baseRefName",
            ]
        )

        if my_prs:
            print(f"  Found {len(my_prs)} open PR(s) authored by me")

            for pr in my_prs:
                # Check for failures
                failure_ctx = check_pr_for_failures(repo, pr, state)
                if failure_ctx and invoke_jib("check_failure", failure_ctx):
                    state.setdefault("processed_failures", {})[failure_ctx["failure_signature"]] = (
                        datetime.utcnow().isoformat()
                    )
                    tasks_queued += 1

                # Check for comments
                comment_ctx = check_pr_for_comments(repo, pr, state)
                if comment_ctx and invoke_jib("comment", comment_ctx):
                    state.setdefault("processed_comments", {})[comment_ctx["comment_signature"]] = (
                        datetime.utcnow().isoformat()
                    )
                    tasks_queued += 1
        else:
            print("  No open PRs authored by me")

        # Check for PRs from others that need review
        review_contexts = check_prs_for_review(repo, state)
        for review_ctx in review_contexts:
            if invoke_jib("review_request", review_ctx):
                state.setdefault("processed_reviews", {})[review_ctx["review_signature"]] = (
                    datetime.utcnow().isoformat()
                )
                tasks_queued += 1

    # Save state
    save_state(state)

    print("\n" + "=" * 60)
    print(f"GitHub Watcher completed - {tasks_queued} task(s) triggered")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
