#!/usr/bin/env python3
"""
Command Handler - Processes incoming Slack messages for PR-related commands

Monitors ~/sharing/incoming/ and ~/sharing/responses/ for commands like:
- "review PR 123"
- "/pr review 123"
- "review PR 123 in webapp"
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime


class CommandHandler:
    def __init__(self):
        self.incoming_dir = Path.home() / "sharing" / "incoming"
        self.responses_dir = Path.home() / "sharing" / "responses"
        self.processed_dir = Path.home() / "sharing" / "tracking" / "processed-commands"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.reviewer_script = Path(__file__).parent / "pr-reviewer.py"

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

    def extract_commands(self, content: str) -> list:
        """Extract PR review commands from message content"""
        commands = []

        # Patterns for PR review commands
        patterns = [
            # "review PR 123"
            # "review PR 123 in webapp"
            r'review\s+PR\s+#?(\d+)(?:\s+in\s+(\w+))?',

            # "/pr review 123"
            # "/pr review 123 webapp"
            r'/pr\s+review\s+#?(\d+)(?:\s+(\w+))?',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                pr_num = int(match.group(1))
                repo = match.group(2) if match.lastindex >= 2 else None

                commands.append({
                    'type': 'review_pr',
                    'pr_number': pr_num,
                    'repo': repo
                })

        return commands

    def execute_command(self, command: dict):
        """Execute a parsed command"""
        if command['type'] == 'review_pr':
            self.review_pr(command['pr_number'], command.get('repo'))

    def review_pr(self, pr_num: int, repo: str = None):
        """Trigger PR review"""
        print(f"Triggering review for PR #{pr_num}" + (f" in {repo}" if repo else ""))

        try:
            cmd = ['python3', str(self.reviewer_script), str(pr_num)]
            if repo:
                cmd.append(repo)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
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


def main():
    """Main entry point"""
    handler = CommandHandler()
    handler.process_messages()


if __name__ == '__main__':
    main()
