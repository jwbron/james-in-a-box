#!/usr/bin/env python3
"""
Codebase Improvement Analyzer

Analyzes the james-in-a-box codebase for potential improvements using a SINGLE
Claude call, then optionally implements the top fixes and opens a PR.

Efficiency: Uses one Claude call to analyze all files at once, instead of
one call per file.

Usage:
  codebase-analyzer.py                    # Analyze and report
  codebase-analyzer.py --implement        # Analyze, fix top 10 issues, open PR
  codebase-analyzer.py --implement --max-fixes 5  # Fix top 5 issues
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
import subprocess
import fnmatch


class CodebaseAnalyzer:
    """Analyzes codebase for improvements using a single Claude Code call."""

    def __init__(self, codebase_path: Path, notification_dir: Path):
        self.codebase_path = codebase_path
        self.notification_dir = notification_dir
        self.logger = self._setup_logging()

        # Check for claude CLI
        if not self._check_claude_cli():
            self.logger.error("claude CLI not found in PATH")
            raise ValueError("claude command not available")

        # Load gitignore patterns
        self.gitignore_patterns = self._load_gitignore_patterns()
        self.always_ignore = {'.git', '__pycache__', 'node_modules', '.venv'}

    def _check_claude_cli(self) -> bool:
        """Check if claude CLI is available."""
        try:
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _setup_logging(self) -> logging.Logger:
        """Configure logging."""
        logger = logging.getLogger('codebase-analyzer')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            console.setFormatter(formatter)
            logger.addHandler(console)
        return logger

    def _load_gitignore_patterns(self) -> Set[str]:
        """Load and parse .gitignore file."""
        patterns = set()
        gitignore_path = self.codebase_path / '.gitignore'

        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.split('#')[0].strip()
                        if line:
                            patterns.add(line)
            except Exception as e:
                self.logger.warning(f"Error reading .gitignore: {e}")

        return patterns

    def _should_analyze(self, file_path: Path) -> bool:
        """Determine if file should be analyzed."""
        # Check always-ignore patterns
        for pattern in self.always_ignore:
            if pattern in str(file_path):
                return False

        # Only analyze specific file types
        valid_extensions = {'.py', '.sh', '.md', '.yml', '.yaml', '.json'}
        if file_path.suffix.lower() not in valid_extensions and file_path.name != 'Dockerfile':
            return False

        # Skip very large files (>50KB)
        try:
            if file_path.stat().st_size > 50_000:
                return False
        except OSError:
            return False

        return True

    def get_files_to_analyze(self) -> List[Path]:
        """Get list of files to analyze from codebase."""
        files = []
        for file_path in self.codebase_path.rglob('*'):
            if file_path.is_file() and self._should_analyze(file_path):
                files.append(file_path)

        self.logger.info(f"Found {len(files)} files to analyze")
        return files

    def build_codebase_summary(self, files: List[Path]) -> str:
        """Build a summary of the codebase for Claude to analyze."""
        summary_parts = []

        for file_path in files:
            try:
                rel_path = file_path.relative_to(self.codebase_path)
                content = file_path.read_text(encoding='utf-8', errors='ignore')

                # Truncate large files
                if len(content) > 3000:
                    content = content[:3000] + "\n... [truncated]"

                summary_parts.append(f"=== FILE: {rel_path} ===\n{content}\n")

            except Exception as e:
                self.logger.warning(f"Error reading {file_path}: {e}")

        return "\n".join(summary_parts)

    def analyze_codebase(self, files: List[Path]) -> List[Dict]:
        """Analyze entire codebase in a single Claude call."""
        self.logger.info("Building codebase summary...")
        codebase_summary = self.build_codebase_summary(files)

        self.logger.info(f"Codebase summary: {len(codebase_summary)} characters")

        prompt = f"""Analyze this codebase for issues that can be automatically fixed.

CODEBASE: james-in-a-box (Docker sandbox for Claude Code CLI)

{codebase_summary}

TASK: Identify the top 10-15 HIGH and MEDIUM priority issues that can be automatically fixed.

Focus on:
1. Bare except clauses (should use specific exceptions)
2. Missing error handling
3. Hardcoded paths that should be configurable
4. Code style issues (unused imports, inline imports)
5. Security issues (unquoted shell variables, etc.)
6. Outdated patterns

