#!/usr/bin/env python3
"""
Comment Responder - Detects new PR comments and generates response suggestions

Monitors PR comments, detects comments that need responses (questions, change
requests), and generates suggested responses for human approval.
"""

import json
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class CommentResponder:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.comments_dir = self.github_dir / "comments"
        self.prs_dir = self.github_dir / "prs"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.beads_dir = Path.home() / "beads"

        # Track which comments have been processed
        self.state_file = Path.home() / "sharing" / "tracking" / "comment-responder-state.json"
        self.processed_comments = self.load_state()

    def load_state(self) -> Dict:
        """Load previously processed comment IDs"""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {'processed': {}}

    def save_state(self):
        """Save processed comment IDs"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump({'processed': self.processed_comments}, f, indent=2)

    def watch(self):
        """Main watch loop - check for new comments"""
        if not self.comments_dir.exists():
            print("Comments directory not found - skipping watch")
            return

        # Scan all comment files
        for comment_file in self.comments_dir.glob("*-PR-*-comments.json"):
            try:
                self.process_comment_file(comment_file)
            except Exception as e:
                print(f"Error processing {comment_file}: {e}")

    def process_comment_file(self, comment_file: Path):
        """Process a single PR's comment file"""
        with comment_file.open() as f:
            data = json.load(f)

        pr_num = data['pr_number']
        repo = data['repository']
        repo_name = repo.split('/')[-1]

        comments = data.get('comments', [])
        if not comments:
            return

        # Find new comments that need responses
        for comment in comments:
            comment_id = str(comment.get('id'))
            if not comment_id or comment_id in self.processed_comments:
                continue  # Already processed

            # Check if comment needs a response
            if self.needs_response(comment):
                print(f"New comment needing response: PR #{pr_num}, comment {comment_id}")
                self.handle_comment(pr_num, repo_name, repo, comment)

            # Mark as processed
            self.processed_comments[comment_id] = datetime.utcnow().isoformat() + 'Z'

        self.save_state()

    def needs_response(self, comment: Dict) -> bool:
        """Determine if a comment needs a response"""
        body = comment.get('body', '').lower()
        author = comment.get('author', '')

        # Skip bot comments
        if 'bot' in author.lower():
            return False

        # Patterns indicating a response is needed
        question_patterns = [
            r'\?$',  # Ends with question mark
            r'\bcan you\b',
            r'\bcould you\b',
            r'\bwould you\b',
            r'\bwhat about\b',
            r'\bwhy\b',
            r'\bhow\b',
            r'\bplease\b.*\bchange\b',
            r'\bplease\b.*\bupdate\b',
            r'\bplease\b.*\bfix\b',
            r'\bcould we\b',
            r'\bshould we\b',
            r'\bwhat if\b',
        ]

        for pattern in question_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                return True

        # Check for change requests
        change_patterns = [
            r'\bchange\b.*\bto\b',
            r'\bupdate\b.*\bto\b',
            r'\breplace\b.*\bwith\b',
            r'\bfix\b',
            r'\bshould be\b',
            r'\binstead of\b',
        ]

        for pattern in change_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                return True

        return False

    def handle_comment(self, pr_num: int, repo_name: str, repo: str, comment: Dict):
        """Generate response for a comment and create notification"""
        # Load PR context
        pr_context = self.load_pr_context(repo_name, pr_num)

        # Generate response suggestion
        response = self.generate_response(comment, pr_context)

        # Create Beads task
        beads_id = self.create_beads_task(pr_num, repo_name, comment)

        # Create notification
        self.create_response_notification(pr_num, repo_name, comment, response, beads_id)

    def load_pr_context(self, repo_name: str, pr_num: int) -> Dict:
        """Load PR context from synced files"""
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        context = {
            'pr_number': pr_num,
            'title': f"PR #{pr_num}",
            'description': '',
            'url': '',
            'files_changed': []
        }

        if pr_file.exists():
            with pr_file.open() as f:
                content = f.read()
                lines = content.split('\n')

                in_description = False
                for line in lines:
                    if line.startswith('# PR #'):
                        context['title'] = line.replace('# PR #', '').replace(f'{pr_num}: ', '').strip()
                    elif line.startswith('**URL**:'):
                        context['url'] = line.replace('**URL**:', '').strip()
                    elif line.startswith('## Description'):
                        in_description = True
                    elif in_description and line.startswith('## '):
                        in_description = False
                    elif in_description and line.strip():
                        context['description'] += line + '\n'

        if diff_file.exists():
            context['has_diff'] = True
            # Could load diff snippets if needed

        return context

    def generate_response(self, comment: Dict, pr_context: Dict) -> Dict:
        """Generate suggested response based on comment and PR context"""
        comment_body = comment.get('body', '')
        comment_author = comment.get('author', '')

        response = {
            'suggested_text': '',
            'reasoning': '',
            'type': 'acknowledgment',
            'confidence': 'medium'
        }

        # Classify comment type
        comment_lower = comment_body.lower()

        # Question
        if '?' in comment_body:
            response['type'] = 'question'
            response['confidence'] = 'medium'

            # Try to understand what's being asked
            if 'why' in comment_lower:
                response['suggested_text'] = f"Good question! The reasoning behind this approach is [EXPLAIN DECISION]. "
                response['suggested_text'] += "This allows us to [BENEFIT], though I'm open to alternative approaches if you have suggestions."
                response['reasoning'] = "User asking 'why' - provide rationale and show openness to feedback"

            elif 'how' in comment_lower:
                response['suggested_text'] = f"Good question! This works by [EXPLAIN MECHANISM]. "
                response['suggested_text'] += "I can add more documentation if that would help clarify."
                response['reasoning'] = "User asking 'how' - explain mechanism and offer to add docs"

            elif 'what about' in comment_lower or 'what if' in comment_lower:
                response['suggested_text'] = "That's a good point. [SCENARIO] is definitely worth considering. "
                response['suggested_text'] += "My current approach handles [CURRENT], but we could extend it to cover [SCENARIO] in a follow-up. What do you think?"
                response['reasoning'] = "User suggesting alternative scenario - acknowledge and discuss trade-offs"

            else:
                response['suggested_text'] = f"Thanks for the question! [PROVIDE ANSWER]. "
                response['suggested_text'] += "Let me know if that answers your question or if you'd like me to clarify further."
                response['reasoning'] = "Generic question - provide answer and offer to clarify"

        # Change request
        elif any(word in comment_lower for word in ['change', 'update', 'fix', 'should be', 'instead of']):
            response['type'] = 'change_request'
            response['confidence'] = 'high'

            # Extract what needs to be changed if possible
            if 'to' in comment_lower:
                response['suggested_text'] = f"Good catch! I'll update this. "
                response['suggested_text'] += "Let me make that change and push an update."
                response['reasoning'] = "Change request with clear direction - acknowledge and commit to action"
            else:
                response['suggested_text'] = "Thanks for catching that! "
                response['suggested_text'] += "I'll fix this and push an update shortly."
                response['reasoning'] = "Change request - commit to fixing"

            response['action_needed'] = True

        # Concern or suggestion
        elif any(word in comment_lower for word in ['concern', 'worried', 'might', 'could', 'should']):
            response['type'] = 'concern'
            response['confidence'] = 'medium'

            response['suggested_text'] = "That's a valid concern. "
            response['suggested_text'] += "[EXPLAIN HOW CURRENT APPROACH ADDRESSES THIS OR PROPOSE SOLUTION]. "
            response['suggested_text'] += "Would that address your concern?"
            response['reasoning'] = "User expressing concern - address it and check if satisfied"

        # Positive feedback
        elif any(word in comment_lower for word in ['looks good', 'lgtm', 'nice', 'great']):
            response['type'] = 'positive'
            response['confidence'] = 'high'

            response['suggested_text'] = f"Thanks {comment_author}! 🙏"
            response['reasoning'] = "Positive feedback - simple acknowledgment"

        # Generic/unclear
        else:
            response['suggested_text'] = f"Thanks for the feedback, {comment_author}! "
            response['suggested_text'] += "Let me know if you'd like me to make any changes or if you have additional suggestions."
            response['reasoning'] = "Generic comment - acknowledge and invite clarification"

        # Add context placeholders
        if '[' in response['suggested_text']:
            response['needs_customization'] = True
            response['customization_note'] = "Replace bracketed placeholders with specific details from the PR context"

        return response

    def create_beads_task(self, pr_num: int, repo_name: str, comment: Dict) -> Optional[str]:
        """Create Beads task for responding to comment"""
        try:
            result = subprocess.run(['which', 'beads'], capture_output=True)
            if result.returncode != 0:
                return None

            author = comment.get('author', 'reviewer')
            comment_preview = comment.get('body', '')[:50]
            title = f"Respond to {author}'s comment on PR #{pr_num}"

            result = subprocess.run(
                ['beads', 'add', title, '--tags', f'pr-{pr_num}', 'comment-response', repo_name],
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
                    notes += f"Comment from: {author}\n"
                    notes += f"Preview: {comment_preview}...\n"
                    notes += f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

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

    def create_response_notification(self, pr_num: int, repo_name: str, comment: Dict,
                                     response: Dict, beads_id: Optional[str]):
        """Create notification with suggested response"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notifications_dir / f"{timestamp}-comment-response-{pr_num}.md"

        comment_author = comment.get('author', 'Reviewer')
        comment_body = comment.get('body', '')
        comment_created = comment.get('created_at', '')

        with notif_file.open('w') as f:
            f.write(f"# 💬 New PR Comment Needs Response: #{pr_num}\n\n")
            f.write(f"**PR**: #{pr_num} in {repo_name}\n")
            f.write(f"**Comment Author**: {comment_author}\n")
            f.write(f"**Posted**: {comment_created}\n")
            if beads_id:
                f.write(f"**Beads Task**: {beads_id}\n")
            f.write("\n")

            # Original comment
            f.write("## 💭 Original Comment\n\n")
            f.write(f"**{comment_author} wrote:**\n\n")
            f.write("```\n")
            f.write(comment_body)
            f.write("\n```\n\n")

            # Response type and confidence
            f.write("## 🤖 Suggested Response\n\n")
            f.write(f"**Type**: {response['type']}\n")
            f.write(f"**Confidence**: {response['confidence']}\n")
            f.write(f"**Reasoning**: {response['reasoning']}\n\n")

            # Suggested response text
            f.write("### Suggested Reply:\n\n")
            f.write("```\n")
            f.write(response['suggested_text'])
            f.write("\n```\n\n")

            # Customization needed?
            if response.get('needs_customization'):
                f.write("⚠️ **Note**: This response contains placeholders that need to be customized:\n")
                f.write(f"- {response.get('customization_note', 'Replace bracketed sections with specific details')}\n\n")

            # Action needed?
            if response.get('action_needed'):
                f.write("⚡ **Action Required**: This comment requests changes to the PR.\n")
                f.write("Consider making the requested changes before posting the response.\n\n")

            # Next steps
            f.write("## 📋 Next Steps\n\n")
            f.write("1. Review the suggested response above\n")
            f.write("2. Customize any bracketed placeholders with specific details\n")
            f.write("3. Reply to this notification with your final response text, OR\n")
            f.write("4. Post the response directly on GitHub\n")

            if response.get('action_needed'):
                f.write("5. Make the requested code changes\n")
                f.write("6. Push the updates to the PR\n")

            f.write("\n")
            f.write("**Quick Commands:**\n")
            f.write("- Reply with 'post: [your response text]' to prepare response for posting\n")
            f.write("- Reply with 'skip' to handle this comment manually\n")

            f.write("\n---\n")
            f.write(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📂 PR #{pr_num} in {repo_name}\n")

        print(f"  ✓ Created response notification: {notif_file.name}")


def main():
    """Main entry point"""
    responder = CommentResponder()
    responder.watch()


if __name__ == '__main__':
    main()
