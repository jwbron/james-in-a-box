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
    - merge_conflict: PR has merge conflicts -> resolves conflicts with base branch

Per ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B":
    - Host-side watcher queries GitHub and triggers container
    - Container performs analysis and takes action via GitHub CLI/MCP
    - No watching/polling logic lives in the container
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


# Import shared Claude runner
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from claude import run_claude


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

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for analysis...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, timeout=900, cwd=cwd)

    if result.success:
        print("Claude analysis completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


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

    prompt += f"""## CRITICAL: Branch Verification and Setup (MUST DO FIRST)

**Target PR Branch**: `{pr_branch}`
**Base Branch**: `{base_branch}`

Before making ANY changes, you MUST:

### Step 1: Checkout PR branch
```bash
cd ~/khan/{repo_name}
git fetch origin {pr_branch} {base_branch}
git checkout {pr_branch}
git branch --show-current  # VERIFY this shows: {pr_branch}
```

**WARNING**: Your container starts on a temporary branch (jib-temp-*), NOT the PR branch!
If you commit without checking out `{pr_branch}` first, your changes will go to the WRONG branch
and may contaminate other PRs. This has caused issues before.

### Step 2: Pull in latest {base_branch} (IMPORTANT)
The failures may be due to the PR branch being out of sync with {base_branch}. Merge it in:
```bash
git merge origin/{base_branch} --no-edit
```

If there are merge conflicts:
- Resolve them first (see files with `git diff --name-only --diff-filter=U`)
- Complete the merge before proceeding

### Step 3: Run checks locally BEFORE attempting fixes
This helps identify whether failures are:
- Real issues in the PR code (need fixing)
- Flaky tests (may pass on retry)
- Issues introduced by merging {base_branch} (need careful resolution)

```bash
make lint   # Check lint status
make test   # Run tests
```

Review the output carefully. Note which failures match the CI logs vs new/different failures.

## Your Task

1. **CHECKOUT PR BRANCH FIRST** (see above) - do NOT skip this step
2. **Verify branch**: Run `git branch --show-current` and confirm it shows `{pr_branch}`
3. **Merge {base_branch}**: Pull in latest changes from {base_branch}
4. **Run checks locally**: Execute lint and test commands to reproduce failures
5. **Analyze** the failures - compare local output with CI logs
6. **Fix** - implement fixes on the PR branch:
   - For lint errors: Try `make fix` or `make lint-fix` first (auto-fix)
   - For test failures: Examine and fix tests
   - For build errors: Check dependencies, imports
7. **Verify fixes** - Run `make lint` and `make test` again to confirm fixes work
8. **Verify branch again**: Run `git branch --show-current` - confirm still on `{pr_branch}`
9. **Commit** - Commit fixes with clear message
10. **Push** - Push to the PR branch: `git push origin {pr_branch}`
11. **Comment** - Add PR comment explaining fixes

Begin by checking out the PR branch now.
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

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for response generation...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, timeout=600, cwd=cwd)

    if result.success:
        print("Claude response generation completed")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_comment_prompt(context: dict) -> str:
    """Build the prompt for Claude to respond to comments."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    comments = context.get("comments", [])

    repo_name = repo.split("/")[-1]

    prompt = f"""# PR Comment Response

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}
- **PR Branch**: {pr_branch}

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

    prompt += f"""## CRITICAL: Branch Verification (IF MAKING CODE CHANGES)

If you need to make code changes in response to comments, you MUST checkout the correct branch first:

**Target PR Branch**: `{pr_branch}`

```bash
cd ~/khan/{repo_name}
git fetch origin {pr_branch}
git checkout {pr_branch}
git branch --show-current  # VERIFY this shows: {pr_branch}
```

**WARNING**: Your container starts on a temporary branch (jib-temp-*), NOT the PR branch!
If you commit without checking out `{pr_branch}` first, your changes will go to the WRONG branch.

## Your Task

Review the comments above and:

1. **Understand** what the commenter is asking or suggesting
2. **Research** - read relevant code if needed to understand context
3. **IF implementing changes**:
   a. FIRST checkout the PR branch: `git checkout {pr_branch}`
   b. Verify with: `git branch --show-current`
   c. Make changes
   d. Verify branch again before committing
   e. Commit and push to `{pr_branch}`
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

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for code review...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, timeout=900, cwd=cwd)

    if result.success:
        print("Claude code review completed")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


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


def handle_merge_conflict(context: dict):
    """Handle PR merge conflicts by invoking Claude to resolve them.

    Context expected:
        - repository: str (e.g., "jwbron/james-in-a-box")
        - pr_number: int
        - pr_title: str
        - pr_url: str
        - pr_branch: str
        - base_branch: str
        - pr_body: str
    """
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")

    print(f"Handling merge conflict for PR #{pr_num} in {repo}")
    print(f"  Branch: {pr_branch} has conflicts with {base_branch}")

    # Build prompt for Claude
    prompt = build_merge_conflict_prompt(context)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin
    print("Invoking Claude for conflict resolution...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, timeout=900, cwd=cwd)

    if result.success:
        print("Claude conflict resolution completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_merge_conflict_prompt(context: dict) -> str:
    """Build the prompt for Claude to resolve merge conflicts."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    pr_body = context.get("pr_body", "")

    repo_name = repo.split("/")[-1]

    prompt = f"""# GitHub PR Merge Conflict Resolution

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}
- **Branch**: {pr_branch} -> {base_branch}

## PR Description
{pr_body[:2000] if pr_body else "No description provided"}

## Problem

This PR has **merge conflicts** with the `{base_branch}` branch. GitHub cannot automatically merge it.

## CRITICAL: Steps to Resolve

You MUST follow these steps exactly:

### Step 1: Checkout the PR branch
```bash
cd ~/khan/{repo_name}
git fetch origin {pr_branch} {base_branch}
git checkout {pr_branch}
git branch --show-current  # VERIFY: must show {pr_branch}
```

### Step 2: Merge the base branch to surface conflicts
```bash
git merge origin/{base_branch}
```

This will show which files have conflicts.

### Step 3: Identify conflicting files
```bash
git diff --name-only --diff-filter=U
```

### Step 4: Resolve each conflict
For each conflicting file:
1. Open the file and look for conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
2. Understand what both sides changed
3. Decide the correct resolution:
   - Keep PR changes if they're the right approach
   - Keep base changes if they should take precedence
   - Combine both if needed
4. Remove ALL conflict markers
5. Ensure the code is syntactically correct

### Step 5: Stage and verify
```bash
git add <resolved_files>
git diff --cached  # Review what you're committing
```

### Step 6: Complete the merge
```bash
git commit -m "Merge {base_branch} into {pr_branch} and resolve conflicts

Resolved merge conflicts to integrate latest {base_branch} changes."
```

### Step 7: Push the resolution
```bash
git push origin {pr_branch}
```

### Step 8: Comment on the PR
Use `gh pr comment {pr_num} --repo {repo}` to explain:
- What conflicts were found
- How you resolved them
- Any decisions you made

Sign with: "— Authored by jib"

## Important Notes

- **Preserve PR intent**: The PR changes should still work as intended after resolution
- **Don't lose changes**: Make sure no important code is accidentally removed
- **Test after**: If possible, run tests to verify the resolution is correct
- **Be conservative**: When in doubt, keep both changes and adjust

Begin conflict resolution now.
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
        choices=["check_failure", "comment", "review_request", "merge_conflict"],
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
        "merge_conflict": handle_merge_conflict,
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
