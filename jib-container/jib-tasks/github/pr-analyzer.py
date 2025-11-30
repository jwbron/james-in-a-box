#!/usr/bin/env python3
"""
PR Analyzer - Container-side processor for GitHub PR analysis

Analyzes PR context fetched by the host-side analyze-pr script and uses
Claude to suggest or implement fixes.

Usage (called by jib --exec):
    python3 pr-analyzer.py <context-file.json> [--fix] [--interactive]

This script:
1. Reads the PR context JSON
2. Formats it into a comprehensive prompt
3. Runs Claude to analyze the PR
4. Optionally implements fixes if --fix is passed
5. Creates notification with results
"""

import json
import subprocess
import sys
from pathlib import Path


# Import shared Claude runner
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from claude import run_claude


def load_context(context_file: Path) -> dict:
    """Load PR context from JSON file."""
    with open(context_file) as f:
        return json.load(f)


def format_pr_summary(ctx: dict) -> str:
    """Format PR metadata as a summary."""
    pr = ctx.get("pr", {})
    return f"""## PR Summary

**Title:** {pr.get("title", "N/A")}
**Author:** {pr.get("author", {}).get("login", "N/A")}
**State:** {pr.get("state", "N/A")}
**Review Decision:** {pr.get("reviewDecision", "PENDING")}
**Draft:** {pr.get("isDraft", False)}
**Mergeable:** {pr.get("mergeable", "N/A")}

**Base:** `{pr.get("baseRefName", "N/A")}` <- **Head:** `{pr.get("headRefName", "N/A")}`

**Changes:** +{pr.get("additions", 0)} / -{pr.get("deletions", 0)} across {pr.get("changedFiles", 0)} files

**Created:** {pr.get("createdAt", "N/A")}
**Updated:** {pr.get("updatedAt", "N/A")}

### Description

{pr.get("body", "*No description provided*")}
"""


def format_files_changed(ctx: dict) -> str:
    """Format list of changed files."""
    files = ctx.get("files", [])
    if not files:
        return "## Files Changed\n\n*No files data available*"

    lines = ["## Files Changed\n"]
    for f in files:
        path = f.get("path", "unknown")
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        lines.append(f"- `{path}` (+{additions} / -{deletions})")

    return "\n".join(lines)


def format_checks(ctx: dict) -> str:
    """Format CI check status."""
    checks = ctx.get("checks", [])
    if not checks:
        return "## CI Checks\n\n*No checks data available*"

    lines = ["## CI Checks\n"]

    # Group by status
    # Note: gh pr checks uses 'state' (e.g., 'FAILURE', 'SUCCESS') not 'conclusion'
    failed = [c for c in checks if c.get("state", "").upper() in ("FAILURE", "FAILED")]
    pending = [
        c for c in checks if c.get("state", "").upper() in ("PENDING", "IN_PROGRESS", "QUEUED")
    ]
    passed = [c for c in checks if c.get("state", "").upper() == "SUCCESS"]
    [c for c in checks if c not in failed and c not in pending and c not in passed]

    if failed:
        lines.append("### Failed")
        for c in failed:
            lines.append(f"- **{c.get('name')}** - {c.get('state')}")
            if c.get("link"):
                lines.append(f"  - Details: {c.get('link')}")

    if pending:
        lines.append("\n### In Progress")
        for c in pending:
            lines.append(f"- {c.get('name')} - {c.get('state')}")

    if passed:
        lines.append(f"\n### Passed ({len(passed)} checks)")
        # Just list names, don't clutter
        names = [c.get("name") for c in passed]
        lines.append(f"  {', '.join(names[:10])}" + ("..." if len(names) > 10 else ""))

    return "\n".join(lines)


