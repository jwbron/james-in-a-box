#!/usr/bin/env python3
"""
GitHub PR Check Fixer - Automatically fixes common PR check failures

Triggered by github-sync.service after syncing PR data.
Analyzes failed checks and implements fixes automatically when possible.
"""

import json
import subprocess
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Add shared path for notifications library
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "jib-container" / "shared"))
try:
    from notifications import slack_notify, NotificationContext
    HAS_NOTIFICATIONS = True
except ImportError:
    HAS_NOTIFICATIONS = False


class CheckFixer:
    """Analyzes and fixes PR check failures automatically."""

    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.checks_dir = self.github_dir / "checks"
        self.prs_dir = self.github_dir / "prs"
        self.khan_dir = Path.home() / "khan"
        self.state_file = Path.home() / "sharing" / "tracking" / "check-fixer-state.json"
        self.state = self.load_state()

    def load_state(self) -> Dict:
        """Load previous state."""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except Exception:
                pass
        return {"handled_failures": {}, "fixes_applied": [], "needs_attention": []}

    def save_state(self):
        """Save state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump(self.state, f, indent=2)

    def run_cmd(self, args: List[str], cwd: Path, check: bool = False, timeout: int = 300) -> subprocess.CompletedProcess:
        """Run a command."""
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

    def run_git(self, args: List[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
        """Run a git command."""
        return self.run_cmd(["git"] + args, cwd, check)

    def run_gh(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run a gh CLI command."""
        return subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            check=False,
        )

    def categorize_failure(self, check: Dict) -> Tuple[str, bool]:
        """
        Categorize a check failure and determine if it's auto-fixable.
        Returns (category, is_auto_fixable).
        """
        name = check.get("name", "").lower()
        log = check.get("full_log", "").lower()

        # Linting failures - usually auto-fixable
        if any(x in name for x in ["lint", "eslint", "prettier", "ruff", "black", "pylint", "flake8"]):
            return "lint", True

        # Formatting failures - usually auto-fixable
        if any(x in name for x in ["format", "fmt"]):
            return "format", True

        # Type checking failures - sometimes auto-fixable
        if any(x in name for x in ["typecheck", "mypy", "pyright", "tsc", "typescript"]):
            # Only auto-fixable for simple type issues
            if "missing return type" in log or "unused import" in log:
                return "types", True
            return "types", False

        # Test failures - rarely auto-fixable
        if any(x in name for x in ["test", "pytest", "jest", "unittest"]):
            # Check for snapshot update requests
            if "snapshot" in log and ("update" in log or "outdated" in log):
                return "snapshot", True
            return "test", False

        # Build failures - sometimes auto-fixable
        if any(x in name for x in ["build", "compile"]):
            # Check for dependency issues
            if "module not found" in log or "cannot find module" in log:
                return "dependency", True
            return "build", False

        # Security checks
        if any(x in name for x in ["security", "cve", "vulnerability", "audit"]):
            return "security", False

        return "unknown", False

    def get_pr_info(self, repo: str, pr_num: int) -> Optional[Dict]:
        """Get PR info from synced files."""
        repo_name = repo.split("/")[-1]
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"

        if not pr_file.exists():
            return None

        try:
            content = pr_file.read_text()
            info = {
                "pr_number": pr_num,
                "repository": repo,
                "head_branch": None,
                "base_branch": None,
                "url": None,
                "title": None,
            }

            for line in content.split("\n"):
                if line.startswith("# PR #") and ":" in line:
                    info["title"] = line.split(":", 1)[1].strip()
                elif line.startswith("**Branch**:"):
                    branch_info = line.replace("**Branch**:", "").strip()
                    if " → " in branch_info:
                        head, base = branch_info.split(" → ", 1)
                        info["head_branch"] = head.strip()
                        info["base_branch"] = base.strip()
                elif line.startswith("**URL**:"):
                    info["url"] = line.replace("**URL**:", "").strip()

            return info
        except Exception:
            return None

    def apply_lint_fix(self, repo_path: Path, check: Dict) -> Tuple[bool, str, List[str]]:
        """Apply linting fixes."""
        name = check.get("name", "").lower()
        files_fixed = []

        try:
            # Detect linter type and run appropriate fix
            if "eslint" in name or "javascript" in name or "typescript" in name:
                # ESLint fix
                result = self.run_cmd(
                    ["npx", "eslint", ".", "--fix", "--max-warnings", "0"],
                    cwd=repo_path,
                    timeout=120,
                )
                if "problem" in result.stdout.lower() or result.returncode == 0:
                    files_fixed = self._get_changed_files(repo_path)

            elif "prettier" in name:
                # Prettier fix
                result = self.run_cmd(
                    ["npx", "prettier", "--write", "."],
                    cwd=repo_path,
                    timeout=120,
                )
                files_fixed = self._get_changed_files(repo_path)

            elif any(x in name for x in ["ruff", "python", "black", "flake8"]):
                # Python linting - try ruff first, then black
                result = self.run_cmd(["ruff", "check", "--fix", "."], cwd=repo_path, timeout=120)
                result2 = self.run_cmd(["ruff", "format", "."], cwd=repo_path, timeout=120)
                files_fixed = self._get_changed_files(repo_path)

                if not files_fixed:
                    # Fallback to black
                    self.run_cmd(["black", "."], cwd=repo_path, timeout=120)
                    files_fixed = self._get_changed_files(repo_path)

            else:
                # Generic: try multiple linters
                for cmd in [
                    ["npx", "eslint", ".", "--fix"],
                    ["npx", "prettier", "--write", "."],
                    ["ruff", "check", "--fix", "."],
                    ["ruff", "format", "."],
                    ["black", "."],
                ]:
                    try:
                        self.run_cmd(cmd, cwd=repo_path, timeout=60)
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue

                files_fixed = self._get_changed_files(repo_path)

            if files_fixed:
                return True, f"Fixed {len(files_fixed)} file(s)", files_fixed
            return False, "No changes after running linters", []

        except Exception as e:
            return False, f"Error: {e}", []

    def apply_format_fix(self, repo_path: Path, check: Dict) -> Tuple[bool, str, List[str]]:
        """Apply formatting fixes."""
        try:
            # Try various formatters
            for cmd in [
                ["npx", "prettier", "--write", "."],
                ["ruff", "format", "."],
                ["black", "."],
                ["go", "fmt", "./..."],
            ]:
                try:
                    self.run_cmd(cmd, cwd=repo_path, timeout=120)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

            files_fixed = self._get_changed_files(repo_path)
            if files_fixed:
                return True, f"Formatted {len(files_fixed)} file(s)", files_fixed
            return False, "No formatting changes needed", []

        except Exception as e:
            return False, f"Error: {e}", []

    def apply_dependency_fix(self, repo_path: Path, check: Dict) -> Tuple[bool, str, List[str]]:
        """Fix dependency issues."""
        log = check.get("full_log", "")
        files_fixed = []

        try:
            # Check for package.json
            if (repo_path / "package.json").exists():
                # Try npm install
                result = self.run_cmd(["npm", "install"], cwd=repo_path, timeout=300)
                if result.returncode == 0:
                    files_fixed = self._get_changed_files(repo_path)
                    if files_fixed:
                        return True, "Ran npm install to fix dependencies", files_fixed

            # Check for requirements.txt
            if (repo_path / "requirements.txt").exists():
                result = self.run_cmd(["pip", "install", "-r", "requirements.txt"], cwd=repo_path, timeout=300)
                # dependencies don't change files, but may fix the issue

            # Check for pyproject.toml
            if (repo_path / "pyproject.toml").exists():
                # Try uv or pip
                self.run_cmd(["uv", "sync"], cwd=repo_path, timeout=300)
                self.run_cmd(["pip", "install", "-e", "."], cwd=repo_path, timeout=300)

            return False, "Installed dependencies (no file changes)", []

        except Exception as e:
            return False, f"Error: {e}", []

    def apply_snapshot_fix(self, repo_path: Path, check: Dict) -> Tuple[bool, str, List[str]]:
        """Update test snapshots."""
        try:
            # Try updating Jest snapshots
            if (repo_path / "package.json").exists():
                result = self.run_cmd(
                    ["npx", "jest", "--updateSnapshot"],
                    cwd=repo_path,
                    timeout=300,
                )
                files_fixed = self._get_changed_files(repo_path)
                if files_fixed:
                    return True, f"Updated {len(files_fixed)} snapshot(s)", files_fixed

            # Try updating pytest snapshots
            result = self.run_cmd(
                ["pytest", "--snapshot-update"],
                cwd=repo_path,
                timeout=300,
            )
            files_fixed = self._get_changed_files(repo_path)
            if files_fixed:
                return True, f"Updated {len(files_fixed)} snapshot(s)", files_fixed

            return False, "No snapshot updates needed", []

        except Exception as e:
            return False, f"Error: {e}", []

    def _get_changed_files(self, repo_path: Path) -> List[str]:
        """Get list of changed files in repo."""
        result = self.run_git(["diff", "--name-only"], cwd=repo_path)
        if result.returncode == 0 and result.stdout.strip():
            return [f for f in result.stdout.strip().split("\n") if f]
        return []

    def apply_fix(self, repo_path: Path, pr_info: Dict, check: Dict, category: str) -> Tuple[bool, str, Optional[str]]:
        """
        Apply a fix for a failed check.
        Returns (success, message, commit_hash).
        """
        head_branch = pr_info["head_branch"]
        pr_num = pr_info["pr_number"]

        try:
            # Fetch and checkout PR branch
            self.run_git(["fetch", "origin"], cwd=repo_path)
            result = self.run_git(["checkout", head_branch], cwd=repo_path)
            if result.returncode != 0:
                result = self.run_git(
                    ["checkout", "-b", head_branch, f"origin/{head_branch}"],
                    cwd=repo_path,
                )
                if result.returncode != 0:
                    return False, f"Could not checkout {head_branch}", None

            # Pull latest
            self.run_git(["pull", "--ff-only"], cwd=repo_path)

            # Apply fix based on category
            fix_methods = {
                "lint": self.apply_lint_fix,
                "format": self.apply_format_fix,
                "dependency": self.apply_dependency_fix,
                "snapshot": self.apply_snapshot_fix,
            }

            if category not in fix_methods:
                return False, f"No auto-fix available for category: {category}", None

            success, message, files_fixed = fix_methods[category](repo_path, check)

            if not success or not files_fixed:
                return False, message, None

            # Stage and commit changes
            self.run_git(["add", "-A"], cwd=repo_path)

            commit_msg = f"""Auto-fix {category} issues for PR #{pr_num}

{message}

Files changed:
{chr(10).join('- ' + f for f in files_fixed[:10])}
{f'... and {len(files_fixed) - 10} more' if len(files_fixed) > 10 else ''}

--- Authored by jib"""

            result = self.run_git(["commit", "-m", commit_msg], cwd=repo_path)
            if result.returncode != 0:
                return False, f"Commit failed: {result.stderr}", None

            # Get commit hash
            hash_result = self.run_git(["rev-parse", "--short", "HEAD"], cwd=repo_path)
            commit_hash = hash_result.stdout.strip()

            # Push changes
            push_result = self.run_git(["push", "origin", head_branch], cwd=repo_path)
            if push_result.returncode != 0:
                return False, f"Push failed: {push_result.stderr}", commit_hash

            return True, message, commit_hash

        except Exception as e:
            # Cleanup
            self.run_git(["checkout", "."], cwd=repo_path)
            self.run_git(["clean", "-fd"], cwd=repo_path)
            return False, f"Error: {e}", None

    def notify(self, title: str, message: str, pr_info: Dict, success: bool = True):
        """Send notification."""
        if HAS_NOTIFICATIONS:
            ctx = NotificationContext(
                task_id=f"check-fix-pr-{pr_info['pr_number']}",
                repository=pr_info["repository"],
            )
            emoji = ":white_check_mark:" if success else ":warning:"
            slack_notify(f"{emoji} {title}", message, context=ctx)
        else:
            # Fallback to file-based notification
            notifications_dir = Path.home() / "sharing" / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            notif_file = notifications_dir / f"{timestamp}-check-fix-{pr_info['pr_number']}.md"

            with notif_file.open("w") as f:
                f.write(f"# {title}\n\n")
                f.write(message)
                f.write(f"\n\n---\n{datetime.now().isoformat()}\n")

    def process_check_file(self, check_file: Path):
        """Process a check file and attempt to fix failures."""
        try:
            with check_file.open() as f:
                data = json.load(f)

            pr_num = data["pr_number"]
            repo = data["repository"]
            checks = data.get("checks", [])

            # Find failed checks
            # Note: gh pr checks uses 'state' with values like 'FAILURE', 'SUCCESS', etc.
            failed_checks = [
                c for c in checks
                if c.get("state", "").upper() in ("FAILURE", "FAILED")
                or c.get("conclusion", "").lower() == "failure"
            ]

            if not failed_checks:
                return

            # Check if we already handled these specific failures
            failure_key = f"{repo}#{pr_num}:" + ",".join(sorted(c.get("name", "") for c in failed_checks))
            if failure_key in self.state["handled_failures"]:
                last_handled = self.state["handled_failures"][failure_key]
                last_time = datetime.fromisoformat(last_handled.replace("Z", "+00:00"))
                # Re-check if more than 30 minutes passed
                if (datetime.now(last_time.tzinfo) - last_time).total_seconds() < 1800:
                    return

            print(f"\nProcessing PR #{pr_num} ({repo}) - {len(failed_checks)} failed check(s)")

            # Get PR info
            pr_info = self.get_pr_info(repo, pr_num)
            if not pr_info:
                print(f"  Could not load PR info")
                return

            repo_name = repo.split("/")[-1]
            repo_path = self.khan_dir / repo_name

            if not repo_path.exists():
                print(f"  Repository not found: {repo_path}")
                return

            # Process each failed check
            fixes_applied = []
            needs_attention = []

            for check in failed_checks:
                check_name = check.get("name", "unknown")
                category, can_fix = self.categorize_failure(check)

                print(f"  Check: {check_name} ({category}, auto-fix: {can_fix})")

                if not can_fix:
                    needs_attention.append({
                        "check": check_name,
                        "category": category,
                        "reason": "Auto-fix not available for this failure type",
                    })
                    continue

                # Attempt fix
                success, message, commit_hash = self.apply_fix(repo_path, pr_info, check, category)

                if success:
                    print(f"    Fixed: {message} (commit: {commit_hash})")
                    fixes_applied.append({
                        "check": check_name,
                        "category": category,
                        "message": message,
                        "commit": commit_hash,
                    })

                    # Comment on PR
                    comment = f"""## :robot: Auto-fix Applied: {check_name}

I detected a failing `{check_name}` check and automatically fixed it.

**Category**: {category}
**Fix**: {message}
**Commit**: `{commit_hash}`

The fix has been pushed to this PR. Please review the changes.

--- Authored by jib"""

                    self.run_gh([
                        "pr", "comment", str(pr_num),
                        "--repo", repo,
                        "--body", comment,
                    ])
                else:
                    print(f"    Could not fix: {message}")
                    needs_attention.append({
                        "check": check_name,
                        "category": category,
                        "reason": message,
                    })

            # Update state
            self.state["handled_failures"][failure_key] = datetime.utcnow().isoformat() + "Z"
            self.state["fixes_applied"].extend(fixes_applied)
            self.state["needs_attention"].extend(needs_attention)
            self.save_state()

            # Send summary notification
            if fixes_applied or needs_attention:
                summary_parts = []
                if fixes_applied:
                    summary_parts.append(f"**Fixed ({len(fixes_applied)}):**\n" + "\n".join(
                        f"- {f['check']}: {f['message']}" for f in fixes_applied
                    ))
                if needs_attention:
                    summary_parts.append(f"**Needs Attention ({len(needs_attention)}):**\n" + "\n".join(
                        f"- {n['check']}: {n['reason']}" for n in needs_attention
                    ))

                self.notify(
                    f"PR Check Fixes: #{pr_num}",
                    f"**PR**: {pr_info.get('title', f'#{pr_num}')}\n**Repository**: {repo}\n\n" + "\n\n".join(summary_parts),
                    pr_info,
                    success=len(needs_attention) == 0,
                )

        except Exception as e:
            print(f"Error processing {check_file.name}: {e}")

    def run(self):
        """Main entry point."""
        print("GitHub PR Check Fixer - Analyzing and fixing check failures...")

        if not self.checks_dir.exists():
            print("No checks directory found, skipping")
            return 0

        check_files = list(self.checks_dir.glob("*-PR-*-checks.json"))
        if not check_files:
            print("No check files found")
            return 0

        print(f"Found {len(check_files)} PR check file(s)")

        for check_file in check_files:
            try:
                self.process_check_file(check_file)
            except Exception as e:
                print(f"Error processing {check_file.name}: {e}")
                continue

        # Summary
        fixes = len(self.state.get("fixes_applied", []))
        attention = len(self.state.get("needs_attention", []))
        print(f"\nCheck fixer summary: {fixes} fixes applied, {attention} need attention")

        return 0


def main():
    """Main entry point."""
    fixer = CheckFixer()
    return fixer.run()


if __name__ == "__main__":
    sys.exit(main())
