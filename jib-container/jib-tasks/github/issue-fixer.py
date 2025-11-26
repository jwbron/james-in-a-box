#!/usr/bin/env python3
"""
GitHub PR Issue Fixer - Detects and reports PR issues for Claude to fix

Triggered by github-sync.service after syncing PR data.
Detects check failures and merge conflicts, then delegates to Claude
to determine the appropriate fix strategy.
"""

import sys
import json
import subprocess
from pathlib import Path


def detect_merge_conflicts(prs_dir: Path, khan_dir: Path) -> list:
    """Detect PRs with potential merge conflicts."""
    conflicts = []

    for pr_file in prs_dir.glob("*-PR-*.md"):
        try:
            content = pr_file.read_text()
            pr_info = parse_pr_file(content)
            if not pr_info:
                continue

            repo_name = pr_info['repository'].split('/')[-1]
            repo_path = khan_dir / repo_name

            if not repo_path.exists():
                continue

            # Check for conflicts by attempting a dry-run merge
            has_conflict, details = check_conflict(
                repo_path, pr_info['head_branch'], pr_info['base_branch']
            )

            if has_conflict:
                conflicts.append({
                    'pr_number': pr_info['pr_number'],
                    'repository': pr_info['repository'],
                    'head_branch': pr_info['head_branch'],
                    'base_branch': pr_info['base_branch'],
                    'title': pr_info.get('title', 'Unknown'),
                    'conflict_details': details,
                })

        except Exception as e:
            print(f"Error checking {pr_file.name}: {e}")

    return conflicts


def parse_pr_file(content: str) -> dict | None:
    """Parse PR info from markdown file."""
    info = {
        "pr_number": None,
        "repository": None,
        "head_branch": None,
        "base_branch": None,
        "title": None,
    }

    for line in content.split("\n"):
        if line.startswith("# PR #"):
            parts = line[6:].split(":", 1)
            if parts:
                try:
                    info["pr_number"] = int(parts[0].strip())
                except ValueError:
                    pass
                if len(parts) > 1:
                    info["title"] = parts[1].strip()
        elif line.startswith("**Repository**:"):
            info["repository"] = line.replace("**Repository**:", "").strip()
        elif line.startswith("**Branch**:"):
            branch_info = line.replace("**Branch**:", "").strip()
            if " → " in branch_info:
                head, base = branch_info.split(" → ", 1)
                info["head_branch"] = head.strip()
                info["base_branch"] = base.strip()

    if info["pr_number"] and info["repository"]:
        return info
    return None


