#!/usr/bin/env python3
"""
GitHub Check Monitor - One-shot analysis of PR check failures

Triggered by github-sync.service after syncing PR data.
Uses Claude Code to intelligently analyze failures and suggest fixes.
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    """Run one-shot check analysis using Claude Code."""
    print("🔍 GitHub Check Monitor - Analyzing PR check failures...")

    github_dir = Path.home() / "context-sync" / "github"
    checks_dir = github_dir / "checks"
    prs_dir = github_dir / "prs"

    if not checks_dir.exists():
        print("GitHub checks directory not found - skipping watch")
        return 0

    # Collect all check failures
    failures = []
    for check_file in checks_dir.glob("*-PR-*-checks.json"):
        try:
            with check_file.open() as f:
                data = json.load(f)

            pr_num = data["pr_number"]
            repo = data["repository"]
            failed_checks = [c for c in data["checks"] if c.get("conclusion") == "failure"]

            if failed_checks:
                # Load PR context
                repo_name = repo.split("/")[-1]
                pr_file = prs_dir / f"{repo_name}-PR-{pr_num}.md"
                pr_context = pr_file.read_text() if pr_file.exists() else "PR details not available"

                failures.append(
                    {
                        "pr_number": pr_num,
                        "repository": repo,
                        "pr_context": pr_context,
                        "failed_checks": failed_checks,
                        "check_file": str(check_file),
                    }
                )

        except Exception as e:
            print(f"Error processing {check_file}: {e}")

    if not failures:
        print("No check failures found")
        return 0

    print(f"Found {len(failures)} PR(s) with check failures")

    # Construct prompt for Claude
    failures_summary = []
    for f in failures:
        failures_summary.append(
            f"**PR #{f['pr_number']}** ({f['repository']}): {len(f['failed_checks'])} failed checks"
        )

    prompt = f"""# GitHub PR Check Failure Analysis

You are analyzing PR check failures. Your goal is to understand failures, suggest fixes, and potentially implement automatic fixes.

## Summary

{len(failures)} PR(s) with failing checks detected:
{chr(10).join("- " + s for s in failures_summary)}

## Full Details

"""

    for f in failures:
        prompt += f"""
### PR #{f["pr_number"]} - {f["repository"]}

**PR Context:**
```
{f["pr_context"][:1000]}...
```

**Failed Checks:**
"""
        for check in f["failed_checks"]:
            prompt += f"""
- **{check["name"]}**: {check.get("conclusion", "failure")}
"""
            if check.get("full_log"):
                log = check["full_log"]
                prompt += f"""
  Log excerpt (first 500 + last 500 chars):
  ```
  {log[:500]}
  ...
  {log[-500:]}
  ```
"""

    prompt += """

## Your Workflow (per ADR)

For each PR with failures:

1. **Analyze the failure**:
   - Review check logs to identify root cause
   - Examine PR context and changed files
   - Determine if this is: lint error, test failure, build error, etc.

2. **Track in Beads**:
   - Create Beads task: `bd add "Fix check failures in PR #<num>" --tags github,ci`
   - Include PR number, repo, and failure types

3. **Attempt automatic fix** (if possible):
   - Lint errors: Often auto-fixable
   - Simple test fixes: Update assertions if clear
   - Build errors: Check dependencies, imports
   - Checkout the PR branch and make fixes
   - Commit with clear message
   - Mark Beads task as in-progress

4. **Create notification** to `~/sharing/notifications/`:
   - Summary of failures
   - Root cause analysis
   - Fix status (auto-fixed, needs human, blocked)
   - Link to PR and Beads task
   - Suggested next steps

## Important Notes

- You're in an ephemeral container
- PRs are synced to ~/context-sync/github/
- You can check out branches and make commits
- Focus on user's own PRs only
- Use Beads to track all work

Analyze these failures now and take appropriate action."""

    # Run Claude Code
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            check=False,
            capture_output=False,
            text=True,
            timeout=900,  # 15 minute timeout
        )

        if result.returncode == 0:
            print("✅ Check analysis complete")
            return 0
        else:
            print(f"⚠️  Claude exited with code {result.returncode}")
            return 1

    except subprocess.TimeoutExpired:
        print("⚠️ Analysis timed out after 15 minutes")
        return 1
    except Exception as e:
        print(f"❌ Error running Claude: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
