#!/usr/bin/env python3
"""
GitHub PR Check Watcher - Monitors for CI/CD failures and triggers analysis

Runs in JIB container, monitors ~/context-sync/github/ for check failures,
automatically analyzes failures and creates notifications with suggested fixes.
"""

import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class GitHubWatcher:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.checks_dir = self.github_dir / "checks"
        self.prs_dir = self.github_dir / "prs"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.beads_dir = Path.home() / "beads"

        # Track which failures we've already notified about
        self.state_file = Path.home() / "sharing" / "tracking" / "github-watcher-state.json"
        self.notified_failures = self.load_state()

    def load_state(self) -> Dict:
        """Load previous notification state"""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {'notified': {}}

    def save_state(self):
        """Save notification state"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump({'notified': self.notified_failures}, f, indent=2)

    def watch(self):
        """Main watch loop - check for failures once"""
        if not self.checks_dir.exists():
            print("GitHub checks directory not found - skipping watch")
            return

        # Scan all check files
        for check_file in self.checks_dir.glob("*-PR-*-checks.json"):
            try:
                self.process_check_file(check_file)
            except Exception as e:
                print(f"Error processing {check_file}: {e}")

    def process_check_file(self, check_file: Path):
        """Process a single PR's check file"""
        with check_file.open() as f:
            data = json.load(f)

        pr_num = data['pr_number']
        repo = data['repository']
        repo_name = repo.split('/')[-1]

        # Find failed checks
        failed_checks = [c for c in data['checks'] if c.get('conclusion') == 'failure']

        if not failed_checks:
            return  # All passing

        # Check if we've already notified about these specific failures
        check_key = f"{repo}-{pr_num}"
        failed_names = sorted([c['name'] for c in failed_checks])
        failed_signature = f"{check_key}:" + ",".join(failed_names)

        if failed_signature in self.notified_failures:
            # Already notified about this exact set of failures
            return

        print(f"New check failure detected: PR #{pr_num} ({repo})")
        print(f"  Failed checks: {', '.join(failed_names)}")

        # Get PR context
        pr_context = self.get_pr_context(repo_name, pr_num)

        # Analyze failures and create notification
        self.analyze_and_notify(pr_num, repo, pr_context, failed_checks)

        # Mark as notified
        self.notified_failures[failed_signature] = datetime.utcnow().isoformat() + 'Z'
        self.save_state()

    def get_pr_context(self, repo_name: str, pr_num: int) -> Dict:
        """Get PR context from synced files"""
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        context = {
            'pr_number': pr_num,
            'title': f"PR #{pr_num}",
            'url': '',
            'branch': '',
            'files_changed': []
        }

        if pr_file.exists():
            # Parse PR markdown for key info
            with pr_file.open() as f:
                content = f.read()
                lines = content.split('\n')

                for line in lines:
                    if line.startswith('# PR #'):
                        context['title'] = line.replace('# PR #', '').replace(f'{pr_num}: ', '').strip()
                    elif line.startswith('**URL**:'):
                        context['url'] = line.replace('**URL**:', '').strip()
                    elif line.startswith('**Branch**:'):
                        context['branch'] = line.replace('**Branch**:', '').strip()
                    elif line.strip().startswith('- `') and '(+' in line:
                        # File change line
                        context['files_changed'].append(line.strip())

        if diff_file.exists():
            context['diff_available'] = True
            context['diff_size'] = diff_file.stat().st_size

        return context

    def analyze_and_notify(self, pr_num: int, repo: str, pr_context: Dict, failed_checks: List[Dict]):
        """Analyze failures and create notification with suggested actions"""
        repo_name = repo.split('/')[-1]

        # Create Beads task for the failure
        beads_id = self.create_beads_task(pr_num, repo_name, pr_context, failed_checks)

        # Analyze the failure
        analysis = self.analyze_failure(pr_context, failed_checks)

        # Create notification
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notifications_dir / f"{timestamp}-pr-check-failed-{pr_num}.md"

        with notif_file.open('w') as f:
            f.write(f"# 🔴 PR Check Failed: #{pr_num}\n\n")
            f.write(f"**PR**: {pr_context['title']}\n")
            f.write(f"**Repository**: {repo}\n")
            f.write(f"**URL**: {pr_context.get('url', 'N/A')}\n")
            f.write(f"**Branch**: {pr_context.get('branch', 'N/A')}\n")
            f.write(f"**Failed Checks**: {len(failed_checks)}\n")
            if beads_id:
                f.write(f"**Beads Task**: {beads_id}\n")
            f.write("\n")

            # List failed checks with logs
            for check in failed_checks:
                f.write(f"## ❌ {check['name']}\n\n")
                f.write(f"**Status**: {check['status']}\n")
                f.write(f"**Conclusion**: {check['conclusion']}\n")
                if check.get('completedAt'):
                    f.write(f"**Completed**: {check['completedAt']}\n")
                f.write("\n")

                if check.get('full_log'):
                    # Include excerpt of log (first 1000 chars + last 1000 chars)
                    log = check['full_log']
                    if len(log) > 2500:
                        f.write("### Log Excerpt (First 1000 chars)\n\n")
                        f.write("```\n")
                        f.write(log[:1000])
                        f.write("\n...\n")
                        f.write("\n### Log Excerpt (Last 1000 chars)\n\n")
                        f.write(log[-1000:])
                        f.write("\n```\n\n")
                    else:
                        f.write("### Full Log\n\n")
                        f.write("```\n")
                        f.write(log)
                        f.write("\n```\n\n")
                else:
                    f.write("*(Logs not available)*\n\n")

            # Analysis and suggested actions
            f.write("## 🔍 Analysis\n\n")
            f.write(f"{analysis['summary']}\n\n")

            if analysis.get('root_cause'):
                f.write(f"**Root Cause**: {analysis['root_cause']}\n\n")

            f.write("## 🛠️ Suggested Actions\n\n")
            for i, action in enumerate(analysis['actions'], 1):
                f.write(f"{i}. {action}\n")
            f.write("\n")

            if analysis.get('can_auto_fix'):
                f.write("## 🤖 Automatic Fix Available\n\n")
                f.write("JIB can automatically implement a fix for this issue.\n\n")
                f.write(f"**Fix**: {analysis['auto_fix_description']}\n\n")
                f.write("**Next Steps**:\n")
                f.write("- Reply 'implement fix' to create a branch with the fix\n")
                f.write("- Reply 'analyze further' for more detailed investigation\n")
                f.write("- Reply 'skip' to handle manually\n")
            else:
                f.write("## 📋 Next Steps\n\n")
                f.write("This failure requires manual investigation.\n\n")
                f.write("**How I can help**:\n")
                f.write("- Reply 'analyze logs' for detailed log analysis\n")
                f.write("- Reply 'check similar' to find similar past failures\n")
                f.write("- Reply 'suggest debugging' for debugging strategies\n")

            f.write("\n---\n")
            f.write(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📂 PR #{pr_num} in {repo}\n")

        print(f"  ✓ Created notification: {notif_file.name}")

    def create_beads_task(self, pr_num: int, repo_name: str, pr_context: Dict, failed_checks: List[Dict]) -> Optional[str]:
        """Create Beads task for the PR failure"""
        try:
            # Check if beads is available
            result = subprocess.run(['which', 'beads'], capture_output=True)
            if result.returncode != 0:
                return None

            # Create task
            check_names = ', '.join([c['name'] for c in failed_checks])
            title = f"Fix PR #{pr_num} check failures: {check_names}"

            result = subprocess.run(
                ['beads', 'add', title, '--tags', f'pr-{pr_num}', 'ci-failure', repo_name, 'urgent'],
                cwd=self.beads_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Extract bead ID from output (usually first line)
                output = result.stdout.strip()
                # Output format: "Created bd-a3f8: Fix PR #123..."
                if 'Created' in output and 'bd-' in output:
                    bead_id = output.split('bd-')[1].split(':')[0]
                    bead_id = f"bd-{bead_id.split()[0]}"

                    # Add notes
                    notes = f"PR #{pr_num} in {repo_name}\n"
                    notes += f"Failed checks: {check_names}\n"
                    notes += f"URL: {pr_context.get('url', 'N/A')}\n"

                    subprocess.run(
                        ['beads', 'update', bead_id, '--notes', notes],
                        cwd=self.beads_dir,
                        capture_output=True
                    )

                    print(f"  ✓ Created Beads task: {bead_id}")
                    return bead_id
        except Exception as e:
            print(f"  Could not create Beads task: {e}")

        return None

    def analyze_failure(self, pr_context: Dict, failed_checks: List[Dict]) -> Dict:
        """Analyze failure and determine if auto-fix is possible"""
        analysis = {
            'summary': '',
            'root_cause': None,
            'actions': [],
            'can_auto_fix': False,
            'auto_fix_description': None
        }

        # Simple heuristic analysis
        check_names = [c['name'].lower() for c in failed_checks]
        logs = [c.get('full_log', '') for c in failed_checks]
        combined_log = '\n'.join(logs).lower()

        # Detect common failure patterns
        if any('pytest' in name or 'test' in name for name in check_names):
            analysis['summary'] = "Test failures detected in PR checks."

            # Check for common test failure patterns
            if 'importerror' in combined_log or 'modulenotfounderror' in combined_log:
                analysis['root_cause'] = "Missing dependency or import error"
                analysis['actions'] = [
                    "Check requirements.txt or package.json for missing dependencies",
                    "Verify all imports are correct",
                    "Run tests locally to reproduce"
                ]
                analysis['can_auto_fix'] = False  # Need human judgment

            elif 'assertion' in combined_log or 'expected' in combined_log:
                analysis['root_cause'] = "Test assertion failure"
                analysis['actions'] = [
                    "Review the failing test to understand expectations",
                    "Check if PR changes broke test assumptions",
                    "Update test if expectations changed"
                ]
                analysis['can_auto_fix'] = False

            else:
                analysis['root_cause'] = "Test failure (cause unclear from logs)"
                analysis['actions'] = [
                    "Review full test output",
                    "Run tests locally",
                    "Check for recent changes that might affect tests"
                ]

        elif any('lint' in name or 'eslint' in name or 'pylint' in name for name in check_names):
            analysis['summary'] = "Code quality/linting failures detected."
            analysis['root_cause'] = "Code style or linting violations"
            analysis['actions'] = [
                "Run linter locally: eslint or pylint",
                "Auto-fix with: eslint --fix or black/autopep8",
                "Review and commit fixes"
            ]
            analysis['can_auto_fix'] = True
            analysis['auto_fix_description'] = "Run linter with --fix flag and commit changes"

        elif any('build' in name or 'compile' in name for name in check_names):
            analysis['summary'] = "Build/compilation failures detected."
            analysis['root_cause'] = "Build errors"
            analysis['actions'] = [
                "Check build logs for specific errors",
                "Verify all dependencies are available",
                "Run build locally to reproduce"
            ]

        else:
            analysis['summary'] = f"{len(failed_checks)} check(s) failed in PR."
            analysis['actions'] = [
                "Review check logs for details",
                "Investigate each failed check individually",
                "Determine if failures are related to PR changes"
            ]

        return analysis


def main():
    """Main entry point"""
    watcher = GitHubWatcher()
    watcher.watch()


if __name__ == '__main__':
    main()