def format_failed_logs(ctx: dict) -> str:
    """Format logs from failed checks."""
    logs = ctx.get("failed_check_logs", {})
    if not logs:
        return ""

    lines = ["## Failed Check Logs\n"]
    for check_name, log_content in logs.items():
        lines.append(f"### {check_name}\n")
        lines.append("```")
        # Truncate individual logs if needed
        if len(log_content) > 15000:
            lines.append(log_content[:15000])
            lines.append(f"\n... (truncated, {len(log_content)} total chars)")
        else:
            lines.append(log_content)
        lines.append("```\n")

    return "\n".join(lines)


def format_comments(ctx: dict) -> str:
    """Format PR comments."""
    comments = ctx.get("comments", [])
    if not comments:
        return "## Comments\n\n*No comments*"

    lines = ["## Comments\n"]
    for c in comments:
        author = c.get("author", {}).get("login", "unknown")
        created = c.get("createdAt", "")
        body = c.get("body", "")
        lines.append(f"**{author}** ({created}):")
        lines.append(f"> {body[:500]}{'...' if len(body) > 500 else ''}\n")

    return "\n".join(lines)


def format_reviews(ctx: dict) -> str:
    """Format PR reviews."""
    reviews = ctx.get("reviews", [])
    if not reviews:
        return "## Reviews\n\n*No reviews*"

    lines = ["## Reviews\n"]
    for r in reviews:
        author = r.get("author", {}).get("login", "unknown")
        state = r.get("state", "UNKNOWN")
        body = r.get("body", "")
        lines.append(f"**{author}**: {state}")
        if body:
            lines.append(f"> {body[:500]}{'...' if len(body) > 500 else ''}")
        lines.append("")

    return "\n".join(lines)


def format_review_comments(ctx: dict) -> str:
    """Format inline code review comments."""
    review_comments = ctx.get("review_comments", [])
    if not review_comments:
        return ""

    lines = ["## Inline Review Comments\n"]
    for c in review_comments:
        path = c.get("path", "unknown")
        line = c.get("line") or c.get("original_line", "?")
        author = c.get("user", {}).get("login", "unknown")
        body = c.get("body", "")
        lines.append(f"**{path}:{line}** - {author}:")
        lines.append(f"> {body[:500]}{'...' if len(body) > 500 else ''}\n")

    return "\n".join(lines)


def format_commits(ctx: dict) -> str:
    """Format PR commits."""
    commits = ctx.get("commits", [])
    if not commits:
        return "## Commits\n\n*No commit data*"

    lines = ["## Commits\n"]
    for c in commits:
        oid = c.get("oid", "")[:8]
        msg = c.get("messageHeadline", "No message")
        lines.append(f"- `{oid}` {msg}")

    return "\n".join(lines)


def format_diff(ctx: dict, max_length: int = 30000) -> str:
    """Format the PR diff."""
    diff = ctx.get("diff", "")
    if not diff:
        return "## Diff\n\n*No diff available*"

    lines = ["## Diff\n", "```diff"]
    if len(diff) > max_length:
        lines.append(diff[:max_length])
        lines.append(f"\n... (truncated, {len(diff)} total chars)")
    else:
        lines.append(diff)
    lines.append("```")

    return "\n".join(lines)


