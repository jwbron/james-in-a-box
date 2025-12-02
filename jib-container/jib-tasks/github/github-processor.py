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
    - pr_review_response: Reviews on bot's own PRs -> addresses feedback and iterates

Per ADR-Context-Sync-Strategy-Custom-vs-MCP Section 4 "Option B":
    - Host-side watcher queries GitHub and triggers container
    - Container performs analysis and takes action via GitHub CLI/MCP
    - No watching/polling logic lives in the container
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# Import shared modules
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from beads import PRContextManager
from claude import run_claude
from jib_logging import ContextScope


# Global PR context manager for beads integration
pr_context_manager = PRContextManager()


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
    pr_title = context.get("pr_title", f"PR #{pr_num}")
    failed_checks = context.get("failed_checks", [])

    print(f"Handling check failure for PR #{pr_num} in {repo}")
    print(f"  Failed checks: {[c.get('name', 'unknown') for c in failed_checks]}")

    # Get or create beads task for this PR (persistent context across sessions)
    beads_id = pr_context_manager.get_or_create_context(
        repo, pr_num, pr_title, task_type="github-pr"
    )
    if beads_id:
        print(f"  Beads task: {beads_id}")
        # Update beads to track this check failure handling
        check_names = [c.get("name", "unknown") for c in failed_checks]
        pr_context_manager.update_context(
            beads_id,
            f"Handling check failures: {', '.join(check_names)}",
            status="in_progress",
        )

    # Build prompt for Claude (includes beads context if available)
    prompt = build_check_failure_prompt(context, beads_id)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for analysis...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, cwd=cwd)

    if result.success:
        print("Claude analysis completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_check_failure_prompt(context: dict, beads_id: str | None = None) -> str:
    """Build the prompt for Claude to analyze check failures."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    pr_body = context.get("pr_body", "")
    failed_checks = context.get("failed_checks", [])

    # Get beads context summary if available
    beads_context = ""
    if beads_id:
        beads_context = pr_context_manager.get_context_summary(repo, pr_num)

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

{beads_context}

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
11. **Update PR description** - Update the PR description to document the fixes:
    ```python
    # First, get the current PR to retrieve the existing body
    # Use MCP: mcp__github__pull_request_read(owner="{repo.split("/")[0]}", repo="{repo.split("/")[-1]}", pullNumber={pr_num}, method="get")
    # Then update with the fixes documented:
    # Use MCP: mcp__github__update_pull_request(
    #     owner="{repo.split("/")[0]}",
    #     repo="{repo.split("/")[-1]}",
    #     pullNumber={pr_num},
    #     body="<existing body>\\n\\n## Updates\\n- Fixed: <list what was fixed>"
    # )
    ```
12. **Comment** - Add PR comment explaining fixes. Use the signature helper to add workflow context:
    ```python
    try:
        from jib_logging.signatures import add_signature_to_comment
        comment_with_sig = add_signature_to_comment("Your comment text here")
    except Exception:
        # Fallback to unsigned comment if signature helper fails
        comment_with_sig = "Your comment text here"
    # Then post to GitHub with comment_with_sig
    ```
    The try/except ensures that signature failures don't block the primary task.
13. **Update beads** - Update the beads task with what you did{f" (task: {beads_id})" if beads_id else ""}

**IMPORTANT**: All PR comments you post should include the workflow signature (automatically added by the helper).

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
    pr_title = context.get("pr_title", f"PR #{pr_num}")
    comments = context.get("comments", [])

    print(f"Handling {len(comments)} comment(s) for PR #{pr_num} in {repo}")

    # Get or create beads task for this PR (persistent context across sessions)
    beads_id = pr_context_manager.get_or_create_context(
        repo, pr_num, pr_title, task_type="github-pr"
    )
    if beads_id:
        print(f"  Beads task: {beads_id}")
        # Update beads to track this comment handling
        comment_authors = list({c.get("author", "unknown") for c in comments})
        pr_context_manager.update_context(
            beads_id,
            f"Handling comments from: {', '.join(comment_authors)}",
            status="in_progress",
        )

    # Build prompt for Claude (includes beads context if available)
    prompt = build_comment_prompt(context, beads_id)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for response generation...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, cwd=cwd)

    if result.success:
        print("Claude response generation completed")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_comment_prompt(context: dict, beads_id: str | None = None) -> str:
    """Build the prompt for Claude to respond to comments."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    comments = context.get("comments", [])

    # Get beads context summary if available
    beads_context = ""
    if beads_id:
        beads_context = pr_context_manager.get_context_summary(repo, pr_num)

    # Extract owner and repo name for use in f-strings
    repo_parts = repo.split("/")
    owner = repo_parts[0] if len(repo_parts) > 1 else context.get("owner", "OWNER")
    repo_name = repo_parts[-1]

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

{beads_context}

## Your Task

Review the comments above and respond appropriately:

### Step 1: Understand the Comments

**Check comment types:**
- **Inline review comments** - Comments on specific lines of code
- **General PR comments** - Overall feedback or questions
- **Suggested changes** - GitHub suggestion blocks that can be committed

### Step 2: Handle Suggested Changes (If Any)

If a comment contains a GitHub suggestion (```suggestion blocks), you can commit it directly using the GitHub MCP:

```python
# Use MCP: mcp__github__pull_request_read(owner="{owner}", repo="{repo_name}", pullNumber={pr_num}, method="get_review_comments")
# This will show you all review comments including suggestions
```

To commit a suggestion:
1. First, checkout the PR branch (see "Branch Verification" above)
2. Apply the suggested change manually by editing the file
3. Commit with a message like: "Apply suggestion from @username"
4. Push to the PR branch

**Alternative using GitHub UI:**
You can also tell the user to commit the suggestion via the GitHub web interface (click "Commit suggestion" button).

### Step 3: Respond to Inline Comments

For inline review comments, you can respond directly to the comment thread using GitHub CLI:

```bash
# Reply to a specific review comment by its ID
gh pr comment {pr_num} --body "Your response here — Authored by jib"
```

Or add a general PR comment:
```bash
gh pr comment {pr_num} --body "Overall response to feedback — Authored by jib"
```

### Step 4: Implement Requested Changes

If the comments request code changes:

**a. FIRST checkout the PR branch:**
```bash
cd ~/khan/{repo_name}
git fetch origin {pr_branch}
git checkout {pr_branch}
git branch --show-current  # VERIFY this shows: {pr_branch}
```

**b. Make the requested changes:**
- Read the code to understand context
- Implement the changes thoughtfully
- Follow project conventions
- Test your changes if possible

**c. Commit with clear message:**
```bash
git add <changed_files>
git commit -m "Address review feedback: <brief description>

- Detail 1
- Detail 2

Addresses: <comment/issue reference>"
git branch --show-current  # VERIFY still on {pr_branch}
git push origin {pr_branch}
```

**d. Update the PR description:**
If changes were significant, update the PR description to document what was addressed:
```python
# First, get the current PR body:
# Use MCP: mcp__github__pull_request_read(owner="{owner}", repo="{repo_name}", pullNumber={pr_num}, method="get")
# Then update with a new "Updates" section:
# Use MCP: mcp__github__update_pull_request(
#     owner="{owner}",
#     repo="{repo_name}",
#     pullNumber={pr_num},
#     body="<existing body>\\n\\n## Updates\\n- Addressed review feedback: <summary>"
# )
```

**e. Comment on the PR to explain what you did:**
```bash
gh pr comment {pr_num} --body "I've addressed the review feedback:
- Fixed issue X in file Y
- Refactored Z as suggested

Committed as [commit SHA]. — Authored by jib"
```

### Step 5: Update Beads

Update the beads task with what you did{f" (task: {beads_id})" if beads_id else ""}

### Important Notes

- **For suggestions**: Either commit them directly or ask the user to
- **For inline questions**: Respond directly in the comment thread
- **For change requests**: Implement, commit, push, and comment
- **Always acknowledge**: Let the commenter know you've seen and processed their feedback

Begin analysis now.
"""

    return prompt


def check_existing_review(repo: str, pr_num: int, bot_username: str = "james-in-a-box") -> bool:
    """Check if a review from the bot already exists on this PR.

    Returns True if a review already exists (should skip), False otherwise.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_num), "--repo", repo, "--json", "reviews"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        reviews_data = json.loads(result.stdout)
        reviews = reviews_data.get("reviews", [])

        # Check if any review is from the bot
        bot_variants = {
            bot_username.lower(),
            f"{bot_username.lower()}[bot]",
            f"app/{bot_username.lower()}",
        }

        for review in reviews:
            author = review.get("author", {}).get("login", "").lower()
            if author in bot_variants:
                return True

        return False
    except Exception as e:
        print(f"  Warning: Could not check for existing reviews: {e}")
        # On error, proceed with review to avoid missing PRs
        return False


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
    pr_title = context.get("pr_title", f"PR #{pr_num}")
    author = context.get("author", "unknown")

    print(f"Handling review request for PR #{pr_num} by @{author} in {repo}")

    # Idempotency check: skip if we've already reviewed this PR
    if check_existing_review(repo, pr_num):
        print(f"  PR #{pr_num} already has a review from jib, skipping duplicate review")
        return

    # Get or create beads task for this PR (persistent context across sessions)
    beads_id = pr_context_manager.get_or_create_context(
        repo, pr_num, pr_title, task_type="github-pr"
    )
    if beads_id:
        print(f"  Beads task: {beads_id}")
        pr_context_manager.update_context(
            beads_id,
            f"Performing code review for PR by @{author}",
            status="in_progress",
        )

    # Build prompt for Claude (includes beads context if available)
    prompt = build_review_prompt(context, beads_id)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    print("Invoking Claude for code review...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, cwd=cwd)

    if result.success:
        print("Claude code review completed")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_review_prompt(context: dict, beads_id: str | None = None) -> str:
    """Build the prompt for Claude to review a PR."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")

    # Get beads context summary if available
    beads_context = ""
    if beads_id:
        beads_context = pr_context_manager.get_context_summary(repo, pr_num)
    base_branch = context.get("base_branch", "main")
    author = context.get("author", "unknown")
    additions = context.get("additions", 0)
    deletions = context.get("deletions", 0)
    files = context.get("files", [])
    diff = context.get("diff", "")

    # Extract owner and repo name for use in f-strings
    repo_parts = repo.split("/")
    owner = repo_parts[0] if len(repo_parts) > 1 else context.get("owner", "OWNER")
    repo_name = repo_parts[-1]

    prompt = rf"""# PR Code Review

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

{beads_context}

## Your Task

Review this PR and provide constructive feedback using **inline comments with suggested fixes**:

### Step 1: Create a Pending Review

Use the GitHub MCP tool to create a pending review:
```python
# Use MCP: mcp__github__pull_request_review_write(method="create", owner="{owner}", repo="{repo_name}", pullNumber={pr_num})
```

### Step 2: Add Inline Comments with Suggested Fixes

For each issue you find, add inline comments using the GitHub MCP tool:

```python
# Use MCP: mcp__github__add_comment_to_pending_review(
#     owner="{owner}",
#     repo="{repo_name}",
#     pullNumber={pr_num},
#     path="path/to/file.py",
#     body="Comment with suggested fix",
#     line=42,
#     side="RIGHT",
#     subjectType="LINE"
# )
```

**Important parameters:**
- `path`: Relative path to the file (from repo root)
- `line`: The line number in the diff where the comment applies
- `side`: "RIGHT" for new code, "LEFT" for old code
- `subjectType`: "LINE" for single-line comments, "FILE" for file-level comments
- `body`: Your comment - use markdown to include suggested fixes

**Suggested fix format:**
When suggesting code changes, use this format in the `body`:
```markdown
Consider refactoring this for better readability:

\`\`\`suggestion
def improved_function():
    # Your suggested code here
    pass
\`\`\`
```

The `suggestion` code fence will render as a suggested change that can be committed directly from GitHub.

### Step 3: Submit the Review

After adding all inline comments, submit the review:
```python
# Use MCP: mcp__github__pull_request_review_write(
#     method="submit_pending",
#     owner="{owner}",
#     repo="{repo_name}",
#     pullNumber={pr_num},
#     body="Overall review summary here. — Reviewed by jib",
#     event="COMMENT"  # or "APPROVE" or "REQUEST_CHANGES"
# )
```

**Review event types:**
- `COMMENT`: General feedback without approval/rejection
- `APPROVE`: Approve the PR
- `REQUEST_CHANGES`: Request changes before merging

### Step 4: What to Review

**Check for:**
1. **Code quality and style** - Does it follow project conventions?
2. **Potential bugs or edge cases** - Are there scenarios not handled?
3. **Security concerns** - Any vulnerabilities (XSS, SQL injection, etc.)?
4. **Test coverage** - Are changes adequately tested?
5. **Documentation** - Are comments and docs updated?

**Be constructive:**
- Use inline comments for specific issues
- Provide suggested fixes when possible
- Acknowledge good patterns you see
- Be specific about what needs to change and why

### Step 5: Update Beads

Update the beads task with your review summary{f" (task: {beads_id})" if beads_id else ""}

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
    pr_title = context.get("pr_title", f"PR #{pr_num}")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")

    print(f"Handling merge conflict for PR #{pr_num} in {repo}")
    print(f"  Branch: {pr_branch} has conflicts with {base_branch}")

    # Get or create beads task for this PR (persistent context across sessions)
    beads_id = pr_context_manager.get_or_create_context(
        repo, pr_num, pr_title, task_type="github-pr"
    )
    if beads_id:
        print(f"  Beads task: {beads_id}")
        pr_context_manager.update_context(
            beads_id,
            f"Handling merge conflict: {pr_branch} vs {base_branch}",
            status="in_progress",
        )

    # Build prompt for Claude (includes beads context if available)
    prompt = build_merge_conflict_prompt(context, beads_id)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin
    print("Invoking Claude for conflict resolution...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, cwd=cwd)

    if result.success:
        print("Claude conflict resolution completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_merge_conflict_prompt(context: dict, beads_id: str | None = None) -> str:
    """Build the prompt for Claude to resolve merge conflicts."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    pr_body = context.get("pr_body", "")

    # Get beads context summary if available
    beads_context = ""
    if beads_id:
        beads_context = pr_context_manager.get_context_summary(repo, pr_num)

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

### Step 8: Update the PR description
Update the PR description to document the merge conflict resolution:
```python
# First, get the current PR body:
# Use MCP: mcp__github__pull_request_read(owner="{repo.split("/")[0]}", repo="{repo.split("/")[-1]}", pullNumber={pr_num}, method="get")
# Then update with conflict resolution details:
# Use MCP: mcp__github__update_pull_request(
#     owner="{repo.split("/")[0]}",
#     repo="{repo.split("/")[-1]}",
#     pullNumber={pr_num},
#     body="<existing body>\\n\\n## Updates\\n- Resolved merge conflicts with {base_branch}: <summary of resolution>"
# )
```

### Step 9: Comment on the PR
Use `gh pr comment {pr_num} --repo {repo}` to explain:
- What conflicts were found
- How you resolved them
- Any decisions you made

Sign with: "— Authored by jib"

### Step 10: Update beads
Update the beads task with what you did{f" (task: {beads_id})" if beads_id else ""}

{beads_context}

## Important Notes

- **Preserve PR intent**: The PR changes should still work as intended after resolution
- **Don't lose changes**: Make sure no important code is accidentally removed
- **Test after**: If possible, run tests to verify the resolution is correct
- **Be conservative**: When in doubt, keep both changes and adjust

Begin conflict resolution now.
"""

    return prompt


# Maximum iterations for PR review response cycle
# This prevents infinite loops if approval never comes
MAX_REVIEW_ITERATIONS = 5


def is_full_approval(reviews: list[dict]) -> bool:
    """Determine if the PR has received a full approval without caveats.

    A full approval is:
    - At least one APPROVED review
    - No CHANGES_REQUESTED reviews after the approval
    - The approval comment doesn't contain caveats like "LGTM but...", "Approved with..."

    Args:
        reviews: List of review dicts with 'state', 'body', 'submitted_at'

    Returns:
        True if there's a clean approval, False otherwise
    """
    if not reviews:
        return False

    # Sort by submitted_at to get chronological order
    sorted_reviews = sorted(reviews, key=lambda r: r.get("submitted_at", ""))

    # Check most recent review first
    latest_review = sorted_reviews[-1] if sorted_reviews else None
    if not latest_review:
        return False

    state = latest_review.get("state", "").upper()
    body = latest_review.get("body", "").lower()

    # Must be an APPROVED state
    if state != "APPROVED":
        return False

    # Check for caveats in the approval message
    caveat_phrases = [
        "but",
        "however",
        "though",
        "although",
        "except",
        "with the caveat",
        "one thing",
        "minor",
        "nitpick",
        "nit:",
        "suggestion:",
        "consider",
        "might want to",
        "could you",
        "would be nice",
        "future improvement",
        "follow-up",
        "followup",
        "todo",
        "fix later",
    ]

    for phrase in caveat_phrases:
        if phrase in body:
            return False

    # Check if there are any unaddressed CHANGES_REQUESTED reviews after the approval
    # This handles the case where someone approves but another reviewer requests changes
    for review in sorted_reviews:
        submitted = review.get("submitted_at", "")
        if submitted > latest_review.get("submitted_at", "") and review.get("state", "").upper() == "CHANGES_REQUESTED":
            return False

    return True


def get_review_iteration_count(beads_context: dict | None) -> int:
    """Extract the current iteration count from beads context.

    Args:
        beads_context: Dict with 'content' from beads task

    Returns:
        Current iteration count (0 if not found)
    """
    if not beads_context or not beads_context.get("content"):
        return 0

    content = beads_context.get("content", "")

    # Look for iteration marker in notes
    # Format: "Review iteration: N"
    match = re.search(r"Review iteration:\s*(\d+)", content)
    if match:
        return int(match.group(1))

    # Count occurrences of "Responding to review" as fallback
    return content.lower().count("responding to review")


def handle_pr_review_response(context: dict):
    """Handle PR review response by invoking Claude to address review feedback.

    This function processes reviews on the bot's own PRs and:
    1. Analyzes review feedback (approved, changes requested, comments)
    2. Addresses requested changes by implementing fixes
    3. Responds to review comments
    4. Tracks iteration count to prevent infinite loops
    5. Stops when full approval is received or max iterations reached

    Context expected:
        - repository: str (e.g., "jwbron/james-in-a-box")
        - pr_number: int
        - pr_title: str
        - pr_url: str
        - pr_branch: str
        - base_branch: str
        - reviews: list[dict] with id, author, state, body, submitted_at
        - line_comments: list[dict] with id, author, body, path, line, diff_hunk
        - diff: str
    """
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", f"PR #{pr_num}")
    reviews = context.get("reviews", [])

    print(f"Handling review response for PR #{pr_num} in {repo}")
    print(f"  Reviews: {len(reviews)}")
    print(f"  Line comments: {len(context.get('line_comments', []))}")

    # Get or create beads task for this PR (persistent context across sessions)
    beads_id = pr_context_manager.get_or_create_context(
        repo, pr_num, pr_title, task_type="github-pr"
    )

    beads_context = None
    if beads_id:
        print(f"  Beads task: {beads_id}")
        beads_context = pr_context_manager.get_context(repo, pr_num)

    # Check iteration count
    iteration_count = get_review_iteration_count(beads_context)
    print(f"  Current iteration: {iteration_count + 1}/{MAX_REVIEW_ITERATIONS}")

    # Check if we've reached max iterations
    if iteration_count >= MAX_REVIEW_ITERATIONS:
        print(f"  Max iterations ({MAX_REVIEW_ITERATIONS}) reached. Stopping review response cycle.")
        if beads_id:
            pr_context_manager.update_context(
                beads_id,
                f"Review iteration: {iteration_count + 1} (MAX REACHED)\n"
                f"Stopping automatic review response. Human intervention may be needed.",
                status="blocked",
            )
        # Create notification about max iterations
        create_notification(
            f"PR #{pr_num} Review Cycle Limit Reached",
            f"**Repository**: {repo}\n"
            f"**PR**: #{pr_num} - {pr_title}\n\n"
            f"The automatic review response cycle has reached the maximum of {MAX_REVIEW_ITERATIONS} iterations.\n\n"
            f"Human intervention may be needed to complete the review process.\n"
        )
        return

    # Check if we have a clean approval
    if is_full_approval(reviews):
        print("  Full approval received! No further action needed.")
        if beads_id:
            reviewer = reviews[-1].get("author", "Unknown") if reviews else "Unknown"
            pr_context_manager.update_context(
                beads_id,
                f"Review iteration: {iteration_count + 1}\n"
                f"Full approval received from @{reviewer}. PR ready to merge!",
                status="closed",
            )
        return

    # Update beads to track this review response
    if beads_id:
        reviewer_states = [f"@{r.get('author', 'unknown')}: {r.get('state', 'COMMENTED')}" for r in reviews]
        pr_context_manager.update_context(
            beads_id,
            f"Review iteration: {iteration_count + 1}\n"
            f"Responding to review feedback: {', '.join(reviewer_states)}",
            status="in_progress",
        )

    # Build prompt for Claude (includes beads context if available)
    prompt = build_pr_review_response_prompt(context, beads_id, iteration_count + 1)

    # Get repo path for working directory
    repo_name = repo.split("/")[-1]
    repo_path = Path.home() / "khan" / repo_name

    # Run Claude Code via stdin
    print("Invoking Claude for review response...")
    cwd = repo_path if repo_path.exists() else Path.home() / "khan"
    result = run_claude(prompt, cwd=cwd)

    if result.success:
        print("Claude review response completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}...")
    else:
        print(f"{result.error}")
        if result.stderr:
            print(f"Error: {result.stderr[:500]}")


def build_pr_review_response_prompt(context: dict, beads_id: str | None = None, iteration: int = 1) -> str:
    """Build the prompt for Claude to respond to PR review feedback."""
    repo = context.get("repository", "unknown")
    pr_num = context.get("pr_number", 0)
    pr_title = context.get("pr_title", "")
    pr_url = context.get("pr_url", "")
    pr_branch = context.get("pr_branch", "")
    base_branch = context.get("base_branch", "main")
    reviews = context.get("reviews", [])
    line_comments = context.get("line_comments", [])
    diff = context.get("diff", "")

    # Get beads context summary if available
    beads_context = ""
    if beads_id:
        beads_context = pr_context_manager.get_context_summary(repo, pr_num)

    repo_parts = repo.split("/")
    owner = repo_parts[0] if len(repo_parts) > 1 else context.get("owner", "OWNER")
    repo_name = repo_parts[-1]

    # Format reviews
    reviews_text = ""
    for r in reviews:
        reviewer = r.get("author", "unknown")
        state = r.get("state", "COMMENTED")
        body = r.get("body", "")
        submitted = r.get("submitted_at", "")
        reviews_text += f"\n### @{reviewer} - {state}\n*{submitted}*\n\n{body}\n"

    # Format line comments
    line_comments_text = ""
    for c in line_comments:
        author = c.get("author", "unknown")
        path = c.get("path", "unknown")
        line = c.get("line", "?")
        body = c.get("body", "")
        diff_hunk = c.get("diff_hunk", "")
        line_comments_text += f"\n### @{author} on `{path}:{line}`\n"
        if diff_hunk:
            line_comments_text += f"```diff\n{diff_hunk[-500:]}\n```\n"
        line_comments_text += f"\n{body}\n"

    prompt = f"""# PR Review Response

You are jib, an AI software engineering agent. Someone has reviewed your PR and you need to respond to their feedback.

## PR Information
- **Repository**: {repo}
- **PR Number**: #{pr_num}
- **Title**: {pr_title}
- **URL**: {pr_url}
- **Branch**: {pr_branch} -> {base_branch}
- **Review Iteration**: {iteration} of {MAX_REVIEW_ITERATIONS}

## Reviews Received
{reviews_text if reviews_text else "No review body comments."}

## Inline Comments
{line_comments_text if line_comments_text else "No inline comments."}

## Current Diff
```diff
{diff[:20000] if diff else "Diff not available"}
{"...(truncated)" if diff and len(diff) > 20000 else ""}
```

{beads_context}

## CRITICAL: Branch Verification (MUST DO FIRST)

Before making ANY changes, you MUST checkout the correct branch:

**Target PR Branch**: `{pr_branch}`

```bash
cd ~/khan/{repo_name}
git fetch origin {pr_branch} {base_branch}
git checkout {pr_branch}
git pull origin {pr_branch}
git branch --show-current  # VERIFY: must show {pr_branch}
```

**WARNING**: Your container starts on a temporary branch (jib-temp-*), NOT the PR branch!

## Your Task

Respond to the review feedback:

### Step 1: Analyze the Feedback

**Check review states:**
- **APPROVED**: Acknowledge and thank the reviewer
- **CHANGES_REQUESTED**: Must address all requested changes before merging
- **COMMENTED**: Respond to questions/suggestions as appropriate

**Check if this is a clean approval:**
- If APPROVED with no caveats ("LGTM", "Looks great", etc.) → Thank reviewer, no code changes needed
- If APPROVED with caveats ("LGTM but...", "Minor suggestion...") → Address the suggestions

### Step 2: Address Requested Changes (if any)

For each CHANGES_REQUESTED review or inline comment requesting changes:

1. **Read the relevant code** to understand the context
2. **Implement the requested changes** thoughtfully
3. **Verify branch**: `git branch --show-current` should show `{pr_branch}`
4. **Commit with clear message**:
   ```bash
   git add <changed_files>
   git commit -m "Address review feedback: <brief description>

   - Change 1
   - Change 2

   Review iteration: {iteration}"
   ```
5. **Push to PR branch**: `git push origin {pr_branch}`

### Step 3: Respond to Inline Comments

Reply to each inline comment that requires a response:

```bash
gh pr comment {pr_num} --repo {repo} --body "Response to @reviewer's feedback...

— Authored by jib"
```

For comments on specific lines, you can reply in the review thread.

### Step 4: Update PR Description (if significant changes)

If you made substantial changes, update the PR description:
```python
# Use MCP: mcp__github__update_pull_request(
#     owner="{owner}",
#     repo="{repo_name}",
#     pullNumber={pr_num},
#     body="<existing body>\\n\\n## Updates (Iteration {iteration})\\n- Addressed review feedback: <summary>"
# )
```

### Step 5: Update Beads

Update the beads task with what you did{f" (task: {beads_id})" if beads_id else ""}:
```bash
cd ~/beads
bd --allow-stale update {beads_id if beads_id else "<task_id>"} --notes "Review iteration: {iteration}
Addressed feedback from: <reviewers>
Changes made: <summary>
Status: <pending next review / ready for approval>"
```

## Important Guidelines

- **Be thorough**: Address ALL requested changes before pushing
- **Be responsive**: Reply to each comment, even if just acknowledging
- **Be professional**: Thank reviewers for their time and feedback
- **Don't over-iterate**: If you've addressed all feedback, say so and wait for re-review
- **Know when to stop**: If the same feedback keeps coming, ask for clarification

## Iteration Limit

This is iteration {iteration} of {MAX_REVIEW_ITERATIONS}. If you reach the maximum without approval:
- The automatic response cycle will stop
- A notification will be sent for human intervention
- Focus on quality over speed

Begin by checking out the PR branch now.
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
        choices=["check_failure", "comment", "review_request", "merge_conflict", "pr_review_response"],
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

    # Extract workflow context from incoming context
    workflow_id = context.get("workflow_id")
    workflow_type = context.get("workflow_type", args.task)
    repository = context.get("repository")
    pr_number = context.get("pr_number")

    # Establish logging context for the entire workflow execution
    # This propagates to all logs, notifications, and signatures
    with ContextScope(
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        repository=repository,
        pr_number=pr_number,
    ):
        if workflow_id:
            print(f"Workflow ID: {workflow_id}")

        # Dispatch to appropriate handler
        handlers = {
            "check_failure": handle_check_failure,
            "comment": handle_comment,
            "review_request": handle_review_request,
            "merge_conflict": handle_merge_conflict,
            "pr_review_response": handle_pr_review_response,
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
