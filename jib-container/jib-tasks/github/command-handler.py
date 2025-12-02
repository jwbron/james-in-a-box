#!/usr/bin/env python3
"""
Command Handler - Processes incoming Slack messages for PR-related commands

Monitors ~/sharing/incoming/ and ~/sharing/responses/ for commands like:
- "review PR 123"
- "/pr review 123"
- "review PR 123 in webapp"

Enhanced with Claude-based natural language command parsing for flexibility.
Supports variations like:
- "can you review my PR"
- "look at pull request 123"
- "check out PR #456 in webapp"
- "review PR 123 and then fix the linting"

Usage:
  # Default: Use Claude for intelligent parsing
  command-handler.py

  # Use regex-only parsing (faster, no Claude)
  command-handler.py --no-claude

  # Show verbose output including Claude responses
  command-handler.py --verbose
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# Add shared modules to path
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "shared"))

try:
    from claude import is_claude_available, run_claude
except ImportError:
    # Fallback if shared module not available
    def is_claude_available() -> bool:
        return False

    def run_claude(*args, **kwargs):
        return None


@dataclass
class ParsedCommand:
    """Structured command parsed from user message."""

    command_type: str  # "review_pr", "analyze_pr", "fix_pr", "list_prs", etc.
    pr_number: int | None  # PR number if specified
    repo: str | None  # Repository name if specified
    additional_context: str | None  # Extra context from the message
    confidence: str  # "high", "medium", "low"


class ClaudeCommandParser:
    """Claude-based agent for natural language command parsing.

    Uses Claude to understand natural language variations of commands,
    supporting flexible phrasing and multi-intent messages.
    """

    COMMAND_PARSE_PROMPT = """You are a command parser for a GitHub PR assistant bot.

Parse the following message and extract any PR-related commands. The assistant can:
1. **review_pr** - Review a pull request (code review, analysis)
2. **analyze_pr** - Analyze PR status, checks, CI failures
3. **fix_pr** - Fix issues in a PR (linting, tests, etc.)
4. **list_prs** - List open PRs in a repository

## Message to Parse
{message}

## Instructions
Extract ALL commands from the message. Users may express commands in various ways:
- Direct: "review PR 123", "/pr review 456"
- Natural: "can you review my pull request", "look at PR #789"
- Implicit: "what do you think about my changes in #123"
- Multi-intent: "review PR 123 and then fix the linting"

For each command found, determine:
- command_type: One of review_pr, analyze_pr, fix_pr, list_prs
- pr_number: The PR number if mentioned (null if not specified)
- repo: Repository name if mentioned (null if not specified, e.g., "webapp", "james-in-a-box")
- additional_context: Any extra context like "focus on security", "fix linting"
- confidence: high/medium/low based on how clear the intent is

## Response Format
Respond with JSON only (no markdown code blocks):

{{
    "commands": [
        {{
            "command_type": "review_pr",
            "pr_number": 123,
            "repo": "webapp",
            "additional_context": "focus on performance",
            "confidence": "high"
        }}
    ],
    "message_intent": "Brief description of what the user wants",
    "ambiguities": ["Any unclear aspects of the request"]
}}

If no commands are found, return:
{{
    "commands": [],
    "message_intent": "No PR-related commands detected",
    "ambiguities": []
}}
"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._available = None

    def is_available(self) -> bool:
        """Check if Claude is available for parsing."""
        if self._available is None:
            self._available = is_claude_available()
        return self._available

    def parse_message(self, content: str) -> list[ParsedCommand]:
        """Parse a message for commands using Claude.

        Args:
            content: The message content to parse.

        Returns:
            List of ParsedCommand objects, empty if no commands found.
        """
        if not self.is_available():
            return []

        # Build prompt
        prompt = self.COMMAND_PARSE_PROMPT.format(message=content[:2000])

        # Call Claude
        result = run_claude(
            prompt=prompt,
            timeout=30,  # 30 seconds should be plenty for parsing
            stream=self.verbose,
            cwd=Path.home() / "khan",
        )

        if not result or not result.success:
            if self.verbose:
                print("  Claude parsing failed")
            return []

        # Parse JSON response
        try:
            parsed_data = self._extract_json(result.stdout)
            if parsed_data and "commands" in parsed_data:
                commands = []
                for cmd in parsed_data["commands"]:
                    commands.append(
                        ParsedCommand(
                            command_type=cmd.get("command_type", "unknown"),
                            pr_number=cmd.get("pr_number"),
                            repo=cmd.get("repo"),
                            additional_context=cmd.get("additional_context"),
                            confidence=cmd.get("confidence", "medium"),
                        )
                    )

                if self.verbose and parsed_data.get("message_intent"):
                    print(f"  Intent: {parsed_data['message_intent']}")
                if self.verbose and parsed_data.get("ambiguities"):
                    print(f"  Ambiguities: {parsed_data['ambiguities']}")

                return commands
        except Exception as e:
            if self.verbose:
                print(f"  Failed to parse Claude response: {e}")

        return []

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from Claude's response."""
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            text = "\n".join(json_lines)

        # Try to parse as JSON directly
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None