def build_analysis_prompt(ctx: dict, fix_mode: bool = False) -> str:
    """Build the full analysis prompt for Claude."""
    owner = ctx.get("owner", "unknown")
    repo = ctx.get("repo", "unknown")
    pr_number = ctx.get("pr_number", "?")
    pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}"

    # Build context sections
    sections = [
        f"# PR Analysis: {owner}/{repo}#{pr_number}",
        f"**URL:** {pr_url}\n",
        format_pr_summary(ctx),
        format_files_changed(ctx),
        format_checks(ctx),
        format_failed_logs(ctx),
        format_reviews(ctx),
        format_review_comments(ctx),
        format_comments(ctx),
        format_commits(ctx),
        format_diff(ctx),
    ]

    context_text = "\n\n".join(sections)

    # Build instructions
    if fix_mode:
        instructions = f"""
---

# Your Task: Analyze and Fix

You are analyzing PR {owner}/{repo}#{pr_number}. Your goal is to:

1. **Understand the PR**: What is it trying to accomplish?
2. **Identify problems**: Look at failing CI, review feedback, and potential issues
3. **Implement fixes**: If you have access to the repo, make the necessary changes

## Action Steps

1. First, explain your analysis:
   - What the PR is trying to do
   - What's blocking it (failing checks, review feedback, etc.)
   - What needs to be fixed

2. If the repo `{repo}` exists in `~/workspace/`:
   - Check out the PR branch: `gh pr checkout {pr_number} --repo {owner}/{repo}`
   - Make the necessary fixes
   - Commit with clear messages
   - Push to update the PR

3. If you can't access the repo, provide:
   - Detailed description of what needs to be fixed
   - Code snippets showing the fix
   - Commands the user should run

4. Create a notification at `~/sharing/notifications/` with:
   - Summary of what you found
   - What you fixed (if applicable)
   - What still needs attention
   - Next steps for the user

## Important

- Be specific about errors - quote the exact error messages
- If there are multiple issues, prioritize by importance
- Don't make unnecessary changes beyond fixing the immediate issues
- Always explain your reasoning
"""
    else:
        instructions = f"""
---

# Your Task: Analyze and Suggest

You are analyzing PR {owner}/{repo}#{pr_number}. Your goal is to:

1. **Understand the PR**: What is it trying to accomplish?
2. **Identify any issues**: CI failures, review feedback, code problems
3. **Suggest fixes**: Provide clear, actionable recommendations

## Output Format

Provide your analysis in this structure:

### Summary
Brief description of what the PR does and its current state.

### Issues Found
For each issue:
- **Issue**: Clear description
- **Location**: File/line if applicable
- **Suggested Fix**: Specific solution
- **Priority**: High/Medium/Low

### Failing CI (if applicable)
For each failing check:
- What's failing
- Why it's failing (based on logs)
- How to fix it

### Review Feedback (if applicable)
Summarize what reviewers are asking for and how to address it.

### Recommended Next Steps
Ordered list of actions to get this PR merged.

---

Create a notification at `~/sharing/notifications/` summarizing your findings.
The notification should be concise and actionable.
"""

    return context_text + instructions


def analyze_with_claude(prompt: str, interactive: bool = False) -> bool:
    """Run Claude with the analysis prompt."""
    cwd = Path.home() / "khan"

    if interactive:
        # Interactive mode - show output in real-time
        result = run_claude(prompt, cwd=cwd, capture_output=False)
        return result.success
    else:
        # Non-interactive - capture output
        result = run_claude(prompt, cwd=cwd)

        if result.success:
            print("=" * 60)
            print("ANALYSIS RESULTS")
            print("=" * 60)
            print(result.stdout)
            return True
        else:
            print(f"{result.error}", file=sys.stderr)
            if result.stderr:
                print(f"stderr: {result.stderr}", file=sys.stderr)
            return False


def stop_background_services():
    """Stop services that would keep the container alive."""
    subprocess.run(["service", "postgresql", "stop"], check=False, capture_output=True)
    subprocess.run(["service", "redis-server", "stop"], check=False, capture_output=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze a PR using Claude")
    parser.add_argument("context_file", help="Path to PR context JSON file")
    parser.add_argument("--fix", action="store_true", help="Attempt to implement fixes")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")

    args = parser.parse_args()

    context_file = Path(args.context_file)
    if not context_file.exists():
        print(f"Error: Context file not found: {context_file}", file=sys.stderr)
        return 1

    print(f"Loading PR context from: {context_file}")

    # Load context
    ctx = load_context(context_file)

    owner = ctx.get("owner", "unknown")
    repo = ctx.get("repo", "unknown")
    pr_number = ctx.get("pr_number", "?")

    print(f"Analyzing: {owner}/{repo}#{pr_number}")
    print("=" * 60)

    # Build prompt
    prompt = build_analysis_prompt(ctx, fix_mode=args.fix)

    # Run Claude
    success = analyze_with_claude(prompt, interactive=args.interactive)

    # Stop background services for clean exit
    stop_background_services()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
