#!/usr/bin/env python3
"""
PR Reviewer - Generates code reviews for GitHub pull requests

Analyzes PR diffs and metadata to provide comprehensive code reviews
covering code quality, security, performance, and best practices.
"""

import json
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class PRReviewer:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.prs_dir = self.github_dir / "prs"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.beads_dir = Path.home() / "beads"

        # Track which PRs have been reviewed
        self.state_file = Path.home() / "sharing" / "tracking" / "pr-reviewer-state.json"
        self.reviewed_prs = self.load_state()

    def load_state(self) -> dict:
        """Load previously reviewed PR IDs"""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {'reviewed': {}}

    def save_state(self):
        """Save reviewed PR IDs"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump(self.reviewed_prs, f, indent=2)

    def watch(self):
        """Scan for new PRs and review them"""
        if not self.prs_dir.exists():
            print("PRs directory not found - skipping review")
            return

        print("Scanning for new PRs to review...")

        # Get current user to skip self-reviews
        current_user = self.get_current_user()

        # Scan all PR files
        for pr_file in self.prs_dir.glob("*-PR-*.md"):
            try:
                # Extract PR number and repo from filename: repo-PR-123.md
                filename = pr_file.stem
                parts = filename.split('-PR-')
                if len(parts) != 2:
                    continue

                repo_name = parts[0]
                pr_num = int(parts[1])

                # Check if already reviewed
                review_key = f"{repo_name}-{pr_num}"
                if review_key in self.reviewed_prs.get('reviewed', {}):
                    continue

                # Load PR to check author
                pr_context = self.load_pr_metadata(pr_file)

                # Skip PRs authored by current user (don't self-review)
                if current_user and pr_context.get('author', '').lower() == current_user.lower():
                    print(f"  Skipping PR #{pr_num} (your own PR)")
                    continue

                print(f"  Reviewing new PR #{pr_num} in {repo_name}")

                # Generate review
                if self.review_pr(pr_num, repo_name):
                    # Mark as reviewed
                    self.reviewed_prs.setdefault('reviewed', {})[review_key] = {
                        'reviewed_at': datetime.now().isoformat(),
                        'pr_num': pr_num,
                        'repo': repo_name
                    }
                    self.save_state()

            except Exception as e:
                print(f"  Error processing {pr_file}: {e}")

    def get_current_user(self) -> str:
        """Get current GitHub user from gh CLI"""
        try:
            result = subprocess.run(
                ['gh', 'api', 'user', '--jq', '.login'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None

    def review_pr(self, pr_num: int, repo_name: str = None) -> bool:
        """Generate a comprehensive review for the specified PR"""
        print(f"Generating review for PR #{pr_num}")

        # Find PR file
        pr_file = None
        diff_file = None

        if repo_name:
            pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
            diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"
        else:
            # Search for PR file
            matches = list(self.prs_dir.glob(f"*-PR-{pr_num}.md"))
            if matches:
                pr_file = matches[0]
                repo_name = pr_file.name.split('-PR-')[0]
                diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        if not pr_file or not pr_file.exists():
            print(f"  ⚠️ PR #{pr_num} not found in synced data")
            return False

        # Load PR metadata
        pr_context = self.load_pr_metadata(pr_file)

        # Load diff
        if not diff_file or not diff_file.exists():
            print(f"  ⚠️ Diff file not found for PR #{pr_num}")
            return False

        with diff_file.open() as f:
            diff_content = f.read()

        # Parse diff into file changes
        file_changes = self.parse_diff(diff_content)

        # Generate review
        review = self.analyze_changes(pr_context, file_changes, diff_content)

        # Create Beads task for review
        beads_id = self.create_beads_task(pr_num, repo_name, pr_context)

        # Create notification
        self.create_review_notification(pr_num, repo_name, pr_context, review, beads_id)

        print(f"  ✅ Review generated for PR #{pr_num}")
        return True

    def load_pr_metadata(self, pr_file: Path) -> Dict:
        """Load PR metadata from markdown file"""
        with pr_file.open() as f:
            content = f.read()

        metadata = {
            'title': '',
            'description': '',
            'url': '',
            'branch': '',
            'author': '',
            'files_changed': [],
            'additions': 0,
            'deletions': 0
        }

        lines = content.split('\n')
        in_description = False

        for i, line in enumerate(lines):
            if line.startswith('# PR #'):
                metadata['title'] = line.split(': ', 1)[1] if ': ' in line else ''
            elif line.startswith('**URL**:'):
                metadata['url'] = line.split(':', 1)[1].strip()
            elif line.startswith('**Branch**:'):
                metadata['branch'] = line.split(':', 1)[1].strip()
            elif line.startswith('**Author**:'):
                metadata['author'] = line.split(':', 1)[1].strip()
            elif line.startswith('**Files Changed**:'):
                # Parse file changes count
                match = re.search(r'(\d+)', line)
                if match:
                    metadata['files_count'] = int(match.group(1))
            elif line.startswith('**Additions**:'):
                match = re.search(r'(\d+)', line)
                if match:
                    metadata['additions'] = int(match.group(1))
            elif line.startswith('**Deletions**:'):
                match = re.search(r'(\d+)', line)
                if match:
                    metadata['deletions'] = int(match.group(1))
            elif line.startswith('## Description'):
                in_description = True
            elif in_description and line.startswith('## '):
                in_description = False
            elif in_description and line.strip():
                metadata['description'] += line + '\n'

        return metadata

    def parse_diff(self, diff_content: str) -> List[Dict]:
        """Parse diff content into structured file changes"""
        file_changes = []
        current_file = None

        for line in diff_content.split('\n'):
            if line.startswith('diff --git'):
                # New file
                if current_file:
                    file_changes.append(current_file)

                # Extract file path
                match = re.search(r'b/(.+)$', line)
                file_path = match.group(1) if match else 'unknown'

                current_file = {
                    'path': file_path,
                    'additions': 0,
                    'deletions': 0,
                    'chunks': [],
                    'language': self.detect_language(file_path)
                }

            elif current_file:
                if line.startswith('@@'):
                    # New chunk
                    current_file['chunks'].append({
                        'header': line,
                        'lines': []
                    })
                elif line.startswith('+') and not line.startswith('+++'):
                    current_file['additions'] += 1
                    if current_file['chunks']:
                        current_file['chunks'][-1]['lines'].append(line)
                elif line.startswith('-') and not line.startswith('---'):
                    current_file['deletions'] += 1
                    if current_file['chunks']:
                        current_file['chunks'][-1]['lines'].append(line)
                elif current_file['chunks']:
                    current_file['chunks'][-1]['lines'].append(line)

        if current_file:
            file_changes.append(current_file)

        return file_changes

    def detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        ext_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
            '.rs': 'rust',
            '.sh': 'bash',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.md': 'markdown',
        }

        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, 'unknown')

    def analyze_changes(self, pr_context: Dict, file_changes: List[Dict], diff_content: str) -> Dict:
        """Analyze code changes and generate review"""
        review = {
            'overall_assessment': '',
            'concerns': [],
            'suggestions': [],
            'security_issues': [],
            'performance_issues': [],
            'file_reviews': [],
            'testing_gaps': [],
            'positive_notes': []
        }

        # Overall assessment
        total_additions = pr_context.get('additions', 0)
        total_deletions = pr_context.get('deletions', 0)
        net_change = total_additions - total_deletions

        if net_change > 500:
            review['overall_assessment'] = "Large PR with significant code changes. Consider breaking into smaller PRs for easier review."
            review['concerns'].append("PR size is large - may be difficult to review thoroughly")
        elif net_change > 200:
            review['overall_assessment'] = "Medium-sized PR with moderate changes."
        else:
            review['overall_assessment'] = "Small, focused PR - good size for review."
            review['positive_notes'].append("PR is well-scoped and focused")

        # Analyze each file
        for file_change in file_changes:
            file_review = self.analyze_file(file_change, diff_content)
            if file_review['comments']:
                review['file_reviews'].append(file_review)

            # Collect specific issue types
            for comment in file_review['comments']:
                if comment['type'] == 'security':
                    review['security_issues'].append({
                        'file': file_change['path'],
                        'concern': comment['text']
                    })
                elif comment['type'] == 'performance':
                    review['performance_issues'].append({
                        'file': file_change['path'],
                        'concern': comment['text']
                    })

        # Check for testing
        has_test_files = any('test' in f['path'].lower() for f in file_changes)
        has_code_changes = any(f['language'] in ['python', 'javascript', 'typescript', 'java', 'go']
                               for f in file_changes
                               if 'test' not in f['path'].lower())

        if has_code_changes and not has_test_files:
            review['testing_gaps'].append("No test files found - consider adding tests for new functionality")

        # Overall suggestions
        if not review['security_issues'] and not review['performance_issues']:
            review['positive_notes'].append("No obvious security or performance concerns detected")

        return review

    def analyze_file(self, file_change: Dict, full_diff: str) -> Dict:
        """Analyze a single file change"""
        file_review = {
            'path': file_change['path'],
            'language': file_change['language'],
            'comments': []
        }

        # Get added lines for analysis
        added_lines = []
        for chunk in file_change['chunks']:
            for line in chunk['lines']:
                if line.startswith('+') and not line.startswith('+++'):
                    added_lines.append(line[1:])  # Remove + prefix

        added_code = '\n'.join(added_lines)

        # Pattern-based analysis
        patterns = self.get_analysis_patterns(file_change['language'])

        for pattern_name, pattern_config in patterns.items():
            regex = pattern_config['regex']
            matches = re.finditer(regex, added_code, re.MULTILINE | re.IGNORECASE)

            for match in matches:
                file_review['comments'].append({
                    'type': pattern_config['type'],
                    'severity': pattern_config['severity'],
                    'text': pattern_config['message'],
                    'context': match.group(0)[:100]
                })

        return file_review

    def get_analysis_patterns(self, language: str) -> Dict:
        """Get code analysis patterns for specific language"""
        # Common patterns across languages
        common_patterns = {
            'console_log': {
                'regex': r'console\.(log|debug|info|warn|error)',
                'type': 'quality',
                'severity': 'low',
                'message': 'Console log statement found - consider removing debug logs before merge'
            },
            'todo_comment': {
                'regex': r'(TODO|FIXME|HACK|XXX):',
                'type': 'quality',
                'severity': 'low',
                'message': 'TODO/FIXME comment found - consider addressing or creating a ticket'
            },
            'hardcoded_url': {
                'regex': r'https?://(?!localhost|127\.0\.0\.1|example\.com)[^\s\'"]+',
                'type': 'quality',
                'severity': 'medium',
                'message': 'Hardcoded URL found - consider using configuration'
            },
        }

        # Python-specific patterns
        python_patterns = {
            'eval_exec': {
                'regex': r'\b(eval|exec)\s*\(',
                'type': 'security',
                'severity': 'high',
                'message': 'Use of eval/exec detected - potential security risk'
            },
            'sql_string_concat': {
                'regex': r'(SELECT|INSERT|UPDATE|DELETE).*\+.*\+',
                'type': 'security',
                'severity': 'high',
                'message': 'Possible SQL injection risk - use parameterized queries'
            },
            'bare_except': {
                'regex': r'except\s*:',
                'type': 'quality',
                'severity': 'medium',
                'message': 'Bare except clause - specify exception types'
            },
            'print_statement': {
                'regex': r'\bprint\s*\(',
                'type': 'quality',
                'severity': 'low',
                'message': 'Print statement found - use logging instead'
            },
        }

        # JavaScript/TypeScript patterns
        js_patterns = {
            'var_keyword': {
                'regex': r'\bvar\s+\w+',
                'type': 'quality',
                'severity': 'low',
                'message': 'Use of var keyword - prefer const or let'
            },
            'double_equals': {
                'regex': r'[^=!]={2}[^=]',
                'type': 'quality',
                'severity': 'medium',
                'message': 'Use of == operator - prefer === for strict equality'
            },
            'dangerouslySetInnerHTML': {
                'regex': r'dangerouslySetInnerHTML',
                'type': 'security',
                'severity': 'high',
                'message': 'dangerouslySetInnerHTML used - ensure HTML is sanitized to prevent XSS'
            },
        }

        if language == 'python':
            return {**common_patterns, **python_patterns}
        elif language in ['javascript', 'typescript']:
            return {**common_patterns, **js_patterns}
        else:
            return common_patterns

    def create_beads_task(self, pr_num: int, repo_name: str, pr_context: Dict) -> Optional[str]:
        """Create Beads task for PR review"""
        try:
            result = subprocess.run(['which', 'beads'], capture_output=True)
            if result.returncode != 0:
                return None

            title = f"Review PR #{pr_num}: {pr_context.get('title', 'PR Review')}"

            result = subprocess.run(
                ['beads', 'add', title, '--tags', f'pr-{pr_num}', 'review', repo_name],
                cwd=self.beads_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if 'Created' in output and 'bd-' in output:
                    bead_id = output.split('bd-')[1].split(':')[0]
                    bead_id = f"bd-{bead_id.split()[0]}"

                    notes = f"PR #{pr_num} in {repo_name}\n"
                    notes += f"Review generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    notes += f"URL: {pr_context.get('url', 'N/A')}"

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

    def create_review_notification(self, pr_num: int, repo_name: str, pr_context: Dict,
                                   review: Dict, beads_id: Optional[str]):
        """Create notification file with review results"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notifications_dir / f"{timestamp}-pr-review-{pr_num}.md"

        with notif_file.open('w') as f:
            f.write(f"# 📝 PR Review: #{pr_num}\n\n")
            f.write(f"**PR**: {pr_context['title']}\n")
            f.write(f"**Repository**: {repo_name}\n")
            f.write(f"**URL**: {pr_context.get('url', 'N/A')}\n")
            f.write(f"**Branch**: {pr_context.get('branch', 'N/A')}\n")
            f.write(f"**Changes**: +{pr_context.get('additions', 0)} -{pr_context.get('deletions', 0)}\n")
            if beads_id:
                f.write(f"**Beads Task**: {beads_id}\n")
            f.write("\n")

            # Overall assessment
            f.write("## 📊 Overall Assessment\n\n")
            f.write(f"{review['overall_assessment']}\n\n")

            # Positive notes
            if review['positive_notes']:
                f.write("### ✅ Positive Notes\n\n")
                for note in review['positive_notes']:
                    f.write(f"- {note}\n")
                f.write("\n")

            # Security issues
            if review['security_issues']:
                f.write("## 🔒 Security Concerns\n\n")
                for issue in review['security_issues']:
                    f.write(f"**{issue['file']}**\n")
                    f.write(f"- ⚠️ {issue['concern']}\n\n")

            # Performance issues
            if review['performance_issues']:
                f.write("## ⚡ Performance Concerns\n\n")
                for issue in review['performance_issues']:
                    f.write(f"**{issue['file']}**\n")
                    f.write(f"- {issue['concern']}\n\n")

            # Testing gaps
            if review['testing_gaps']:
                f.write("## 🧪 Testing Gaps\n\n")
                for gap in review['testing_gaps']:
                    f.write(f"- {gap}\n")
                f.write("\n")

            # File-by-file review
            if review['file_reviews']:
                f.write("## 📁 File-by-File Review\n\n")
                for file_review in review['file_reviews']:
                    f.write(f"### `{file_review['path']}`\n\n")

                    # Group comments by severity
                    high_comments = [c for c in file_review['comments'] if c['severity'] == 'high']
                    medium_comments = [c for c in file_review['comments'] if c['severity'] == 'medium']
                    low_comments = [c for c in file_review['comments'] if c['severity'] == 'low']

                    if high_comments:
                        f.write("**High Priority:**\n")
                        for comment in high_comments:
                            f.write(f"- 🔴 {comment['text']}\n")
                        f.write("\n")

                    if medium_comments:
                        f.write("**Medium Priority:**\n")
                        for comment in medium_comments:
                            f.write(f"- 🟡 {comment['text']}\n")
                        f.write("\n")

                    if low_comments:
                        f.write("**Low Priority:**\n")
                        for comment in low_comments:
                            f.write(f"- 🔵 {comment['text']}\n")
                        f.write("\n")

            # Summary
            f.write("## 📋 Review Summary\n\n")

            total_issues = (len(review['security_issues']) +
                          len(review['performance_issues']) +
                          len(review['testing_gaps']))

            if total_issues == 0:
                f.write("✅ No major issues found. Code looks good!\n\n")
            else:
                f.write(f"Found {total_issues} area(s) that may need attention:\n")
                if review['security_issues']:
                    f.write(f"- {len(review['security_issues'])} security concern(s)\n")
                if review['performance_issues']:
                    f.write(f"- {len(review['performance_issues'])} performance concern(s)\n")
                if review['testing_gaps']:
                    f.write(f"- {len(review['testing_gaps'])} testing gap(s)\n")
                f.write("\n")

            f.write("**Next Steps:**\n")
            f.write("1. Address high-priority issues before merge\n")
            f.write("2. Consider medium-priority suggestions for code quality\n")
            f.write("3. Low-priority items can be addressed in follow-up PRs\n")
            f.write("\n")

            f.write("---\n")
            f.write(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"🤖 Generated by jib PR Reviewer\n")

        print(f"  ✓ Created review notification: {notif_file.name}")


def main():
    """Main entry point for PR review"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Generate code reviews for GitHub PRs")
    parser.add_argument("pr_number", nargs="?", type=int, help="PR number to review")
    parser.add_argument("repo_name", nargs="?", help="Repository name (optional)")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Scan for new PRs and review them (excludes own PRs)")

    args = parser.parse_args()

    reviewer = PRReviewer()

    if args.watch:
        # Watch mode: scan for new PRs to review
        reviewer.watch()
        sys.exit(0)
    elif args.pr_number:
        # Direct PR review
        success = reviewer.review_pr(args.pr_number, args.repo_name)
        sys.exit(0 if success else 1)
    else:
        # Default: run in watch mode
        reviewer.watch()
        sys.exit(0)


if __name__ == '__main__':
    main()