def check_conflict(repo_path: Path, head_branch: str, base_branch: str) -> tuple[bool, str]:
    """Check if merging base into head would cause conflicts."""
    try:
        # Fetch latest
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo_path,
            capture_output=True,
            check=False,
        )

        # Try checkout
        result = subprocess.run(
            ["git", "checkout", head_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "checkout", "-b", head_branch, f"origin/{head_branch}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return False, ""

        # Pull latest
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path,
            capture_output=True,
            check=False,
        )

        # Try merge (dry run)
        merge_result = subprocess.run(
            ["git", "merge", f"origin/{base_branch}", "--no-commit", "--no-ff"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )

        has_conflict = merge_result.returncode != 0 and "CONFLICT" in merge_result.stdout

        # Abort merge
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=repo_path,
            capture_output=True,
            check=False,
        )

        if has_conflict:
            return True, merge_result.stdout
        return False, ""

    except Exception as e:
        return False, str(e)


def collect_check_failures(checks_dir: Path, prs_dir: Path) -> list:
    """Collect all check failures from synced data."""
    failures = []

    for check_file in checks_dir.glob("*-PR-*-checks.json"):
        try:
            with check_file.open() as f:
                data = json.load(f)

            pr_num = data['pr_number']
            repo = data['repository']
            failed_checks = [c for c in data['checks'] if c.get('conclusion') == 'failure']

            if failed_checks:
                repo_name = repo.split('/')[-1]
                pr_file = prs_dir / f"{repo_name}-PR-{pr_num}.md"
                pr_context = pr_file.read_text() if pr_file.exists() else "PR details not available"

                failures.append({
                    'pr_number': pr_num,
                    'repository': repo,
                    'pr_context': pr_context,
                    'failed_checks': failed_checks,
                })

        except Exception as e:
            print(f"Error processing {check_file}: {e}")

    return failures


def build_prompt(failures: list, conflicts: list) -> str:
    """Build the prompt for Claude to analyze and fix issues."""
    if not failures and not conflicts:
        return ""

    prompt = """# GitHub PR Issue Analysis and Fixes

You are analyzing PRs for issues (check failures, merge conflicts). Your goal is to:
1. Understand the root cause of each issue
2. Determine the appropriate fix strategy
3. Implement fixes where possible
4. Report on what you did

"""

    # Merge conflicts section
    if conflicts:
        prompt += f"## Merge Conflicts ({len(conflicts)} PR(s))\n\n"
        for c in conflicts:
            prompt += f"""### PR #{c['pr_number']} - {c['repository']}
**Title**: {c['title']}
**Branches**: `{c['head_branch']}` ← `{c['base_branch']}`

Conflict details:
```
{c['conflict_details'][:1000]}
```

"""

    # Check failures section
    if failures:
        prompt += f"## Check Failures ({len(failures)} PR(s))\n\n"
        for f in failures:
            prompt += f"""### PR #{f['pr_number']} - {f['repository']}

**PR Context:**
```
{f['pr_context'][:1000]}...
```

**Failed Checks:**
"""
            for check in f['failed_checks']:
                prompt += f"- **{check['name']}**: {check.get('conclusion', 'failure')}\n"
                if check.get('full_log'):
                    log = check['full_log']
                    prompt += f"""  Log excerpt:
  ```
  {log[:500]}
  ...
  {log[-500:]}
  ```
"""

    prompt += """
## Your Task

For each issue:

1. **Analyze** - Understand what's wrong
2. **Fix** - Checkout the PR branch and implement appropriate fixes:
   - Merge conflicts: Resolve conflicts intelligently based on the code context
   - Lint/format errors: Run appropriate linters/formatters
   - Test failures: Examine and fix tests if the fix is clear
   - Build errors: Check dependencies, imports, etc.
3. **Commit** - Commit your fixes with clear messages
4. **Push** - Push to the PR branch
5. **Comment** - Add a PR comment explaining what you fixed
6. **Notify** - Create a notification summarizing your work

Use your judgment to determine the best approach for each issue. You have full access
to the codebase and can make any changes needed.

**Track in Beads**: `bd add "Fix issues in PR #<num>" --tags github,ci`

Begin analysis now.
"""

    return prompt


def main():
    """Main entry point."""
    print("GitHub PR Issue Fixer - Detecting issues...")

    github_dir = Path.home() / "context-sync" / "github"
    checks_dir = github_dir / "checks"
    prs_dir = github_dir / "prs"
    khan_dir = Path.home() / "khan"

    # Collect issues
    failures = []
    if checks_dir.exists():
        failures = collect_check_failures(checks_dir, prs_dir)
        print(f"Found {len(failures)} PR(s) with check failures")

    conflicts = []
    if prs_dir.exists():
        conflicts = detect_merge_conflicts(prs_dir, khan_dir)
        print(f"Found {len(conflicts)} PR(s) with merge conflicts")

    if not failures and not conflicts:
        print("No issues found - all PRs are healthy")
        return 0

    # Build prompt and run Claude
    prompt = build_prompt(failures, conflicts)

    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=False,
            text=True,
            timeout=900,  # 15 minute timeout
        )

        if result.returncode == 0:
            print("Issue analysis and fixes complete")
            return 0
        else:
            print(f"Claude exited with code {result.returncode}")
            return 1

    except subprocess.TimeoutExpired:
        print("Analysis timed out after 15 minutes")
        return 1
    except Exception as e:
        print(f"Error running Claude: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