For each issue, provide:
- file: relative path to file
- line_hint: approximate line number or function name
- priority: HIGH or MEDIUM
- category: error_handling, security, maintainability, modern_practices
- description: what's wrong
- suggestion: specific fix to apply

Return as JSON array:
[
  {{
    "file": "path/to/file.py",
    "line_hint": "in function foo() around line 50",
    "priority": "HIGH",
    "category": "error_handling",
    "description": "Bare except clause catches all exceptions",
    "suggestion": "Replace 'except:' with 'except Exception as e:' and log the error"
  }}
]

Return ONLY the JSON array, no other text."""

        self.logger.info("Calling Claude for analysis (single call)...")

        try:
            result = subprocess.run(
                ['claude', '-p', prompt],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for large analysis
            )

            if result.returncode != 0:
                self.logger.error(f"Claude returned error: {result.stderr}")
                return []

            response = result.stdout.strip()

            # Extract JSON from response
            try:
                # Find JSON array in response
                start_idx = response.find('[')
                end_idx = response.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    issues = json.loads(json_str)
                    self.logger.info(f"Found {len(issues)} issues")
                    return issues
                else:
                    self.logger.warning("No JSON array found in response")
                    return []
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON: {e}")
                self.logger.debug(f"Response was: {response[:500]}")
                return []

        except subprocess.TimeoutExpired:
            self.logger.error("Claude call timed out")
            return []
        except Exception as e:
            self.logger.error(f"Error calling Claude: {e}")
            return []

    def implement_fix(self, issue: Dict) -> bool:
        """Implement a single fix using Claude Code."""
        file_path = self.codebase_path / issue['file']

        if not file_path.exists():
            self.logger.warning(f"File not found: {file_path}")
            return False

        try:
            content = file_path.read_text(encoding='utf-8')

            prompt = f"""Fix this issue in the file. Make ONLY the minimal change needed.

FILE: {issue['file']}
ISSUE: {issue['description']}
LOCATION: {issue.get('line_hint', 'unknown')}
SUGGESTION: {issue['suggestion']}

CURRENT FILE:
```
{content}
```

Return ONLY the complete fixed file content. No explanations, no markdown fences."""

            result = subprocess.run(
                ['claude', '-p', prompt],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                self.logger.error(f"Claude error for {issue['file']}: {result.stderr}")
                return False

            fixed_content = result.stdout.strip()

            # Remove markdown fences if present
            if fixed_content.startswith('```'):
                lines = fixed_content.split('\n')
                lines = lines[1:]  # Remove first line
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                fixed_content = '\n'.join(lines)

            # Validate the fix
            if len(fixed_content) < len(content) * 0.3:
                self.logger.warning(f"Fixed content too short for {issue['file']}, skipping")
                return False

            if len(fixed_content) > len(content) * 3:
                self.logger.warning(f"Fixed content too long for {issue['file']}, skipping")
                return False

            # Write the fix
            file_path.write_text(fixed_content, encoding='utf-8')
            self.logger.info(f"✓ Fixed: {issue['file']} ({issue['category']})")
            return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout fixing {issue['file']}")
            return False
        except Exception as e:
            self.logger.error(f"Error fixing {issue['file']}: {e}")
            return False

    def create_pr(self, implemented: List[Dict]) -> Optional[str]:
        """Commit changes and create a PR."""
        if not implemented:
            return None

        try:
            # Check for changes
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.codebase_path,
                capture_output=True,
                text=True
            )

            if not result.stdout.strip():
                self.logger.warning("No changes to commit")
                return None

            # Create branch
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"auto-fix/codebase-{timestamp}"

            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=self.codebase_path,
                check=True,
                capture_output=True
            )

            # Stage and commit
            subprocess.run(['git', 'add', '-A'], cwd=self.codebase_path, check=True, capture_output=True)

            categories = set(i['category'] for i in implemented)
            commit_msg = f"""Auto-fix: {len(implemented)} codebase improvements

Categories: {', '.join(categories)}

Fixes:
"""
            for issue in implemented:
                commit_msg += f"- {issue['file']}: {issue['description'][:50]}...\n"

            commit_msg += """
🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"""

            subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=self.codebase_path,
                check=True,
                capture_output=True
            )

            # Push
            result = subprocess.run(
                ['git', 'push', '-u', 'origin', branch_name],
                cwd=self.codebase_path,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.logger.error(f"Push failed: {result.stderr}")
                return None

            # Create PR
            pr_body = f"## Auto-fix: {len(implemented)} improvements\n\n"
            for cat in sorted(categories):
                cat_issues = [i for i in implemented if i['category'] == cat]
                pr_body += f"### {cat.title()} ({len(cat_issues)})\n"
                for i in cat_issues:
                    pr_body += f"- `{i['file']}`: {i['description'][:60]}\n"
                pr_body += "\n"

            pr_body += "\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"

            result = subprocess.run(
                ['gh', 'pr', 'create', '--base', 'main', '--head', branch_name,
                 '--title', f'Auto-fix: {len(implemented)} codebase improvements',
                 '--body', pr_body],
                cwd=self.codebase_path,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.logger.error(f"PR creation failed: {result.stderr}")
                return None

            pr_url = result.stdout.strip()
            self.logger.info(f"✓ Created PR: {pr_url}")
            return pr_url

        except Exception as e:
            self.logger.error(f"Error creating PR: {e}")
            return None

    def create_notification(self, issues: List[Dict], pr_url: Optional[str] = None):
        """Create a notification with findings."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notification_dir / f"{timestamp}-codebase-analysis.md"

        self.notification_dir.mkdir(parents=True, exist_ok=True)

        content = f"# 🔍 Codebase Analysis\n\n"
        content += f"**Found {len(issues)} issues**\n\n"

        if pr_url:
            content += f"**PR Created**: {pr_url}\n\n"

        # Group by priority
        high = [i for i in issues if i.get('priority') == 'HIGH']
        medium = [i for i in issues if i.get('priority') == 'MEDIUM']

        if high:
            content += "## 🔴 HIGH Priority\n\n"
            for i in high:
                content += f"- `{i['file']}`: {i['description']}\n"
            content += "\n"

        if medium:
            content += "## 🟡 MEDIUM Priority\n\n"
            for i in medium:
                content += f"- `{i['file']}`: {i['description']}\n"
            content += "\n"

        content += f"\n---\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        notif_file.write_text(content)
        self.logger.info(f"Notification: {notif_file}")

    def run(self, implement: bool = False, max_fixes: int = 10):
        """Main analysis workflow."""
        self.logger.info("=" * 60)
        self.logger.info("Codebase Analyzer")
        self.logger.info("=" * 60)

        # Get files
        files = self.get_files_to_analyze()

        # Analyze (single Claude call)
        issues = self.analyze_codebase(files)

        if not issues:
            self.logger.info("No issues found")
            return

        # Implement fixes if requested
        pr_url = None
        if implement:
            self.logger.info(f"\nImplementing top {max_fixes} fixes...")
            to_fix = issues[:max_fixes]
            implemented = []

            for issue in to_fix:
                if self.implement_fix(issue):
                    implemented.append(issue)

            self.logger.info(f"Implemented {len(implemented)}/{len(to_fix)} fixes")

            if implemented:
                pr_url = self.create_pr(implemented)

        # Create notification
        self.create_notification(issues, pr_url)

        self.logger.info("Done!")


def main():
    parser = argparse.ArgumentParser(description="Analyze codebase for improvements")
    parser.add_argument('--implement', action='store_true', help='Implement fixes and create PR')
    parser.add_argument('--max-fixes', type=int, default=10, help='Max fixes to implement')
    parser.add_argument('--force', action='store_true', help='Force run (ignored, kept for compatibility)')

    args = parser.parse_args()

    codebase_path = Path.home() / "khan" / "james-in-a-box"
    notification_dir = Path.home() / "sharing" / "notifications"

    if not codebase_path.exists():
        print(f"Error: {codebase_path} not found", file=sys.stderr)
        sys.exit(1)

    try:
        analyzer = CodebaseAnalyzer(codebase_path, notification_dir)
        analyzer.run(implement=args.implement, max_fixes=args.max_fixes)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
