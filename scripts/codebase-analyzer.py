#!/usr/bin/env python3
"""
Codebase Improvement Analyzer

Analyzes the cursor-sandboxed codebase for potential improvements:
- File-by-file code review for best practices
- Web search for new technologies and improvements
- Generates notification with findings

Uses 'claude code --print' for analysis (reuses existing authentication)

Runs on host (not in sandbox) via systemd timer:
- Weekly (checks if last run was >7 days ago)
- 5 minutes after system startup (if not run in last week)
- Can force run with --force flag
"""

import os
import sys
import json
import logging
import tempfile
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import subprocess

# Only requests is required
try:
    import requests
except ImportError:
    print("Error: requests module not found.", file=sys.stderr)
    print("Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class CodebaseAnalyzer:
    """Analyzes codebase for improvements using Claude Code CLI."""

    def __init__(self, codebase_path: Path, notification_dir: Path):
        self.codebase_path = codebase_path
        self.notification_dir = notification_dir
        self.logger = self._setup_logging()

        # Check for claude CLI
        if not self._check_claude_cli():
            self.logger.error("claude CLI not found in PATH")
            raise ValueError("claude command not available")

        # Files to analyze (ignore certain patterns)
        self.ignore_patterns = {
            '__pycache__',
            '.git',
            '.pyc',
            'node_modules',
            '.log',
        }

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

        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console.setFormatter(formatter)
        logger.addHandler(console)

        return logger

    def should_analyze_file(self, file_path: Path) -> bool:
        """Determine if file should be analyzed."""
        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if pattern in str(file_path):
                return False

        # Only analyze specific file types
        valid_extensions = {'.py', '.sh', '.md', '.dockerfile', '.yml', '.yaml', '.json'}
        if file_path.suffix.lower() not in valid_extensions and file_path.name != 'Dockerfile':
            return False

        # Skip very large files (>100KB)
        try:
            if file_path.stat().st_size > 100_000:
                return False
        except:
            return False

        return True

    def get_files_to_analyze(self) -> List[Path]:
        """Get list of files to analyze from codebase."""
        files = []
        for file_path in self.codebase_path.rglob('*'):
            if file_path.is_file() and self.should_analyze_file(file_path):
                files.append(file_path)

        self.logger.info(f"Found {len(files)} files to analyze")
        return files

    def call_claude(self, prompt: str) -> str:
        """Call Claude Code CLI with a prompt."""
        try:
            # Call claude code --print with prompt via stdin
            result = subprocess.run(
                ['claude', 'code', '--print'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return result.stdout
            else:
                self.logger.warning(f"Claude returned error: {result.stderr}")
                return ""

        except subprocess.TimeoutExpired:
            self.logger.error("Claude call timed out")
            return ""
        except Exception as e:
            self.logger.error(f"Error calling Claude: {e}")
            return ""

    def analyze_file(self, file_path: Path) -> Optional[Dict]:
        """Analyze a single file for improvements."""
        try:
            # Read file content
            content = file_path.read_text(encoding='utf-8', errors='ignore')

            # Skip empty or very small files
            if len(content.strip()) < 50:
                return None

            relative_path = file_path.relative_to(self.codebase_path)

            # Build analysis prompt
            prompt = f"""Analyze this file from the cursor-sandboxed codebase for potential improvements.

File: {relative_path}
Language: {file_path.suffix}

Focus on:
1. Security vulnerabilities or concerns
2. Performance optimizations
3. Code maintainability and readability
4. Missing or inadequate error handling
5. Documentation gaps
6. Modern best practices not being followed

Content:
```
{content[:4000]}
```

Provide a concise analysis. Only report HIGH and MEDIUM priority issues.
Format as JSON:
{{
  "has_issues": true/false,
  "issues": [
    {{
      "priority": "HIGH" or "MEDIUM",
      "category": "security|performance|maintainability|documentation|error_handling|modern_practices",
      "description": "brief description",
      "suggestion": "specific recommendation"
    }}
  ]
}}

If no significant issues found, return {{"has_issues": false, "issues": []}}"""

            response_text = self.call_claude(prompt)

            if not response_text:
                return None

            # Try to extract JSON from response
            try:
                # Find JSON in response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    analysis = json.loads(json_str)
                else:
                    analysis = {"has_issues": False, "issues": []}
            except json.JSONDecodeError:
                self.logger.warning(f"Could not parse JSON from response for {relative_path}")
                analysis = {"has_issues": False, "issues": []}

            if analysis.get('has_issues'):
                return {
                    'file': str(relative_path),
                    'analysis': analysis
                }

            return None

        except Exception as e:
            self.logger.error(f"Error analyzing {file_path}: {e}")
            return None

    def search_web(self, query: str) -> List[str]:
        """Perform actual web search using DuckDuckGo."""
        try:
            # Use DuckDuckGo HTML search (no API key required)
            url = "https://html.duckduckgo.com/html/"
            params = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }

            response = requests.post(url, data=params, headers=headers, timeout=10)
            response.raise_for_status()

            # Basic parsing of results (just get snippets for Claude to analyze)
            text = response.text
            results = []

            # Extract result snippets (very basic approach)
            import re
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)
            for snippet in snippets[:5]:  # Top 5 results
                # Clean HTML tags
                clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                clean_snippet = clean_snippet.strip()
                if clean_snippet:
                    results.append(clean_snippet)

            return results

        except Exception as e:
            self.logger.warning(f"Web search failed for '{query}': {e}")
            return []

    def search_web_for_improvements(self) -> List[Dict]:
        """Search web for new technologies and improvements."""
        self.logger.info("Searching web for technology improvements...")

        search_queries = [
            "Docker sandbox best practices 2025",
            "Claude Code CLI improvements",
            "Python systemd integration security",
            "Slack bot best practices",
            "inotify alternatives Linux",
        ]

        all_findings = []

        for query in search_queries:
            try:
                self.logger.info(f"Searching: {query}")

                # Perform web search
                search_results = self.search_web(query)

                if not search_results:
                    continue

                # Combine search results
                search_context = "\n\n".join(search_results[:3])

                # Ask Claude to analyze search results
                prompt = f"""Based on these web search results for "{query}":

{search_context}

Identify potential improvements for the cursor-sandboxed project (a Docker sandbox for Claude Code CLI with Slack integration, systemd services, and file watching).

Focus on:
1. New technologies or tools worth considering
2. Security improvements
3. Performance optimizations
4. Modern best practices we might not be following

Return findings as JSON:
{{
  "findings": [
    {{
      "topic": "brief topic",
      "description": "specific actionable insight",
      "relevance": "how it applies to our project",
      "priority": "HIGH|MEDIUM|LOW"
    }}
  ]
}}

Only include HIGH and MEDIUM priority findings. If nothing relevant, return {{"findings": []}}"""

                response_text = self.call_claude(prompt)

                if not response_text:
                    continue

                # Extract JSON
                try:
                    start_idx = response_text.find('{')
                    end_idx = response_text.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = response_text[start_idx:end_idx]
                        result = json.loads(json_str)
                        if result.get('findings'):
                            all_findings.extend(result['findings'])
                except json.JSONDecodeError:
                    self.logger.warning(f"Could not parse analysis results for: {query}")

            except Exception as e:
                self.logger.error(f"Error processing '{query}': {e}")

        return all_findings

    def generate_notification(self, file_issues: List[Dict], web_findings: List[Dict]):
        """Generate notification file for Slack."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notification_file = self.notification_dir / f"{timestamp}-codebase-improvements.md"

        # Ensure notification directory exists
        self.notification_dir.mkdir(parents=True, exist_ok=True)

        # Build notification content
        content = f"""# 🔍 Codebase Improvement Analysis

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Project**: cursor-sandboxed
**Analysis Type**: Automated Daily Review

---

## 📊 Summary

- **Files Analyzed**: {len(file_issues)} files with potential improvements
- **Web Research Findings**: {len(web_findings)} relevant discoveries
- **Priority Breakdown**:
  - HIGH: {sum(1 for f in file_issues for i in f['analysis']['issues'] if i.get('priority') == 'HIGH')} file issues
  - MEDIUM: {sum(1 for f in file_issues for i in f['analysis']['issues'] if i.get('priority') == 'MEDIUM')} file issues

---

"""

        # Add file-specific issues
        if file_issues:
            content += "## 🔧 File-Specific Improvements\n\n"

            # Group by priority
            high_priority = [f for f in file_issues if any(i.get('priority') == 'HIGH' for i in f['analysis']['issues'])]
            medium_priority = [f for f in file_issues if f not in high_priority]

            if high_priority:
                content += "### ⚠️ HIGH Priority\n\n"
                for item in high_priority:
                    content += f"**File**: `{item['file']}`\n\n"
                    for issue in item['analysis']['issues']:
                        if issue.get('priority') == 'HIGH':
                            content += f"- **{issue['category'].title()}**: {issue['description']}\n"
                            content += f"  - *Suggestion*: {issue['suggestion']}\n\n"

            if medium_priority:
                content += "### 📋 MEDIUM Priority\n\n"
                for item in medium_priority[:5]:  # Limit to top 5
                    content += f"**File**: `{item['file']}`\n\n"
                    for issue in item['analysis']['issues']:
                        if issue.get('priority') == 'MEDIUM':
                            content += f"- **{issue['category'].title()}**: {issue['description']}\n"
                            content += f"  - *Suggestion*: {issue['suggestion']}\n\n"

        # Add web findings
        if web_findings:
            content += "\n## 🌐 Technology & Best Practice Research\n\n"

            # Group by priority
            high_web = [f for f in web_findings if f.get('priority') == 'HIGH']
            medium_web = [f for f in web_findings if f.get('priority') == 'MEDIUM']

            if high_web:
                content += "### ⚠️ HIGH Priority Findings\n\n"
                for finding in high_web:
                    content += f"**{finding['topic']}**\n"
                    content += f"- {finding['description']}\n"
                    content += f"- *Relevance*: {finding['relevance']}\n\n"

            if medium_web:
                content += "### 📋 MEDIUM Priority Findings\n\n"
                for finding in medium_web:
                    content += f"**{finding['topic']}**\n"
                    content += f"- {finding['description']}\n"
                    content += f"- *Relevance*: {finding['relevance']}\n\n"

        # Add footer
        content += f"""
---

## 🎯 Next Steps

1. Review HIGH priority items first
2. Evaluate web findings for applicability
3. Create JIRA tickets for approved improvements
4. Schedule implementation in next sprint

---

📅 Next analysis: Tomorrow at 11:00 AM PST
🤖 Automated by cursor-sandboxed codebase analyzer
"""

        # Write notification
        notification_file.write_text(content)
        self.logger.info(f"Notification written to: {notification_file}")

        return notification_file

    def run_analysis(self, enable_web_search: bool = True):
        """Main analysis workflow."""
        self.logger.info("Starting codebase analysis...")
        self.logger.info(f"Analyzing: {self.codebase_path}")

        # Get files to analyze
        files = self.get_files_to_analyze()

        # Analyze ALL files (not limited)
        file_issues = []

        self.logger.info(f"Analyzing {len(files)} files...")
        for i, file_path in enumerate(files):
            self.logger.info(f"[{i+1}/{len(files)}] Analyzing {file_path.name}")
            result = self.analyze_file(file_path)
            if result:
                file_issues.append(result)

        self.logger.info(f"Found issues in {len(file_issues)} files")

        # Web search for improvements
        web_findings = []
        if enable_web_search:
            web_findings = self.search_web_for_improvements()
        else:
            self.logger.info("Web search disabled")

        # Generate notification if we have findings
        if file_issues or web_findings:
            notification_file = self.generate_notification(file_issues, web_findings)
            self.logger.info(f"Analysis complete! Notification: {notification_file}")
            return True
        else:
            self.logger.info("No significant improvements found")
            return False


def check_last_run(notification_dir: Path) -> Optional[datetime]:
    """Check when the analyzer was last run by finding the most recent report."""
    try:
        # Find all codebase improvement notifications
        reports = list(notification_dir.glob("*-codebase-improvements.md"))

        if not reports:
            return None

        # Sort by modification time, get most recent
        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        most_recent = reports[0]

        # Get modification time
        mtime = datetime.fromtimestamp(most_recent.stat().st_mtime)
        return mtime
    except Exception as e:
        logging.error(f"Error checking last run: {e}")
        return None


def should_run_analysis(notification_dir: Path, force: bool = False) -> bool:
    """Determine if analysis should run based on weekly schedule."""
    if force:
        print("Force flag set - running analysis")
        return True

    last_run = check_last_run(notification_dir)

    if last_run is None:
        print("No previous analysis found - running analysis")
        return True

    days_since_last_run = (datetime.now() - last_run).days

    if days_since_last_run >= 7:
        print(f"Last analysis was {days_since_last_run} days ago - running analysis")
        return True
    else:
        print(f"Last analysis was {days_since_last_run} days ago (< 7 days) - skipping")
        print(f"Use --force to run anyway")
        return False


def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Analyze cursor-sandboxed codebase for improvements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run if last analysis was >7 days ago
  %(prog)s --force            # Force run regardless of schedule
  %(prog)s --no-web-search    # Skip web search (faster)
        """
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force analysis even if run recently'
    )
    parser.add_argument(
        '--no-web-search',
        action='store_true',
        help='Skip web search (faster, code analysis only)'
    )

    args = parser.parse_args()

    # Configuration
    codebase_path = Path.home() / "khan" / "cursor-sandboxed"
    notification_dir = Path.home() / "sharing" / "notifications"

    # Validate paths
    if not codebase_path.exists():
        print(f"Error: Codebase path not found: {codebase_path}", file=sys.stderr)
        sys.exit(1)

    # Check if we should run based on weekly schedule
    if not should_run_analysis(notification_dir, force=args.force):
        sys.exit(0)

    # Create analyzer and run
    try:
        analyzer = CodebaseAnalyzer(codebase_path, notification_dir)
        enable_web_search = not args.no_web_search
        analyzer.run_analysis(enable_web_search=enable_web_search)
    except Exception as e:
        print(f"Error running analysis: {e}", file=sys.stderr)
        logging.exception("Analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