class CommandHandler:
    """Processes incoming Slack messages for PR-related commands.

    Supports both regex-based parsing (fast, exact matches) and
    Claude-based parsing (flexible natural language understanding).
    """

    def __init__(self, use_claude: bool = True, verbose: bool = False):
        self.incoming_dir = Path.home() / "sharing" / "incoming"
        self.responses_dir = Path.home() / "sharing" / "responses"
        self.processed_dir = Path.home() / "sharing" / "tracking" / "processed-commands"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.reviewer_script = Path(__file__).parent / "pr-reviewer.py"
        self.analyzer_script = Path(__file__).parent / "pr-analyzer.py"

        self.use_claude = use_claude
        self.verbose = verbose
        self.claude_parser = ClaudeCommandParser(verbose=verbose) if use_claude else None

    def process_messages(self):
        """Process all unprocessed incoming messages and responses"""
        processed_count = 0

        # Process incoming messages
        if self.incoming_dir.exists():
            for msg_file in self.incoming_dir.glob("*.md"):
                if self.process_message_file(msg_file):
                    processed_count += 1

        # Process responses
        if self.responses_dir.exists():
            for msg_file in self.responses_dir.glob("*.md"):
                if self.process_message_file(msg_file):
                    processed_count += 1

        if processed_count > 0:
            print(f"Processed {processed_count} command(s)")

        return processed_count

    def process_message_file(self, msg_file: Path) -> bool:
        """Process a single message file for commands"""
        # Check if already processed
        processed_marker = self.processed_dir / msg_file.name
        if processed_marker.exists():
            return False

        try:
            with msg_file.open() as f:
                content = f.read()

            # Look for PR review commands
            commands = self.extract_commands(content)

            if not commands:
                # Mark as processed (no commands found)
                processed_marker.touch()
                return False

            # Execute commands
            for command in commands:
                self.execute_command(command)

            # Mark as processed
            processed_marker.touch()
            return True

        except Exception as e:
            print(f"Error processing {msg_file}: {e}")
            return False

    def extract_commands(self, content: str) -> list[dict]:
        """Extract PR commands from message content.

        Uses Claude for intelligent parsing when available,
        with fallback to regex patterns.
        """
        # Try Claude-based parsing first
        if self.claude_parser and self.claude_parser.is_available():
            if self.verbose:
                print("  Using Claude for command parsing...")

            parsed_commands = self.claude_parser.parse_message(content)
            if parsed_commands:
                # Convert ParsedCommand objects to dict format for execute_command
                commands = []
                for cmd in parsed_commands:
                    # Only process high/medium confidence commands
                    if cmd.confidence == "low":
                        if self.verbose:
                            print(f"  Skipping low-confidence command: {cmd.command_type}")
                        continue

                    commands.append(
                        {
                            "type": cmd.command_type,
                            "pr_number": cmd.pr_number,
                            "repo": cmd.repo,
                            "context": cmd.additional_context,
                            "source": "claude",
                        }
                    )

                if commands:
                    return commands

        # Fallback to regex-based extraction
        return self._extract_commands_regex(content)

    def _extract_commands_regex(self, content: str) -> list[dict]:
        """Extract commands using regex patterns (fallback method)."""
        commands = []

        # Patterns for PR review commands
        patterns = [
            # "review PR 123"
            # "review PR 123 in webapp"
            r"review\s+PR\s+#?(\d+)(?:\s+in\s+(\w+))?",
            # "/pr review 123"
            # "/pr review 123 webapp"
            r"/pr\s+review\s+#?(\d+)(?:\s+(\w+))?",
            # "look at PR 123", "check PR 123", "analyze PR 123"
            r"(?:look\s+at|check|analyze)\s+PR\s+#?(\d+)(?:\s+in\s+(\w+))?",
            # "pull request 123" or "PR #123"
            r"(?:pull\s+request|PR)\s+#?(\d+)(?:\s+in\s+(\w+))?",
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                pr_num = int(match.group(1))
                repo = match.group(2) if match.lastindex >= 2 else None

                # Avoid duplicates
                if not any(c["pr_number"] == pr_num and c.get("repo") == repo for c in commands):
                    commands.append(
                        {
                            "type": "review_pr",
                            "pr_number": pr_num,
                            "repo": repo,
                            "source": "regex",
                        }
                    )

        return commands

    def execute_command(self, command: dict):
        """Execute a parsed command"""
        cmd_type = command.get("type", "")

        if cmd_type == "review_pr":
            self.review_pr(command.get("pr_number"), command.get("repo"))
        elif cmd_type == "analyze_pr":
            self.analyze_pr(command.get("pr_number"), command.get("repo"))
        elif cmd_type == "fix_pr":
            # Fix commands could trigger specific fix workflows
            self.review_pr(command.get("pr_number"), command.get("repo"))
            if self.verbose:
                print("  Note: fix_pr mapped to review_pr for now")
        elif cmd_type == "list_prs":
            self.list_prs(command.get("repo"))
        elif self.verbose:
            print(f"  Unknown command type: {cmd_type}")

    def review_pr(self, pr_num: int | None, repo: str | None = None):
        """Trigger PR review"""
        if pr_num is None:
            print("  ⚠️ Cannot review PR: no PR number specified")
            return

        print(f"Triggering review for PR #{pr_num}" + (f" in {repo}" if repo else ""))

        try:
            cmd = ["python3", str(self.reviewer_script), str(pr_num)]
            if repo:
                cmd.append(repo)

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode == 0:
                print(f"  ✅ Review completed for PR #{pr_num}")
            else:
                print(f"  ⚠️ Review failed for PR #{pr_num}")
                if result.stderr:
                    print(f"     Error: {result.stderr}")

        except subprocess.TimeoutExpired:
            print(f"  ⚠️ Review timed out for PR #{pr_num}")
        except Exception as e:
            print(f"  ⚠️ Error running review: {e}")

    def analyze_pr(self, pr_num: int | None, repo: str | None = None):
        """Trigger PR analysis (status, checks, etc.)"""
        if pr_num is None:
            print("  ⚠️ Cannot analyze PR: no PR number specified")
            return

        print(f"Triggering analysis for PR #{pr_num}" + (f" in {repo}" if repo else ""))

        if not self.analyzer_script.exists():
            print(f"  ⚠️ Analyzer script not found: {self.analyzer_script}")
            # Fall back to review
            self.review_pr(pr_num, repo)
            return

        try:
            cmd = ["python3", str(self.analyzer_script), str(pr_num)]
            if repo:
                cmd.append(repo)

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                print(f"  ✅ Analysis completed for PR #{pr_num}")
            else:
                print(f"  ⚠️ Analysis failed for PR #{pr_num}")
                if result.stderr:
                    print(f"     Error: {result.stderr}")

        except subprocess.TimeoutExpired:
            print(f"  ⚠️ Analysis timed out for PR #{pr_num}")
        except Exception as e:
            print(f"  ⚠️ Error running analysis: {e}")

    def list_prs(self, repo: str | None = None):
        """List open PRs in a repository"""
        print("Listing open PRs" + (f" in {repo}" if repo else ""))

        # Use gh CLI to list PRs
        try:
            cmd = ["gh", "pr", "list", "--state", "open"]
            if repo:
                cmd.extend(["--repo", f"jwbron/{repo}"])

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                print(result.stdout)
            else:
                print("  ⚠️ Failed to list PRs")
                if result.stderr:
                    print(f"     Error: {result.stderr}")

        except Exception as e:
            print(f"  ⚠️ Error listing PRs: {e}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Process Slack messages for PR-related commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: Use Claude for intelligent parsing
  %(prog)s

  # Use regex-only parsing (faster, no Claude)
  %(prog)s --no-claude

  # Show verbose output including Claude responses
  %(prog)s --verbose

Supported commands:
  - "review PR 123" or "review PR 123 in webapp"
  - "/pr review 123"
  - "can you review my pull request #456"
  - "look at PR 789" or "check PR 789"
  - "review PR 123 and then fix the linting" (multi-intent)
""",
    )

    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Disable Claude parsing, use regex patterns only",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output including Claude parsing progress",
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    # Show parsing mode
    if args.verbose:
        if args.no_claude:
            print("Command parsing: regex-only mode")
        else:
            print("Command parsing: Claude-enhanced mode")

    handler = CommandHandler(
        use_claude=not args.no_claude,
        verbose=args.verbose,
    )
    handler.process_messages()


if __name__ == "__main__":
    main()
