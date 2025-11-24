#!/usr/bin/env python3
"""
GitHub PR Sync - Syncs open PRs to disk for JIB consumption

Fetches:
- PR metadata, description, files
- Full diffs
- Check status
- Full logs for failed checks (user's PRs only)

Stores to: ~/context-sync/github/
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class GitHubSync:
    def __init__(self, sync_dir: Path):
        self.sync_dir = sync_dir
        self.prs_dir = sync_dir / "prs"
        self.checks_dir = sync_dir / "checks"

        # Ensure directories exist
        self.prs_dir.mkdir(parents=True, exist_ok=True)
        self.checks_dir.mkdir(parents=True, exist_ok=True)

    def gh_api(self, cmd: str) -> Any:
        """Run gh CLI command and return JSON output"""
        try:
            result = subprocess.run(
                ["gh"] + cmd.split(),
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running gh command: {cmd}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            raise
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from: {cmd}", file=sys.stderr)
            print(f"stdout: {result.stdout}", file=sys.stderr)
            raise

    def gh_text(self, cmd: str) -> str:
        """Run gh CLI command and return text output"""
        try:
            result = subprocess.run(
                ["gh"] + cmd.split(),
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error running gh command: {cmd}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            return ""

    def sync_prs(self):
        """Sync all open PRs authored by current user"""
        print("Fetching open PRs...")

        # Get list of open PRs
        prs = self.gh_api(
            "pr list --author @me --state open "
            "--json number,title,url,updatedAt,headRefName,baseRefName,repository"
        )

        print(f"Found {len(prs)} open PR(s)")

        pr_numbers = []
        for pr in prs:
            pr_num = pr['number']
            repo = pr['repository']['name']
            pr_numbers.append(pr_num)

            print(f"  Syncing PR #{pr_num} ({repo}): {pr['title']}")

            try:
                # Get full PR details
                pr_full = self.gh_api(
                    f"pr view {pr_num} --repo {pr['repository']['nameWithOwner']} "
                    f"--json number,title,body,author,url,state,createdAt,updatedAt,"
                    f"files,comments,headRefName,baseRefName,repository"
                )

                # Get diff
                diff = self.gh_text(
                    f"pr diff {pr_num} --repo {pr['repository']['nameWithOwner']}"
                )

                # Get check status
                checks = self.gh_api(
                    f"pr checks {pr_num} --repo {pr['repository']['nameWithOwner']} "
                    f"--json name,status,conclusion,startedAt,completedAt,detailsUrl"
                )

                # Write PR markdown and diff
                self.write_pr_markdown(pr_full, diff)

                # Write checks JSON and fetch logs for failures
                self.write_checks(pr_num, pr_full['repository']['nameWithOwner'], checks)

            except Exception as e:
                print(f"    Error syncing PR #{pr_num}: {e}", file=sys.stderr)
                continue

        # Update index
        self.write_index(prs)

        # Cleanup old PRs that are no longer open
        self.cleanup_closed_prs(pr_numbers)

    def write_pr_markdown(self, pr: Dict, diff: str):
        """Write PR as markdown file"""
        pr_num = pr['number']
        repo_name = pr['repository']['name']
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        # Write markdown
        with pr_file.open('w') as f:
            f.write(f"# PR #{pr_num}: {pr['title']}\n\n")
            f.write(f"**Repository**: {pr['repository']['nameWithOwner']}\n")
            f.write(f"**Author**: {pr['author']['login']}\n")
            f.write(f"**State**: {pr['state']}\n")
            f.write(f"**URL**: {pr['url']}\n")
            f.write(f"**Branch**: {pr['headRefName']} → {pr['baseRefName']}\n")
            f.write(f"**Created**: {pr['createdAt']}\n")
            f.write(f"**Updated**: {pr['updatedAt']}\n\n")

            f.write("## Description\n\n")
            f.write(pr.get('body', '(No description)') + "\n\n")

            f.write(f"## Files Changed ({len(pr.get('files', []))})\n\n")
            for file in pr.get('files', []):
                f.write(f"- `{file['path']}` (+{file['additions']}, -{file['deletions']})\n")

            if pr.get('comments'):
                f.write(f"\n## Comments ({len(pr['comments'])})\n\n")
                for comment in pr['comments']:
                    f.write(f"### {comment['author']['login']} ({comment['createdAt']})\n\n")
                    f.write(f"{comment['body']}\n\n")
                    f.write("---\n\n")

            f.write("## Diff\n\n")
            f.write(f"See: `{repo_name}-PR-{pr_num}.diff`\n")

        # Write diff
        diff_file.write_text(diff)
        print(f"    ✓ Wrote PR markdown and diff")

    def write_checks(self, pr_num: int, repo: str, checks: List[Dict]):
        """Write check status and fetch failed logs"""
        repo_name = repo.split('/')[-1]
        checks_file = self.checks_dir / f"{repo_name}-PR-{pr_num}-checks.json"

        enriched_checks = []
        failed_count = 0

        for check in checks:
            check_data = check.copy()

            # If failed, fetch full logs
            if check.get('conclusion') == 'failure':
                failed_count += 1
                print(f"    ⚠ Check failed: {check['name']}, fetching logs...")
                log = self.get_check_logs(pr_num, repo, check)
                if log:
                    check_data['full_log'] = log
                    print(f"      ✓ Fetched {len(log)} bytes of logs")
                else:
                    print(f"      ✗ Could not fetch logs")

            enriched_checks.append(check_data)

        with checks_file.open('w') as f:
            json.dump({
                'pr_number': pr_num,
                'repository': repo,
                'last_updated': datetime.utcnow().isoformat() + 'Z',
                'checks': enriched_checks,
                'summary': {
                    'total': len(checks),
                    'failed': failed_count,
                    'passed': len([c for c in checks if c.get('conclusion') == 'success']),
                    'pending': len([c for c in checks if c.get('status') != 'completed'])
                }
            }, f, indent=2)

        if failed_count > 0:
            print(f"    ✓ Wrote checks ({failed_count} failed)")
        else:
            print(f"    ✓ Wrote checks (all passing)")

    def get_check_logs(self, pr_num: int, repo: str, check: Dict) -> Optional[str]:
        """Fetch full logs for a failed check"""
        # Try to extract run ID from details URL
        # GitHub Actions URL format: https://github.com/org/repo/actions/runs/12345
        details_url = check.get('detailsUrl', '')

        if '/actions/runs/' in details_url:
            try:
                run_id = details_url.split('/runs/')[-1].split('/')[0].split('?')[0]

                # Fetch logs using gh CLI
                logs = self.gh_text(f"run view {run_id} --repo {repo} --log-failed")

                if logs:
                    return logs

            except Exception as e:
                print(f"      Error fetching logs for run {run_id}: {e}", file=sys.stderr)

        # Fallback: try to get job logs if available
        try:
            # List jobs for the check
            # This is a best-effort attempt
            return None
        except:
            return None

    def write_index(self, prs: List[Dict]):
        """Write quick index of all PRs"""
        index = {
            'last_sync': datetime.utcnow().isoformat() + 'Z',
            'pr_count': len(prs),
            'prs': [
                {
                    'number': pr['number'],
                    'repository': pr['repository']['nameWithOwner'],
                    'title': pr['title'],
                    'url': pr['url'],
                    'head_branch': pr['headRefName'],
                    'base_branch': pr['baseRefName'],
                    'updated': pr['updatedAt']
                }
                for pr in prs
            ]
        }

        with (self.sync_dir / 'index.json').open('w') as f:
            json.dump(index, f, indent=2)

        print(f"✓ Updated index with {len(prs)} PR(s)")

    def cleanup_closed_prs(self, current_pr_numbers: List[int]):
        """Remove files for PRs that are no longer open"""
        # Find all PR files
        all_pr_files = list(self.prs_dir.glob("*-PR-*.md"))
        all_check_files = list(self.checks_dir.glob("*-PR-*-checks.json"))

        for pr_file in all_pr_files:
            # Extract PR number from filename: repo-PR-123.md
            try:
                pr_num = int(pr_file.stem.split('-PR-')[-1])
                if pr_num not in current_pr_numbers:
                    # This PR is no longer open, remove it
                    pr_file.unlink()
                    diff_file = pr_file.parent / f"{pr_file.stem}.diff"
                    if diff_file.exists():
                        diff_file.unlink()
                    print(f"  Removed closed PR #{pr_num} files")
            except (ValueError, IndexError):
                pass

        for check_file in all_check_files:
            try:
                pr_num = int(check_file.stem.split('-PR-')[-1].split('-checks')[0])
                if pr_num not in current_pr_numbers:
                    check_file.unlink()
            except (ValueError, IndexError):
                pass


def main():
    """Main entry point"""
    sync_dir = Path.home() / "context-sync" / "github"

    print("=" * 60)
    print("GitHub PR Sync")
    print("=" * 60)
    print()

    try:
        syncer = GitHubSync(sync_dir)
        syncer.sync_prs()
        print()
        print("=" * 60)
        print("✓ Sync complete")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Sync failed: {e}", file=sys.stderr)
        print("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()
