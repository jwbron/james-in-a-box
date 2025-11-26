#!/usr/bin/env python3
"""
GitHub PR Check Watcher - Monitors for CI/CD failures and triggers analysis

Runs in jib container, monitors ~/context-sync/github/ for check failures,
automatically analyzes failures and creates notifications with suggested fixes.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path


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

    def load_state(self) -> dict:
        """Load previous notification state"""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {"notified": {}}

    def save_state(self):
        """Save notification state"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump({"notified": self.notified_failures}, f, indent=2)

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

        pr_num = data["pr_number"]
        repo = data["repository"]
        repo_name = repo.split("/")[-1]

        # Find failed checks
        # Note: gh pr checks uses 'state' (e.g., 'FAILURE') not 'conclusion'
        failed_checks = [
            c for c in data["checks"]
            if c.get("state", "").upper() in ("FAILURE", "FAILED")
        ]

        if not failed_checks:
            return  # All passing

        # Check if we've already notified about these specific failures
        check_key = f"{repo}-{pr_num}"
        failed_names = sorted([c["name"] for c in failed_checks])
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
        self.notified_failures[failed_signature] = datetime.utcnow().isoformat() + "Z"
        self.save_state()

    def get_pr_context(self, repo_name: str, pr_num: int) -> dict:
        """Get PR context from synced files"""
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        context = {
            "pr_number": pr_num,
            "title": f"PR #{pr_num}",
            "url": "",
            "branch": "",
            "files_changed": [],
        }

        if pr_file.exists():
            # Parse PR markdown for key info
            with pr_file.open() as f:
                content = f.read()
                lines = content.split("\n")

                for line in lines:
                    if line.startswith("# PR #"):
                        context["title"] = (
                            line.replace("# PR #", "").replace(f"{pr_num}: ", "").strip()
                        )
                    elif line.startswith("**URL**:"):
                        context["url"] = line.replace("**URL**:", "").strip()
                    elif line.startswith("**Branch**:"):
                        context["branch"] = line.replace("**Branch**:", "").strip()
                    elif line.strip().startswith("- `") and "(+" in line:
                        # File change line
                        context["files_changed"].append(line.strip())

        if diff_file.exists():
            context["diff_available"] = True
            context["diff_size"] = diff_file.stat().st_size

        return context

    def analyze_and_notify(
        self, pr_num: int, repo: str, pr_context: dict, failed_checks: list[dict]
    ):
        """Analyze failures and create notification with suggested actions"""
        repo_name = repo.split("/")[-1]

        # Create Beads task for the failure
        beads_id = self.create_beads_task(pr_num, repo_name, pr_context, failed_checks)

        # Analyze the failure
        analysis = self.analyze_failure(pr_context, failed_checks)

        # If auto-fix is possible, implement it immediately
        fix_result = None
        if analysis.get("can_auto_fix"):
            fix_result = self.implement_auto_fix(pr_num, repo_name, pr_context, analysis, beads_id)

        # Create notification
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notifications_dir / f"{timestamp}-pr-check-failed-{pr_num}.md"

        with notif_file.open("w") as f:
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
                f.write(f"**State**: {check.get('state', 'FAILURE')}\n")
                if check.get("completedAt"):
                    f.write(f"**Completed**: {check['completedAt']}\n")
                f.write("\n")

                if check.get("full_log"):
                    # Include excerpt of log (first 1000 chars + last 1000 chars)
                    log = check["full_log"]
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

            if analysis.get("root_cause"):
                f.write(f"**Root Cause**: {analysis['root_cause']}\n\n")

            f.write("## 🛠️ Suggested Actions\n\n")
            for i, action in enumerate(analysis["actions"], 1):
                f.write(f"{i}. {action}\n")
            f.write("\n")

            if fix_result:
                f.write("## ✅ Automatic Fix Implemented\n\n")
                f.write(f"**Branch**: `{fix_result['branch']}`\n")
                f.write(f"**Changes**: {fix_result['changes']}\n\n")
                if fix_result.get("commit"):
                    f.write(f"**Commit**: {fix_result['commit']}\n\n")
                f.write("**Next Steps**:\n")
                f.write(f"1. Review the changes in branch `{fix_result['branch']}`\n")
                f.write("2. Test locally if needed\n")
                f.write("3. Push the branch and update the PR or create a new one\n")
                f.write("\n")
                if fix_result.get("notes"):
                    f.write(f"**Notes**: {fix_result['notes']}\n\n")
            elif analysis.get("can_auto_fix"):
                f.write("## ⚠️ Auto-Fix Failed\n\n")
                f.write("An automatic fix was attempted but failed.\n\n")
                f.write(f"**Intended Fix**: {analysis['auto_fix_description']}\n\n")
                f.write("**Next Steps**:\n")
                f.write("- Review the failure manually\n")
                f.write("- Reply 'analyze further' for more detailed investigation\n")
                f.write("\n")
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

    def implement_auto_fix(
        self, pr_num: int, repo_name: str, pr_context: dict, analysis: dict, beads_id: str | None
    ) -> dict | None:
        """
        Implement automatic fix for obvious issues (e.g., linting)

        Returns dict with fix result:
        {
            'branch': 'fix/pr-123-linting',
            'changes': 'Description of changes',
            'commit': 'commit hash',
            'notes': 'Additional notes'
        }
        """
        try:
            # Determine repository path
            repo_path = Path.home() / "khan" / repo_name
            if not repo_path.exists():
                print(f"  ⚠️ Repository not found: {repo_path}")
                return None

            # Get current branch from PR context
            pr_branch = pr_context.get("branch", "").split(" → ")[0].strip()
            if not pr_branch:
                print("  ⚠️ Could not determine PR branch")
                return None

            # Create fix branch name
            fix_branch = f"fix/pr-{pr_num}-autofix-{datetime.now().strftime('%Y%m%d')}"

            print(f"  🔧 Implementing auto-fix in {repo_name}")
            print(f"     Base branch: {pr_branch}")
            print(f"     Fix branch: {fix_branch}")

            # Change to repo directory
            original_dir = Path.cwd()

            try:
                import os

                os.chdir(repo_path)

                # Ensure we're on the PR branch
                result = subprocess.run(
                    ["git", "checkout", pr_branch], check=False, capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  ⚠️ Could not checkout branch {pr_branch}: {result.stderr}")
                    return None

                # Pull latest changes
                subprocess.run(["git", "pull"], check=False, capture_output=True)

                # Create new fix branch
                result = subprocess.run(
                    ["git", "checkout", "-b", fix_branch],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"  ⚠️ Could not create branch {fix_branch}: {result.stderr}")
                    return None

                # Determine and run appropriate fix command based on analysis
                fix_commands = []
                changes_description = []

                if "eslint" in analysis["auto_fix_description"].lower():
                    fix_commands.append(["npx", "eslint", ".", "--fix"])
                    changes_description.append("Ran eslint --fix")
                elif (
                    "pylint" in analysis["auto_fix_description"].lower()
                    or "black" in analysis["auto_fix_description"].lower()
                ):
                    # Run black for Python formatting
                    fix_commands.append(["black", "."])
                    changes_description.append("Ran black formatter")
                else:
                    # Generic linting fix - try both
                    fix_commands.append(["npx", "eslint", ".", "--fix"])
                    fix_commands.append(["black", "."])
                    changes_description.append("Ran available linters")

                # Run fix commands
                fix_output = []
                for cmd in fix_commands:
                    result = subprocess.run(
                        cmd, check=False, capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0 or result.stdout:
                        fix_output.append(f"{' '.join(cmd)}: {result.stdout[:200]}")

                # Check if there are changes
                result = subprocess.run(
                    ["git", "diff", "--name-only"], check=False, capture_output=True, text=True
                )

                changed_files = result.stdout.strip().split("\n")
                changed_files = [f for f in changed_files if f]

                if not changed_files:
                    print("  [info] No changes after running fix commands")
                    # Clean up branch
                    subprocess.run(["git", "checkout", pr_branch], check=False, capture_output=True)
                    subprocess.run(
                        ["git", "branch", "-D", fix_branch], check=False, capture_output=True
                    )
                    return None

                # Stage all changes
                subprocess.run(["git", "add", "-A"], check=False, capture_output=True)

                # Commit changes
                commit_message = f"Auto-fix linting issues for PR #{pr_num}\n\n"
                commit_message += "Automatically fixed linting failures detected in PR checks.\n\n"
                commit_message += "Changes:\n"
                for desc in changes_description:
                    commit_message += f"- {desc}\n"
                commit_message += f"\nFixed {len(changed_files)} file(s)"

                result = subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    print(f"  ⚠️ Commit failed: {result.stderr}")
                    return None

                # Get commit hash
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                commit_hash = result.stdout.strip()

                print(f"  ✅ Auto-fix committed: {commit_hash}")
                print(f"     Files changed: {len(changed_files)}")

                # Update Beads task if available
                if beads_id:
                    notes = f"Auto-fix implemented in branch {fix_branch}\n"
                    notes += f"Commit: {commit_hash}\n"
                    notes += f"Files changed: {len(changed_files)}"

                    subprocess.run(
                        ["beads", "update", beads_id, "--notes", notes],
                        check=False,
                        cwd=self.beads_dir,
                        capture_output=True,
                    )

                return {
                    "branch": fix_branch,
                    "changes": f"Fixed {len(changed_files)} file(s): "
                    + ", ".join(changed_files[:5])
                    + ("..." if len(changed_files) > 5 else ""),
                    "commit": commit_hash,
                    "notes": f"Auto-fix applied using: {', '.join(changes_description)}",
                }

            finally:
                # Always return to original directory
                os.chdir(original_dir)

        except subprocess.TimeoutExpired:
            print("  ⚠️ Fix command timed out")
            return None
        except Exception as e:
            print(f"  ⚠️ Auto-fix failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def create_beads_task(
        self, pr_num: int, repo_name: str, pr_context: dict, failed_checks: list[dict]
    ) -> str | None:
        """Create Beads task for the PR failure"""
        try:
            # Check if beads is available
            result = subprocess.run(["which", "beads"], check=False, capture_output=True)
            if result.returncode != 0:
                return None

            # Create task
            check_names = ", ".join([c["name"] for c in failed_checks])
            title = f"Fix PR #{pr_num} check failures: {check_names}"

            result = subprocess.run(
                [
                    "beads",
                    "add",
                    title,
                    "--tags",
                    f"pr-{pr_num}",
                    "ci-failure",
                    repo_name,
                    "urgent",
                ],
                check=False,
                cwd=self.beads_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Extract bead ID from output (usually first line)
                output = result.stdout.strip()
                # Output format: "Created bd-a3f8: Fix PR #123..."
                if "Created" in output and "bd-" in output:
                    bead_id = output.split("bd-")[1].split(":")[0]
                    bead_id = f"bd-{bead_id.split()[0]}"

                    # Add notes
                    notes = f"PR #{pr_num} in {repo_name}\n"
                    notes += f"Failed checks: {check_names}\n"
                    notes += f"URL: {pr_context.get('url', 'N/A')}\n"

                    subprocess.run(
                        ["beads", "update", bead_id, "--notes", notes],
                        check=False,
                        cwd=self.beads_dir,
                        capture_output=True,
                    )

                    print(f"  ✓ Created Beads task: {bead_id}")
                    return bead_id
        except Exception as e:
            print(f"  Could not create Beads task: {e}")

        return None

    def analyze_failure(self, pr_context: dict, failed_checks: list[dict]) -> dict:
        """Analyze failure and determine if auto-fix is possible"""
        analysis = {
            "summary": "",
            "root_cause": None,
            "actions": [],
            "can_auto_fix": False,
            "auto_fix_description": None,
        }

        # Simple heuristic analysis
        check_names = [c["name"].lower() for c in failed_checks]
        logs = [c.get("full_log", "") for c in failed_checks]
        combined_log = "\n".join(logs).lower()

        # Detect common failure patterns
        if any("pytest" in name or "test" in name for name in check_names):
            analysis["summary"] = "Test failures detected in PR checks."

            # Check for common test failure patterns
            if "importerror" in combined_log or "modulenotfounderror" in combined_log:
                analysis["root_cause"] = "Missing dependency or import error"
                analysis["actions"] = [
                    "Check requirements.txt or package.json for missing dependencies",
                    "Verify all imports are correct",
                    "Run tests locally to reproduce",
                ]
                analysis["can_auto_fix"] = False  # Need human judgment

            elif "assertion" in combined_log or "expected" in combined_log:
                analysis["root_cause"] = "Test assertion failure"
                analysis["actions"] = [
                    "Review the failing test to understand expectations",
                    "Check if PR changes broke test assumptions",
                    "Update test if expectations changed",
                ]
                analysis["can_auto_fix"] = False

            else:
                analysis["root_cause"] = "Test failure (cause unclear from logs)"
                analysis["actions"] = [
                    "Review full test output",
                    "Run tests locally",
                    "Check for recent changes that might affect tests",
                ]

        elif any("lint" in name or "eslint" in name or "pylint" in name for name in check_names):
            analysis["summary"] = "Code quality/linting failures detected."
            analysis["root_cause"] = "Code style or linting violations"
            analysis["actions"] = [
                "Run linter locally: eslint or pylint",
                "Auto-fix with: eslint --fix or black/autopep8",
                "Review and commit fixes",
            ]
            analysis["can_auto_fix"] = True
            analysis["auto_fix_description"] = "Run linter with --fix flag and commit changes"

        elif any("build" in name or "compile" in name for name in check_names):
            analysis["summary"] = "Build/compilation failures detected."
            analysis["root_cause"] = "Build errors"
            analysis["actions"] = [
                "Check build logs for specific errors",
                "Verify all dependencies are available",
                "Run build locally to reproduce",
            ]

        else:
            analysis["summary"] = f"{len(failed_checks)} check(s) failed in PR."
            analysis["actions"] = [
                "Review check logs for details",
                "Investigate each failed check individually",
                "Determine if failures are related to PR changes",
            ]

        return analysis


def main():
    """Main entry point"""
    watcher = GitHubWatcher()
    watcher.watch()


if __name__ == "__main__":
    main()
