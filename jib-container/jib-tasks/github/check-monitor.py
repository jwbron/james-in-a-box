#!/usr/bin/env python3
"""
GitHub Check Monitor - One-shot analysis of PR check failures

Triggered by github-sync.service after syncing PR data.
Uses Claude Code to intelligently analyze failures and suggest fixes.

Each PR maintains persistent context in Beads for memory across sessions.
"""

import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PRContextManager:
    """Manages persistent PR context in Beads.

    Each PR gets a unique task that tracks its entire lifecycle:
    - Comments and responses
    - CI check failures and fixes
    - Review feedback and changes

    Context ID format: pr-<repo>-<number> (e.g., pr-james-in-a-box-75)
    """

    def __init__(self):
        self.beads_dir = Path.home() / "beads"

    def get_context_id(self, repo: str, pr_num: int) -> str:
        """Generate unique context ID for a PR."""
        repo_name = repo.split('/')[-1]
        return f"pr-{repo_name}-{pr_num}"

    def search_context(self, repo: str, pr_num: int) -> Optional[str]:
        """Search for existing beads task for this PR."""
        context_id = self.get_context_id(repo, pr_num)
        try:
            result = subprocess.run(
                ['bd', 'list', '--search', context_id, '--allow-stale'],
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if line.strip() and line.startswith('beads-'):
                        return line.split()[0]
            return None
        except Exception as e:
            logger.warning(f"Failed to search beads context: {e}")
            return None

    def get_context(self, repo: str, pr_num: int) -> Optional[Dict]:
        """Get existing context for a PR."""
        task_id = self.search_context(repo, pr_num)
        if not task_id:
            return None

        try:
            result = subprocess.run(
                ['bd', 'show', task_id, '--allow-stale'],
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10
            )
            if result.returncode == 0:
                return {
                    'task_id': task_id,
                    'content': result.stdout.strip()
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to get beads context: {e}")
            return None

    def create_context(self, repo: str, pr_num: int, pr_title: str) -> Optional[str]:
        """Create new beads task for a PR."""
        context_id = self.get_context_id(repo, pr_num)
        repo_name = repo.split('/')[-1]

        try:
            result = subprocess.run(
                ['bd', 'create', f'PR #{pr_num}: {pr_title}',
                 '--label', 'github-pr',
                 '--label', context_id,
                 '--label', repo_name,
                 '--label', 'ci-failure',
                 '--allow-stale'],
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if 'beads-' in output:
                    for word in output.split():
                        if word.startswith('beads-'):
                            return word.rstrip(':')
            return None
        except Exception as e:
            logger.warning(f"Failed to create beads context: {e}")
            return None

    def update_context(self, task_id: str, notes: str, status: Optional[str] = None) -> bool:
        """Update beads task with new notes."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        timestamped_notes = f"=== {timestamp} ===\n{notes}"

        try:
            cmd = ['bd', 'update', task_id, '--notes', timestamped_notes, '--allow-stale']
            if status:
                cmd.extend(['--status', status])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to update beads context: {e}")
            return False

    def get_or_create_context(self, repo: str, pr_num: int, pr_title: str = "") -> Optional[str]:
        """Get existing context or create new one."""
        existing = self.search_context(repo, pr_num)
        if existing:
            return existing
        return self.create_context(repo, pr_num, pr_title or f"PR #{pr_num}")


def main():
    """Run one-shot check analysis using Claude Code."""
    print("🔍 GitHub Check Monitor - Analyzing PR check failures...")

    github_dir = Path.home() / "context-sync" / "github"
    checks_dir = github_dir / "checks"
    prs_dir = github_dir / "prs"

    if not checks_dir.exists():
        print("GitHub checks directory not found - skipping watch")
        return 0

    # Initialize PR context manager
    pr_context_mgr = PRContextManager()

    # Collect all check failures
    failures = []
    for check_file in checks_dir.glob("*-PR-*-checks.json"):
        try:
            with check_file.open() as f:
                data = json.load(f)

            pr_num = data['pr_number']
            repo = data['repository']
            failed_checks = [c for c in data['checks'] if c.get('conclusion') == 'failure']

            if failed_checks:
                # Load PR context
                repo_name = repo.split('/')[-1]
                pr_file = prs_dir / f"{repo_name}-PR-{pr_num}.md"
                pr_context = pr_file.read_text() if pr_file.exists() else "PR details not available"

                # Get or create beads context for this PR
                beads_task_id = pr_context_mgr.get_or_create_context(repo, pr_num, f"CI failure in PR #{pr_num}")
                beads_context = None
                if beads_task_id:
                    beads_context = pr_context_mgr.get_context(repo, pr_num)
                    # Update with check failure info
                    check_names = [c['name'] for c in failed_checks]
                    pr_context_mgr.update_context(
                        beads_task_id,
                        f"CI check failure detected\nFailed checks: {', '.join(check_names)}",
                        status='in_progress'
                    )
                    print(f"  PR #{pr_num}: Beads task {beads_task_id}")

                failures.append({
                    'pr_number': pr_num,
                    'repository': repo,
                    'repo_name': repo_name,
                    'pr_context': pr_context,
                    'failed_checks': failed_checks,
                    'check_file': str(check_file),
                    'beads_task_id': beads_task_id,
                    'beads_context': beads_context
                })

        except Exception as e:
            print(f"Error processing {check_file}: {e}")

    if not failures:
        print("No check failures found")
        return 0

    print(f"Found {len(failures)} PR(s) with check failures")

    # Construct prompt for Claude
    failures_summary = []
    for f in failures:
        failures_summary.append(f"**PR #{f['pr_number']}** ({f['repository']}): {len(f['failed_checks'])} failed checks")

    prompt = f"""# GitHub PR Check Failure Analysis

You are analyzing PR check failures. Your goal is to understand failures, suggest fixes, and potentially implement automatic fixes.

## Summary

{len(failures)} PR(s) with failing checks detected:
{chr(10).join('- ' + s for s in failures_summary)}

## Full Details

"""

    for f in failures:
        # Include beads context if available
        beads_section = ""
        if f.get('beads_context'):
            beads_section = f"""
**Beads Task**: {f['beads_task_id']}
**Previous Context**:
```
{f['beads_context'].get('content', '')[:1000]}
```
"""
        prompt += f"""
### PR #{f['pr_number']} - {f['repository']}

**Beads Task**: {f.get('beads_task_id', 'None')}
{beads_section}
**PR Context:**
```
{f['pr_context'][:1000]}...
```

**Failed Checks:**
"""
        for check in f['failed_checks']:
            prompt += f"""
- **{check['name']}**: {check.get('conclusion', 'failure')}
"""
            if check.get('full_log'):
                log = check['full_log']
                prompt += f"""
  Log excerpt (first 500 + last 500 chars):
  ```
  {log[:500]}
  ...
  {log[-500:]}
  ```
"""

    prompt += """

## Your Workflow

For each PR with failures:

1. **Check Beads Context First**:
   - A Beads task has been created/updated for each PR with failures
   - Review previous context to understand what's already been tried
   - Avoid repeating failed approaches

2. **Analyze the failure**:
   - Review check logs to identify root cause
   - Examine PR context and changed files
   - Determine if this is: lint error, test failure, build error, etc.

3. **Attempt automatic fix** (if possible):
   - Lint errors: Often auto-fixable
   - Simple test fixes: Update assertions if clear
   - Build errors: Check dependencies, imports
   - Checkout the PR branch and make fixes
   - Commit with clear message

4. **Update Beads Context**:
   - Use `bd update <task-id> --notes "your update"` to record what was done
   - Include: analysis results, fix attempts, current status

5. **Create notification** to `~/sharing/notifications/`:
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
- Each PR has ONE Beads task that tracks its entire lifecycle
- Check existing Beads context before starting new analysis

Analyze these failures now and take appropriate action."""

    # Run Claude Code
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=False,
            text=True,
            timeout=900  # 15 minute timeout
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


if __name__ == '__main__':
    sys.exit(main())
