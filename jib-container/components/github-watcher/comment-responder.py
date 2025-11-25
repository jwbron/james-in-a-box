#!/usr/bin/env python3
"""
Comment Responder - Responds to PR comments using Claude

Monitors PR comments on YOUR OWN PRs, uses Claude to understand the comment
and formulate an appropriate response, then takes action:
- For writable repos: posts response to GitHub, makes/pushes code changes if needed
- For non-writable repos: notifies via Slack with suggested response and branch name

Scope:
- Only processes PRs you've opened (--author @me)
- Skips jib's own comments (identified by signature)
- Skips bot comments
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


def load_config() -> Dict:
    """Load repository configuration."""
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)

    return {"writable_repos": []}


def is_writable_repo(repo: str, config: Dict) -> bool:
    """Check if repo has write access."""
    writable = config.get("writable_repos", [])
    return repo in writable or repo.split("/")[-1] in [r.split("/")[-1] for r in writable]


class CommentResponder:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.comments_dir = self.github_dir / "comments"
        self.prs_dir = self.github_dir / "prs"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.khan_dir = Path.home() / "khan"

        # Load config
        self.config = load_config()

        # Track which comments have been processed
        self.state_file = Path.home() / "sharing" / "tracking" / "comment-responder-state.json"
        self.processed_comments = self.load_state()

        # Check for claude CLI
        if not self._check_claude_cli():
            raise RuntimeError("claude CLI not found - required for response generation")

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

    def load_state(self) -> Dict:
        """Load previously processed comment IDs."""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    data = json.load(f)
                    # Handle old nested format
                    while isinstance(data.get('processed'), dict) and 'processed' in data.get('processed', {}):
                        data = data['processed']
                    return data.get('processed', {})
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load state file: {e}")
        return {}

    def save_state(self):
        """Save processed comment IDs."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump({'processed': self.processed_comments}, f, indent=2)

    def watch(self):
        """Main watch loop - check for new comments."""
        if not self.comments_dir.exists():
            print("Comments directory not found - skipping watch")
            return

        for comment_file in self.comments_dir.glob("*-PR-*-comments.json"):
            try:
                self.process_comment_file(comment_file)
            except Exception as e:
                print(f"Error processing {comment_file}: {e}")
                import traceback
                traceback.print_exc()

    def process_comment_file(self, comment_file: Path):
        """Process a single PR's comment file."""
        with comment_file.open() as f:
            data = json.load(f)

        pr_num = data['pr_number']
        repo = data['repository']
        repo_name = repo.split('/')[-1]

        comments = data.get('comments', [])
        if not comments:
            return

        for comment in comments:
            comment_id = str(comment.get('id'))
            if not comment_id or comment_id in self.processed_comments:
                continue

            if self.needs_response(comment):
                print(f"New comment needing response: PR #{pr_num}, comment {comment_id}")
                self.handle_comment(pr_num, repo_name, repo, comment, data)

            self.processed_comments[comment_id] = datetime.utcnow().isoformat() + 'Z'

        self.save_state()

    def needs_response(self, comment: Dict) -> bool:
        """Determine if a comment needs a response."""
        body = comment.get('body', '')
        author = comment.get('author', '')

        # Skip bot comments
        if 'bot' in author.lower():
            return False

        # Skip jib's own comments (identified by signature)
        jib_signatures = [
            'authored by jib',
            '— jib',
            'generated with [claude code]',
        ]
        body_lower = body.lower()
        for sig in jib_signatures:
            if sig in body_lower:
                print(f"  Skipping jib's own comment (signature: {sig})")
                return False

        # Any non-jib, non-bot comment on our PR needs a response
        # Let Claude decide the appropriate action
        return True

    def handle_comment(self, pr_num: int, repo_name: str, repo: str, comment: Dict, pr_data: Dict):
        """Handle a comment by generating and posting a response."""
        # Load full PR context
        pr_context = self.load_pr_context(repo_name, pr_num)

        # Load all comments for context
        all_comments = pr_data.get('comments', [])

        # Check if this is a writable repo
        writable = is_writable_repo(repo, self.config)

        # Generate response using Claude
        response = self.generate_response_with_claude(comment, pr_context, all_comments, repo, pr_num, writable)

        if not response:
            print(f"  Failed to generate response for comment {comment.get('id')}")
            return

        if writable:
            self.handle_writable_repo(pr_num, repo_name, repo, comment, response)
        else:
            self.handle_readonly_repo(pr_num, repo_name, repo, comment, response)

    def load_pr_context(self, repo_name: str, pr_num: int) -> Dict:
        """Load PR context from synced files."""
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        context = {
            'pr_number': pr_num,
            'title': f"PR #{pr_num}",
            'description': '',
            'url': '',
            'diff': '',
        }

        if pr_file.exists():
            context['pr_content'] = pr_file.read_text()
            # Parse key fields
            for line in context['pr_content'].split('\n'):
                if line.startswith('# PR #'):
                    context['title'] = line.replace('# ', '').strip()
                elif line.startswith('**URL**:'):
                    context['url'] = line.replace('**URL**:', '').strip()

        if diff_file.exists():
            diff_content = diff_file.read_text()
            # Truncate if too large
            if len(diff_content) > 10000:
                diff_content = diff_content[:10000] + "\n... [diff truncated]"
            context['diff'] = diff_content

        return context

    def generate_response_with_claude(
        self,
        comment: Dict,
        pr_context: Dict,
        all_comments: List[Dict],
        repo: str,
        pr_num: int,
        writable: bool
    ) -> Optional[Dict]:
        """Use Claude to generate an appropriate response."""

        comment_body = comment.get('body', '')
        comment_author = comment.get('author', '')

        # Build comment history
        comment_history = ""
        for c in all_comments[-10:]:  # Last 10 comments for context
            author = c.get('author', 'unknown')
            body = c.get('body', '')[:500]
            is_current = c.get('id') == comment.get('id')
            marker = " <-- THIS IS THE COMMENT TO RESPOND TO" if is_current else ""
            comment_history += f"\n--- {author}{marker} ---\n{body}\n"

        # Build the prompt
        prompt = f"""You are jib, an AI software engineering agent. You need to respond to a PR comment.

CONTEXT:
- Repository: {repo}
- PR: #{pr_num}
- PR Title: {pr_context.get('title', 'Unknown')}
- PR URL: {pr_context.get('url', 'Unknown')}
- You have {"WRITE" if writable else "READ-ONLY"} access to this repository

PR DESCRIPTION:
{pr_context.get('pr_content', 'No description available')[:2000]}

RECENT DIFF (relevant changes):
{pr_context.get('diff', 'No diff available')[:3000]}

COMMENT THREAD:
{comment_history}

THE COMMENT TO RESPOND TO:
Author: {comment_author}
Content: {comment_body}

YOUR TASK:
1. Understand what the commenter is asking/requesting
2. Formulate an appropriate response
3. Determine if code changes are needed

RESPOND WITH JSON:
{{
    "response_text": "Your response to post as a GitHub comment. Be helpful, professional, and concise. Sign with '\\n\\n—\\nAuthored by jib'",
    "needs_code_changes": true/false,
    "code_change_description": "If needs_code_changes is true, describe what changes to make",
    "reasoning": "Brief explanation of your response approach"
}}

IMPORTANT:
- If the comment is just positive feedback (LGTM, looks good, etc.), respond with a brief thank you
- If asking a question, answer it based on the PR context
- If requesting changes, acknowledge and {"make the changes" if writable else "describe what changes would be needed"}
- If you disagree with the suggestion, explain your reasoning respectfully
- Always end response_text with the jib signature: "\\n\\n—\\nAuthored by jib"

Return ONLY the JSON, no other text."""

        try:
            print(f"  Calling Claude to generate response...")
            result = subprocess.run(
                ['claude', '-p', '--output-format', 'text', prompt],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                print(f"  Claude error: {result.stderr}")
                return None

            response_text = result.stdout.strip()

            # Parse JSON from response
            try:
                # Find JSON in response
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end > start:
                    json_str = response_text[start:end]
                    return json.loads(json_str)
                else:
                    print(f"  No JSON found in response")
                    return None
            except json.JSONDecodeError as e:
                print(f"  Failed to parse response JSON: {e}")
                return None

        except subprocess.TimeoutExpired:
            print(f"  Claude call timed out")
            return None
        except Exception as e:
            print(f"  Error calling Claude: {e}")
            return None

    def handle_writable_repo(self, pr_num: int, repo_name: str, repo: str, comment: Dict, response: Dict):
        """Handle response for a writable repository - post comment and make changes."""
        response_text = response.get('response_text', '')
        needs_changes = response.get('needs_code_changes', False)
        change_desc = response.get('code_change_description', '')

        # Find the repo directory
        repo_dir = self.find_repo_dir(repo_name)

        # If code changes needed, make them first
        branch_name = None
        if needs_changes and change_desc and repo_dir:
            branch_name = self.make_code_changes(repo_dir, pr_num, change_desc, response_text)
            if branch_name:
                response_text += f"\n\nI've pushed the changes to branch `{branch_name}`."

        # Post the response to GitHub
        self.post_github_comment(repo, pr_num, response_text)

        print(f"  ✓ Posted response to PR #{pr_num}")
        if branch_name:
            print(f"  ✓ Pushed changes to branch: {branch_name}")

    def handle_readonly_repo(self, pr_num: int, repo_name: str, repo: str, comment: Dict, response: Dict):
        """Handle response for read-only repository - notify via Slack."""
        response_text = response.get('response_text', '')
        needs_changes = response.get('needs_code_changes', False)
        change_desc = response.get('code_change_description', '')
        reasoning = response.get('reasoning', '')

        # Create notification
        self.create_notification(pr_num, repo_name, repo, comment, response_text, needs_changes, change_desc, reasoning)

        print(f"  ✓ Created notification for PR #{pr_num} (read-only repo)")

    def find_repo_dir(self, repo_name: str) -> Optional[Path]:
        """Find the local directory for a repository."""
        # Check common locations
        candidates = [
            self.khan_dir / repo_name,
            self.khan_dir / repo_name.replace('-', '_'),
        ]

        for candidate in candidates:
            if candidate.exists() and (candidate / '.git').exists():
                return candidate

        return None

    def make_code_changes(self, repo_dir: Path, pr_num: int, change_desc: str, context: str) -> Optional[str]:
        """Use Claude to make code changes and push them."""
        try:
            # Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )
            current_branch = result.stdout.strip()

            # Create prompt for Claude to make changes
            prompt = f"""Make the following code changes in the repository at {repo_dir}:

CHANGE REQUEST:
{change_desc}

CONTEXT:
{context[:1000]}

Instructions:
1. Read the relevant files
2. Make the minimal changes needed
3. The changes should be committed to the current branch: {current_branch}

After making changes, output a JSON summary:
{{
    "files_changed": ["list", "of", "files"],
    "commit_message": "Brief commit message",
    "success": true/false
}}

Make the changes now using the available tools (Read, Edit, Write, Bash for git commands)."""

            # Use claude with full tool access for making changes
            result = subprocess.run(
                ['claude', '-p', '--dangerously-skip-permissions', prompt],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"  Code change failed: {result.stderr}")
                return None

            # Check if there are changes to push
            status = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )

            if not status.stdout.strip():
                print(f"  No changes made")
                return None

            # Commit any uncommitted changes
            subprocess.run(['git', 'add', '-A'], cwd=repo_dir, capture_output=True)
            subprocess.run(
                ['git', 'commit', '-m', f'Address PR #{pr_num} feedback\n\n{change_desc[:200]}\n\n—\nAuthored by jib'],
                cwd=repo_dir,
                capture_output=True
            )

            # Push
            push_result = subprocess.run(
                ['git', 'push'],
                cwd=repo_dir,
                capture_output=True,
                text=True
            )

            if push_result.returncode != 0:
                print(f"  Push failed: {push_result.stderr}")
                return None

            return current_branch

        except Exception as e:
            print(f"  Error making code changes: {e}")
            return None

    def post_github_comment(self, repo: str, pr_num: int, comment_text: str):
        """Post a comment to a GitHub PR."""
        try:
            result = subprocess.run(
                ['gh', 'pr', 'comment', str(pr_num), '--repo', repo, '--body', comment_text],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"  Failed to post comment: {result.stderr}")
        except Exception as e:
            print(f"  Error posting comment: {e}")

    def create_notification(
        self,
        pr_num: int,
        repo_name: str,
        repo: str,
        comment: Dict,
        response_text: str,
        needs_changes: bool,
        change_desc: str,
        reasoning: str
    ):
        """Create notification for read-only repos."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notifications_dir / f"{timestamp}-comment-response-{pr_num}.md"

        self.notifications_dir.mkdir(parents=True, exist_ok=True)

        comment_author = comment.get('author', 'Reviewer')
        comment_body = comment.get('body', '')

        content = f"""# 💬 PR Comment Response Ready: #{pr_num}

**Repository**: {repo} (read-only - manual action required)
**PR**: #{pr_num}
**Comment Author**: {comment_author}

## Original Comment

{comment_body}

## Suggested Response

```
{response_text}
```

## Analysis

**Reasoning**: {reasoning}
"""

        if needs_changes:
            content += f"""
## Code Changes Needed

{change_desc}

**Note**: This is a read-only repository. Please make these changes manually or grant jib write access.
"""

        content += f"""
## Actions Required

1. Review the suggested response above
2. Post the response to the PR manually, or
3. Grant jib write access to this repository

---
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        notif_file.write_text(content)
        print(f"  Created notification: {notif_file.name}")


def main():
    """Main entry point."""
    logging.basicConfig(level=logging.INFO)

    try:
        responder = CommentResponder()
        responder.watch()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
