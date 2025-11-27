#!/usr/bin/env python3
"""
GitHub Processor - Container-side dispatcher for GitHub-related tasks.

This script is invoked by the host-side github-watcher.py via `jib --exec`.
It receives context via command-line arguments and dispatches to the
appropriate handler based on task type.

Usage:
    jib --exec python3 github-processor.py --task <task_type> --context <json>

Task types:
    - check_failure: PR check failures -> analyzes and fixes CI issues
    - comment: New PR comments -> generates appropriate responses
    - review_request: New PR needing review -> performs code review

Per ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B":
    - Host-side watcher queries GitHub and triggers container
    - Container performs analysis and takes action via GitHub CLI/MCP
    - No watching/polling logic lives in the container
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def create_notification(title: str, body: str):
    """Create a notification file for Slack delivery."""
    notifications_dir = Path.home() / "sharing" / "notifications"
    notifications_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_title = title.replace(" ", "-").replace("#", "").replace(":", "")[:50]
    notif_file = notifications_dir / f"{timestamp}-{safe_title}.md"

    with notif_file.open("w") as f:
        f.write(f"# {title}\n\n")
        f.write(body)

    print(f"Created notification: {notif_file.name}")


def handle_check_failure(context: dict):
    """Handle PR check failures by invoking Claude for analysis and fixes.

    Context expected:
        - repository: str (e.g., "jwbron/james-in-a-box")
        - pr_number: int
        - pr_title: str
        - pr_url: str
        - pr_branch: str
        - base_branch: str
        - pr_body: str
        - failed_checks: list[dict] with name, state, full_log, etc.
    """
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    failed_checks = context.get("failed_checks", [])

    print(f"Handling check failure for PR #{pr_num} in {repo}")
    print(f"  Failed checks: {[c.get('name', 'unknown') for c in failed_checks]}")

    # Build prompt for Claude
    prompt = build_check_failure_prompt(context)

    # Invoke Claude
    print("Invoking Claude for analysis...")
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            check=False,
            capture_output=False,
            text=True,
            timeout=900,  # 15 minute timeout
        )

        if result.returncode == 0:
            print("Claude analysis completed successfully")
        else:
            print(f"Claude exited with code {result.returncode}")

    except subprocess.TimeoutExpired:
        print("Claude analysis timed out after 15 minutes")
    except FileNotFoundError:
        print("Claude CLI not found - is it installed?")
    except Exception as e:
        print(f"Error invoking Claude: {e}")


def build_check_failure_prompt(context: dict) -> str:
    """Build the prompt for Claude to analyze check failures."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    pr_body = context.get("pr_body", "")
    failed_checks = context.get("failed_checks", [])

    # Detect make targets for the repository
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name
    make_targets = detect_make_targets(repo_path) if repo_path.exists() else {}

    prompt = f"""# GitHub PR Check Failure Analysis

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}
- **Branch**: {pr_branch} -> {base_branch}

## PR Description
{pr_body[:2000] if pr_body else "No description provided"}

## Failed Checks ({len(failed_checks)})

"""

    for check in failed_checks:
        check_name = check.get("name", "Unknown")
        check_state = check.get("state", "FAILURE")
        full_log = check.get("full_log", "")

        prompt += f"""### {check_name}
**State**: {check_state}

"""
        if full_log:
            # Include log excerpts
            if len(full_log) > 4000:
                prompt += f"""**Log Excerpt (first 2000 chars)**:
```
{full_log[:2000]}
```

**Log Excerpt (last 2000 chars)**:
```
{full_log[-2000:]}
```

"""
            else:
                prompt += f"""**Full Log**:
```
{full_log}
```

"""
        else:
            prompt += "*No log available*\n\n"

    # Add make targets info if available
    if make_targets.get("all"):
        prompt += """## Available Make Targets

**IMPORTANT**: Use these make targets to fix issues. Many lint errors can be auto-fixed!

"""
        if make_targets.get("fix"):
            prompt += "**Auto-fix targets** (run these first!):\n"
            for t in make_targets["fix"]:
                prompt += f"- `make {t}`\n"
        if make_targets.get("lint"):
            prompt += "**Lint targets**:\n"
            for t in make_targets["lint"]:
                if t not in make_targets.get("fix", []):
                    prompt += f"- `make {t}`\n"
        if make_targets.get("test"):
            prompt += "**Test targets**:\n"
            for t in make_targets["test"]:
                prompt += f"- `make {t}`\n"
        prompt += "\n"

    prompt += """## Your Task

1. **Analyze** the failures - understand root cause from logs
2. **Fix** - checkout the PR branch and implement fixes:
   - For lint errors: Try `make fix` or `make lint-fix` first (auto-fix)
   - For test failures: Examine and fix tests
   - For build errors: Check dependencies, imports
3. **Verify** - Run `make lint` and `make test` to verify fixes
4. **Commit** - Commit fixes with clear message
5. **Push** - Push to the PR branch
6. **Comment** - Add PR comment explaining fixes

Begin analysis now.
"""

    return prompt


def detect_make_targets(repo_path: Path) -> dict[str, list[str]]:
    """Detect available make targets from Makefile."""
    makefile = repo_path / "Makefile"
    if not makefile.exists():
        return {}

    targets = {"lint": [], "test": [], "fix": [], "all": []}
    try:
        content = makefile.read_text()
        for line in content.split("\n"):
            # Match target definitions like "target:" or "target: deps"
            is_valid = (
                line
                and not line.startswith("\t")
                and not line.startswith("#")
                and ":" in line
                and not line.startswith(".")
            )
            if is_valid:
                target = line.split(":")[0].strip()
                if target and not target.startswith("$"):
                    targets["all"].append(target)
                    if "lint" in target.lower():
                        targets["lint"].append(target)
                    if "test" in target.lower():
                        targets["test"].append(target)
                    if "fix" in target.lower():
                        targets["fix"].append(target)
    except Exception:
        pass
    return targets


def handle_comment(context: dict):
    """Handle new PR comments by invoking Claude for response.

    Context expected:
        - repository: str
        - pr_number: int
        - pr_title: str
        - pr_url: str
        - pr_branch: str
        - comments: list[dict] with id, author, body, created_at, type
    """
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    comments = context.get("comments", [])

    print(f"Handling {len(comments)} comment(s) for PR #{pr_num} in {repo}")

    # Build prompt for Claude
    prompt = build_comment_prompt(context)

    # Invoke Claude
    print("Invoking Claude for response generation...")
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            check=False,
            capture_output=False,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode == 0:
            print("Claude response generation completed")
        else:
            print(f"Claude exited with code {result.returncode}")

    except subprocess.TimeoutExpired:
        print("Claude response generation timed out")
    except FileNotFoundError:
        print("Claude CLI not found")
    except Exception as e:
        print(f"Error invoking Claude: {e}")


def build_comment_prompt(context: dict) -> str:
    """Build the prompt for Claude to respond to comments."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    comments = context.get("comments", [])

    prompt = f"""# PR Comment Response

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}

## Comments to Respond To

"""

    for comment in comments:
        author = comment.get("author", "unknown")
        body = comment.get("body", "")
        comment_type = comment.get("type", "comment")
        created_at = comment.get("created_at", "")
        state = comment.get("state", "")

        prompt += f"""### From @{author} ({comment_type}{" - " + state if state else ""})
*{created_at}*

{body}

---

"""

    prompt += """## Your Task

Review the comments above and:

1. **Understand** what the commenter is asking or suggesting
2. **Research** - read relevant code if needed to understand context
3. **Implement** any requested changes if appropriate
4. **Respond** - use `gh pr comment` to respond thoughtfully:
   - Acknowledge their feedback
   - Explain what you've done or will do
   - Ask clarifying questions if needed

Sign your response with: "— Authored by jib"

Begin analysis now.
"""

    return prompt


def handle_review_request(context: dict):
    """Handle new PR review request by invoking Claude for code review.

    Context expected:
        - repository: str
        - pr_number: int
        - pr_title: str
        - pr_url: str
        - pr_branch: str
        - base_branch: str
        - author: str
        - additions: int
        - deletions: int
        - files: list[str]
        - diff: str
    """
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    author = context.get("author", "unknown")

    print(f"Handling review request for PR #{pr_num} by @{author} in {repo}")

    # Build prompt for Claude
    prompt = build_review_prompt(context)

    # Invoke Claude
    print("Invoking Claude for code review...")
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            check=False,
            capture_output=False,
            text=True,
            timeout=900,  # 15 minute timeout
        )

        if result.returncode == 0:
            print("Claude code review completed")
        else:
            print(f"Claude exited with code {result.returncode}")

    except subprocess.TimeoutExpired:
        print("Claude review timed out")
    except FileNotFoundError:
        print("Claude CLI not found")
    except Exception as e:
        print(f"Error invoking Claude: {e}")


def build_review_prompt(context: dict) -> str:
    """Build the prompt for Claude to review a PR."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    author = context.get("author", "unknown")
    additions = context.get("additions", 0)
    deletions = context.get("deletions", 0)
    files = context.get("files", [])
    diff = context.get("diff", "")

    prompt = f"""# PR Code Review

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}
- **Author**: @{author}
- **Branch**: {pr_branch} -> {base_branch}
- **Changes**: +{additions} / -{deletions}

## Files Changed ({len(files)})
{chr(10).join("- " + f for f in files[:20])}
{"..." if len(files) > 20 else ""}

## Diff
```diff
{diff[:30000] if diff else "Diff not available"}
{"...(truncated)" if diff and len(diff) > 30000 else ""}
```

## Your Task

Review this PR and provide constructive feedback:

1. **Understand** the purpose of the changes
2. **Check** for:
   - Code quality and style
   - Potential bugs or edge cases
   - Security concerns
   - Test coverage
   - Documentation
3. **Comment** using `gh pr review` with your assessment:
   - Be constructive and specific
   - Suggest improvements where appropriate
   - Acknowledge good patterns you see

Sign your review with: "— Reviewed by jib"

Begin review now.
"""

    return prompt


def main():
    """Main entry point - parse arguments and dispatch to handler."""
    parser = argparse.ArgumentParser(
        description="GitHub Processor - Container-side task dispatcher"
    )
    parser.add_argument(
        "--task",
        required=True,
        choices=["check_failure", "comment", "review_request"],
        help="Type of task to process",
    )
    parser.add_argument(
        "--context",
        required=True,
        help="JSON context for the task",
    )

    args = parser.parse_args()

    # Parse context
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON context: {e}")
        sys.exit(1)

    print("=" * 60)
    print(f"GitHub Processor - {args.task}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Dispatch to appropriate handler
    handlers = {
        "check_failure": handle_check_failure,
        "comment": handle_comment,
        "review_request": handle_review_request,
    }

    handler = handlers.get(args.task)
    if handler:
        handler(context)
    else:
        print(f"Unknown task type: {args.task}")
        sys.exit(1)

    print("=" * 60)
    print("GitHub Processor - Completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
