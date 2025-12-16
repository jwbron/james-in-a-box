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
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


# Validate required dependencies at startup with clear error messages
def _check_dependencies():
    """Check required dependencies and provide clear error messages if missing."""
    missing = []

    try:
        import yaml  # noqa: F401
    except ImportError:
        missing.append(("yaml", "pyyaml", "pip3 install pyyaml"))

    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append(("requests", "requests", "pip3 install requests"))

    if missing:
        print("=" * 60, file=sys.stderr)
        print("ERROR: Missing required Python dependencies", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for module, _package, install_cmd in missing:
            print(f"  Module '{module}' not found", file=sys.stderr)
            print(f"    Install with: {install_cmd}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("", file=sys.stderr)
        print("To fix: Add these to the Dockerfile:", file=sys.stderr)
        print("  RUN pip3 install --no-cache-dir pyyaml requests", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or rebuild the container after fixing.", file=sys.stderr)
        sys.exit(1)


_check_dependencies()

import yaml


# Add paths for imports:
# - jib-container/ for claude module
# - shared/ for jib_logging, notifications
# Path: jib-container/jib-tasks/github/comment-responder.py
_repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_repo_root / "jib-container"))  # for claude
sys.path.insert(0, str(_repo_root / "shared"))  # for jib_logging, notifications
try:
    from jib_logging import get_logger
    from llm import run_agent

    from notifications import NotificationContext, get_slack_service
except ImportError as e:
    print("=" * 60, file=sys.stderr)
    print("ERROR: Cannot import libraries", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  Import error: {e}", file=sys.stderr)
    print(
        f"  Checked paths: {_repo_root / 'jib-container'}, {_repo_root / 'shared'}", file=sys.stderr
    )
    print("", file=sys.stderr)
    print("This usually means a module is missing.", file=sys.stderr)
    print("Check that jib-container/claude/ and shared/ directories exist.", file=sys.stderr)
    sys.exit(1)

logger = get_logger("comment-responder")


class PRContextManager:
    """Manages persistent PR context in Beads.

    Each PR gets a unique task that tracks its entire lifecycle:
    - Comments and responses
    - CI check failures and fixes
    - Review feedback and changes

    Context ID format: pr-<repo>-<number> (e.g., pr-james-in-a-box-75)
    """

    def __init__(self):
        self.beads_dir = Path.home() / "beads"

    def get_context_id(self, repo: str, pr_num: int) -> str:
        """Generate unique context ID for a PR."""
        repo_name = repo.split("/")[-1]
        return f"pr-{repo_name}-{pr_num}"

    def search_context(self, repo: str, pr_num: int) -> str | None:
        """Search for existing beads task for this PR.

        Returns:
            Beads task ID if found, None otherwise.
        """
        context_id = self.get_context_id(repo, pr_num)
        try:
            result = subprocess.run(
                ["bd", "list", "--search", context_id, "--allow-stale"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Parse output to get task ID (first word of first line)
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if line.strip() and line.startswith("beads-"):
                        return line.split()[0]
            return None
        except Exception as e:
            logger.warning(f"Failed to search beads context: {e}")
            return None

    def get_context(self, repo: str, pr_num: int) -> dict | None:
        """Get existing context for a PR.

        Returns:
            Dict with task info and notes, or None if not found.
        """
        task_id = self.search_context(repo, pr_num)
        if not task_id:
            return None

        try:
            result = subprocess.run(
                ["bd", "show", task_id, "--allow-stale"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0:
                return {"task_id": task_id, "content": result.stdout.strip()}
            return None
        except Exception as e:
            logger.warning(f"Failed to get beads context: {e}")
            return None

    def create_context(self, repo: str, pr_num: int, pr_title: str) -> str | None:
        """Create new beads task for a PR.

        Returns:
            Beads task ID if created, None otherwise.
        """
        context_id = self.get_context_id(repo, pr_num)
        repo_name = repo.split("/")[-1]

        try:
            result = subprocess.run(
                [
                    "bd",
                    "create",
                    f"PR #{pr_num}: {pr_title}",
                    "--label",
                    "github-pr",
                    "--label",
                    context_id,
                    "--label",
                    repo_name,
                    "--allow-stale",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0:
                # Parse output to get task ID
                output = result.stdout.strip()
                if "beads-" in output:
                    # Extract task ID from output like "Created beads-abc123"
                    for word in output.split():
                        if word.startswith("beads-"):
                            return word.rstrip(":")
            return None
        except Exception as e:
            logger.warning(f"Failed to create beads context: {e}")
            return None

    def update_context(self, task_id: str, notes: str, status: str | None = None) -> bool:
        """Update beads task with new notes.

        Args:
            task_id: Beads task ID
            notes: Notes to append (will be timestamped)
            status: Optional status update (in_progress, closed, etc.)

        Returns:
            True if update succeeded, False otherwise.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        timestamped_notes = f"=== {timestamp} ===\n{notes}"

        try:
            cmd = ["bd", "update", task_id, "--notes", timestamped_notes, "--allow-stale"]
            if status:
                cmd.extend(["--status", status])

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to update beads context: {e}")
            return False

    def get_or_create_context(self, repo: str, pr_num: int, pr_title: str = "") -> str | None:
        """Get existing context or create new one.

        Returns:
            Beads task ID
        """
        existing = self.search_context(repo, pr_num)
        if existing:
            return existing
        return self.create_context(repo, pr_num, pr_title or f"PR #{pr_num}")


def load_config() -> dict:
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


def is_writable_repo(repo: str, config: dict) -> bool:
    """Check if repo has write access."""
    writable = config.get("writable_repos", [])
    return repo in writable or repo.split("/")[-1] in [r.split("/")[-1] for r in writable]


class CommentResponder:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.comments_dir = self.github_dir / "comments"
        self.prs_dir = self.github_dir / "prs"
        self.khan_dir = Path.home() / "khan"

        # Load config
        self.config = load_config()

        # Initialize notification service
        self.slack = get_slack_service()

        # Initialize PR context manager for beads integration
        self.pr_context = PRContextManager()

        # Track which comments have been processed
        self.state_file = Path.home() / "sharing" / "tracking" / "comment-responder-state.json"
        self.processed_comments = self.load_state()

        # Check for claude CLI
        if not self._check_claude_cli():
            raise RuntimeError("claude CLI not found - required for response generation")

    def _check_claude_cli(self) -> bool:
        """Check if Claude Agent SDK is available."""
        # SDK is always installed in the jib container
        return True

    def load_state(self) -> dict:
        """Load previously processed comment IDs."""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    data = json.load(f)
                    # Handle old nested format
                    while isinstance(data.get("processed"), dict) and "processed" in data.get(
                        "processed", {}
                    ):
                        data = data["processed"]
                    return data.get("processed", {})
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to load state file: {e}")
        return {}

    def save_state(self):
        """Save processed comment IDs."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump({"processed": self.processed_comments}, f, indent=2)

    def watch(self):
        """Main watch loop - check for new comments on all PRs in parallel."""
        if not self.comments_dir.exists():
            print("Comments directory not found - skipping watch")
            return

        comment_files = list(self.comments_dir.glob("*-PR-*-comments.json"))
        if not comment_files:
            print("No PR comment files found")
            return

        print(f"Found {len(comment_files)} PR(s) to check for comments")

        # Process PRs in parallel (max 4 concurrent to avoid overwhelming resources)
        max_workers = min(4, len(comment_files))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all PR processing tasks
            future_to_file = {
                executor.submit(self._process_comment_file_safe, cf): cf for cf in comment_files
            }

            # Collect results as they complete
            all_processed_ids = {}
            for future in as_completed(future_to_file):
                comment_file = future_to_file[future]
                try:
                    processed_ids = future.result()
                    if processed_ids:
                        all_processed_ids.update(processed_ids)
                except Exception as e:
                    print(f"Error processing {comment_file.name}: {e}")
                    import traceback

                    traceback.print_exc()

        # Merge all processed IDs into state and save once
        if all_processed_ids:
            self.processed_comments.update(all_processed_ids)
            self.save_state()
            print(f"✓ Saved state with {len(all_processed_ids)} newly processed comment(s)")

    def _process_comment_file_safe(self, comment_file: Path) -> dict[str, str]:
        """Process a comment file and return dict of processed comment IDs.

        This is a thread-safe wrapper that doesn't modify shared state directly.
        Returns a dict of {comment_id: timestamp} for successfully processed comments.
        """
        try:
            return self.process_comment_file(comment_file)
        except Exception as e:
            print(f"Error processing {comment_file.name}: {e}")
            import traceback

            traceback.print_exc()
            return {}

    def process_comment_file(self, comment_file: Path) -> dict[str, str]:
        """Process a single PR's comment file - batches all unprocessed comments.

        Returns:
            Dict of {comment_id: timestamp} for comments that were processed.
        """
        with comment_file.open() as f:
            data = json.load(f)

        pr_num = data["pr_number"]
        repo = data["repository"]
        repo_name = repo.split("/")[-1]

        comments = data.get("comments", [])
        if not comments:
            return {}

        # Collect all unprocessed comments that need responses
        pending_comments = []
        processed_ids = {}  # Return value: comment_id -> timestamp

        for comment in comments:
            comment_id = str(comment.get("id"))
            if not comment_id or comment_id in self.processed_comments:
                continue

            if self.needs_response(comment):
                pending_comments.append(comment)
            else:
                # Comment doesn't need a response (bot, jib's own comment, etc.)
                # Mark as processed to avoid re-checking it every time
                processed_ids[comment_id] = datetime.utcnow().isoformat() + "Z"

        # If no pending comments, return any skipped comment IDs
        if not pending_comments:
            return processed_ids

        print(f"Processing {len(pending_comments)} pending comment(s) on PR #{pr_num} ({repo})")

        # Process all pending comments as a batch
        success = self.handle_pr_comments_batch(pr_num, repo_name, repo, pending_comments, data)

        if success:
            # Mark all processed comments as done
            for comment in pending_comments:
                comment_id = str(comment.get("id"))
                processed_ids[comment_id] = datetime.utcnow().isoformat() + "Z"
            print(f"  ✓ PR #{pr_num}: Processed {len(pending_comments)} comment(s)")
        else:
            print(f"  ⚠ PR #{pr_num}: Failed to process comments - will retry on next run")

        return processed_ids

    def needs_response(self, comment: dict) -> bool:
        """Determine if a comment needs a response."""
        body = comment.get("body", "")
        author = comment.get("author", "")

        # Skip bot comments
        if "bot" in author.lower():
            return False

        # Skip jib's own comments (identified by signature)
        jib_signatures = [
            "authored by jib",
            "— jib",
            "generated with [claude code]",
        ]
        body_lower = body.lower()
        for sig in jib_signatures:
            if sig in body_lower:
                print(f"  Skipping jib's own comment (signature: {sig})")
                return False

        # Any non-jib, non-bot comment on our PR needs a response
        # Let Claude decide the appropriate action
        return True

    def handle_pr_comments_batch(
        self, pr_num: int, repo_name: str, repo: str, pending_comments: list[dict], pr_data: dict
    ) -> bool:
        """Handle all pending comments on a PR as a batch.

        This processes all unprocessed comments chronologically, allowing Claude to:
        - Respond to each comment appropriately
        - Make code changes if needed
        - Post multiple GitHub comments if appropriate

        Each PR maintains persistent context in Beads for memory across sessions.

        Returns:
            True if all comments were successfully handled, False otherwise.
        """
        # Load full PR context from synced files
        pr_file_context = self.load_pr_context(repo_name, pr_num)

        # Get or create beads context for this PR
        pr_title = pr_file_context.get("title", f"PR #{pr_num}")
        beads_task_id = self.pr_context.get_or_create_context(repo, pr_num, pr_title)

        # Load existing beads context (previous interactions history)
        beads_context = None
        if beads_task_id:
            beads_context = self.pr_context.get_context(repo, pr_num)
            print(f"  Beads context: {beads_task_id}")

        # Load all comments for full thread context
        all_comments = pr_data.get("comments", [])

        # Check if this is a writable repo
        writable = is_writable_repo(repo, self.config)

        # Get PR info from GitHub
        pr_info = self.get_pr_info(repo, pr_num)
        if not pr_info:
            print(f"  Could not get PR info for #{pr_num}")
            return False

        pr_state = pr_info.get("state", "UNKNOWN")
        pr_branch = pr_info.get("headRefName", "")
        base_branch = pr_info.get("baseRefName", "main")

        # Find the repo directory
        repo_dir = self.find_repo_dir(repo_name)

        # Build the batch prompt for Claude
        response = self.generate_batch_response(
            pending_comments=pending_comments,
            pr_context=pr_file_context,
            all_comments=all_comments,
            repo=repo,
            pr_num=pr_num,
            writable=writable,
            repo_dir=repo_dir,
            pr_branch=pr_branch,
            base_branch=base_branch,
            pr_state=pr_state,
            beads_context=beads_context,
        )

        if not response:
            print(f"  Failed to process comments on PR #{pr_num}")
            return False

        # Update beads context with processed comments
        if beads_task_id:
            comment_authors = list({c.get("author", "unknown") for c in pending_comments})
            notes = (
                f"Processed {len(pending_comments)} comment(s) from: {', '.join(comment_authors)}"
            )
            self.pr_context.update_context(beads_task_id, notes, status="in_progress")

        return True

    def handle_comment(
        self, pr_num: int, repo_name: str, repo: str, comment: dict, pr_data: dict
    ) -> bool:
        """Handle a single comment (legacy method for backwards compatibility).

        Returns:
            True if the comment was successfully handled, False otherwise.
            This is used to determine whether to mark the comment as processed.
        """
        # Load full PR context
        pr_context = self.load_pr_context(repo_name, pr_num)

        # Load all comments for context
        all_comments = pr_data.get("comments", [])

        # Check if this is a writable repo
        writable = is_writable_repo(repo, self.config)

        # Generate response using Claude
        response = self.generate_response_with_claude(
            comment, pr_context, all_comments, repo, pr_num, writable
        )

        if not response:
            print(f"  Failed to generate response for comment {comment.get('id')}")
            return False  # Don't mark as processed - will retry on next run

        if writable:
            self.handle_writable_repo(pr_num, repo_name, repo, comment, response)
        else:
            self.handle_readonly_repo(pr_num, repo_name, repo, comment, response)

        return True

    def generate_batch_response(
        self,
        pending_comments: list[dict],
        pr_context: dict,
        all_comments: list[dict],
        repo: str,
        pr_num: int,
        writable: bool,
        repo_dir: Path | None,
        pr_branch: str,
        base_branch: str,
        pr_state: str,
        beads_context: dict | None = None,
    ) -> bool:
        """Generate batch response using Claude with full context.

        Claude will process all pending comments and:
        - Make code changes if needed
        - Post GitHub comments for each response
        - Handle the conversation naturally

        Args:
            beads_context: Optional dict with 'task_id' and 'content' from previous interactions

        Returns:
            True if successful, False otherwise.
        """
        # Build full comment history
        comment_history = ""
        for c in all_comments:
            author = c.get("author", "unknown")
            body = c.get("body", "")
            created = c.get("created_at", "")
            comment_id = str(c.get("id", ""))

            # Mark pending comments that need responses
            is_pending = any(str(pc.get("id")) == comment_id for pc in pending_comments)
            marker = " **[NEEDS RESPONSE]**" if is_pending else ""

            comment_history += f"\n### {author} ({created}){marker}\n{body}\n"

        # Build previous interactions section from beads
        previous_interactions = ""
        if beads_context and beads_context.get("content"):
            previous_interactions = f"""
## Previous Interactions (from Beads)

This PR has been worked on before. Here's the history of previous interactions:

```
{beads_context.get("content", "")[:2000]}
```

Use this context to understand what has already been done and avoid repeating work.

"""

        # Build the prompt
        prompt = f"""You are jib, an AI software engineering agent. You're responding to PR feedback on your own PR.

## Context

- **Repository**: {repo}
- **PR**: #{pr_num}
- **PR State**: {pr_state}
- **PR Title**: {pr_context.get("title", "Unknown")}
- **PR URL**: {pr_context.get("url", "Unknown")}
- **PR Branch**: {pr_branch} → {base_branch}
- **Access**: {"WRITE (can make changes and push)" if writable else "READ-ONLY"}
- **Repo Directory**: {repo_dir if repo_dir else "Not found locally"}
- **Beads Task**: {beads_context.get("task_id", "None") if beads_context else "None"}
{previous_interactions}
## PR Description

{pr_context.get("pr_content", "No description available")[:3000]}

## Current Diff

{pr_context.get("diff", "No diff available")[:5000]}

## Comment Thread (Chronological)

{comment_history}

## Comments Needing Response

There are **{len(pending_comments)} comment(s)** marked with [NEEDS RESPONSE] above that you need to address.

## Your Task

Go through the pending comments **chronologically** and for each one:

1. **Understand the feedback**: What is the reviewer asking for or pointing out?
2. **Respond appropriately**:
   - For questions: Answer based on PR context
   - For requested changes: Implement them if you have write access
   - For feedback: Acknowledge and update code if needed
   - For approval (LGTM, etc.): Brief thank you
3. **Make code changes** if requested (if writable and PR is OPEN):
   - Read the relevant files
   - Make the necessary edits
   - Commit with a clear message: `git add -A && git commit -m "Address feedback: ..."`
   - Push: `git push origin {pr_branch}`
4. **Post GitHub comment(s)** for each response:
   - Use: `gh pr comment {pr_num} --repo {repo} --body "Your response..."`
   - Sign each comment with: `\\n\\n—\\nAuthored by jib`
   - You may post one combined response or multiple separate comments as appropriate

## Important Guidelines

- Process comments in order (earliest first)
- If multiple comments ask for the same thing, address them together
- If a comment asks for changes you've already made, mention that in your response
- If you make code changes, mention the commit in your response
- Be professional, helpful, and concise
- If you disagree with feedback, explain your reasoning respectfully
- ALWAYS sign your comments with `\\n\\n—\\nAuthored by jib`

## Example Response Flow

For a comment asking to "add error handling to the function":
1. Read the relevant file
2. Edit to add error handling
3. Commit: `git add -A && git commit -m "Add error handling per review feedback"`
4. Push: `git push origin {pr_branch}`
5. Comment: `gh pr comment {pr_num} --repo {repo} --body "Done! Added error handling...\\n\\n—\\nAuthored by jib"`

Now process the pending comments and take the appropriate actions."""

        print(f"  Calling Claude to process {len(pending_comments)} comment(s)...")

        # Change to repo directory if available
        cwd = repo_dir if repo_dir else Path.home() / "khan"
        result = run_agent(prompt, cwd=cwd)

        if not result.success:
            print(f"  {result.error}")
            if result.stdout:
                print(f"  Claude stdout (first 500 chars): {result.stdout[:500]}")
            return False

        print(f"  Claude response length: {len(result.stdout)} chars")
        print(f"  ✓ Claude processed {len(pending_comments)} comment(s)")

        # Send Slack notification about the processed comments
        self._notify_batch_processed(repo, pr_num, pending_comments)

        return True

    def _notify_batch_processed(self, repo: str, pr_num: int, pending_comments: list[dict]):
        """Send Slack notification about processed PR comments."""
        try:
            comment_summary = "\n".join(
                [
                    f"- {c.get('author', 'Unknown')}: {c.get('body', '')[:100]}..."
                    for c in pending_comments[:5]
                ]
            )
            if len(pending_comments) > 5:
                comment_summary += f"\n- ... and {len(pending_comments) - 5} more"

            context = NotificationContext(
                task_id=f"pr-comments-{repo.split('/')[-1]}-{pr_num}",
                source="comment-responder",
                repository=repo,
                pr_number=pr_num,
            )

            self.slack.notify_info(
                title=f"Processed {len(pending_comments)} PR Comment(s): #{pr_num}",
                body=f"**Repository**: {repo}\n**PR**: #{pr_num}\n\n**Comments addressed:**\n{comment_summary}",
                context=context,
            )
        except Exception as e:
            print(f"  Warning: Failed to send Slack notification: {e}")

    def load_pr_context(self, repo_name: str, pr_num: int) -> dict:
        """Load PR context from synced files."""
        pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
        diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        context = {
            "pr_number": pr_num,
            "title": f"PR #{pr_num}",
            "description": "",
            "url": "",
            "diff": "",
        }

        if pr_file.exists():
            context["pr_content"] = pr_file.read_text()
            # Parse key fields
            for line in context["pr_content"].split("\n"):
                if line.startswith("# PR #"):
                    context["title"] = line.replace("# ", "").strip()
                elif line.startswith("**URL**:"):
                    context["url"] = line.replace("**URL**:", "").strip()

        if diff_file.exists():
            diff_content = diff_file.read_text()
            # Truncate if too large
            if len(diff_content) > 10000:
                diff_content = diff_content[:10000] + "\n... [diff truncated]"
            context["diff"] = diff_content

        return context

    def generate_response_with_claude(
        self,
        comment: dict,
        pr_context: dict,
        all_comments: list[dict],
        repo: str,
        pr_num: int,
        writable: bool,
    ) -> dict | None:
        """Use Claude to generate an appropriate response."""

        comment_body = comment.get("body", "")
        comment_author = comment.get("author", "")

        # Build comment history
        comment_history = ""
        for c in all_comments[-10:]:  # Last 10 comments for context
            author = c.get("author", "unknown")
            body = c.get("body", "")[:500]
            is_current = c.get("id") == comment.get("id")
            marker = " <-- THIS IS THE COMMENT TO RESPOND TO" if is_current else ""
            comment_history += f"\n--- {author}{marker} ---\n{body}\n"

        # Build the prompt
        prompt = f"""You are jib, an AI software engineering agent. You need to respond to a PR comment.

CONTEXT:
- Repository: {repo}
- PR: #{pr_num}
- PR Title: {pr_context.get("title", "Unknown")}
- PR URL: {pr_context.get("url", "Unknown")}
- You have {"WRITE" if writable else "READ-ONLY"} access to this repository

PR DESCRIPTION:
{pr_context.get("pr_content", "No description available")[:2000]}

RECENT DIFF (relevant changes):
{pr_context.get("diff", "No diff available")[:3000]}

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

        print("  Calling Claude to generate response...")
        result = run_agent(prompt)

        if not result.success:
            print(f"  {result.error}")
            if result.stdout:
                print(f"  Claude stdout (first 500 chars): {result.stdout[:500]}")
            return None

        response_text = result.stdout.strip()
        print(f"  Claude response length: {len(response_text)} chars")

        # Parse JSON from response
        try:
            # Find JSON in response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response_text[start:end]
                return json.loads(json_str)
            else:
                print("  No JSON found in response")
                return None
        except json.JSONDecodeError as e:
            print(f"  Failed to parse response JSON: {e}")
            return None

    def get_pr_info(self, repo: str, pr_num: int) -> dict | None:
        """Get PR information from GitHub including branch name and state."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_num),
                    "--repo",
                    repo,
                    "--json",
                    "state,headRefName,baseRefName",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                print(f"  Failed to get PR info: {result.stderr}")
                return None
        except Exception as e:
            print(f"  Error getting PR info: {e}")
            return None

    def handle_writable_repo(
        self, pr_num: int, repo_name: str, repo: str, comment: dict, response: dict
    ):
        """Handle response for a writable repository - post comment and make changes."""
        response_text = response.get("response_text", "")
        needs_changes = response.get("needs_code_changes", False)
        change_desc = response.get("code_change_description", "")

        # Get PR info from GitHub
        pr_info = self.get_pr_info(repo, pr_num)
        if not pr_info:
            print("  Could not get PR info, skipping code changes")
            # Still post the comment
            self.post_github_comment(repo, pr_num, response_text)
            return

        pr_state = pr_info.get("state", "UNKNOWN")
        pr_branch = pr_info.get("headRefName", "")
        base_branch = pr_info.get("baseRefName", "main")

        # Find the repo directory
        repo_dir = self.find_repo_dir(repo_name)

        # If code changes needed, make them
        result_info = None
        if needs_changes and change_desc and repo_dir:
            if pr_state == "OPEN":
                # PR is still open - push to the PR's branch
                result_info = self.make_code_changes(
                    repo_dir, repo, pr_num, pr_branch, base_branch, change_desc, response_text
                )
            else:
                # PR is closed/merged - create a new branch and PR
                print(f"  PR #{pr_num} is {pr_state}, creating new PR for changes")
                result_info = self.make_code_changes_new_pr(
                    repo_dir, repo, pr_num, base_branch, change_desc, response_text
                )

            if result_info:
                if result_info.get("new_pr_url"):
                    response_text += (
                        f"\n\nI've created a new PR with the changes: {result_info['new_pr_url']}"
                    )
                elif result_info.get("branch"):
                    response_text += (
                        f"\n\nI've pushed the changes to branch `{result_info['branch']}`."
                    )

        # Post the response to GitHub (even on closed PRs, comments are fine)
        self.post_github_comment(repo, pr_num, response_text)

        print(f"  ✓ Posted response to PR #{pr_num}")
        if result_info:
            if result_info.get("new_pr_url"):
                print(f"  ✓ Created new PR: {result_info['new_pr_url']}")
            elif result_info.get("branch"):
                print(f"  ✓ Pushed changes to branch: {result_info['branch']}")

        # Send Slack notification about actions taken
        pushed_branch = result_info.get("branch") if result_info else None
        new_pr_url = result_info.get("new_pr_url") if result_info else None
        self.slack.notify_pr_comment(
            pr_number=pr_num,
            repo=repo,
            comment_author=comment.get("author", "Unknown"),
            comment_body=comment.get("body", ""),
            response_text=response_text,
            pushed_branch=pushed_branch,
            new_pr_url=new_pr_url,
        )

    def handle_readonly_repo(
        self, pr_num: int, repo_name: str, repo: str, comment: dict, response: dict
    ):
        """Handle response for read-only repository - notify via Slack."""
        response_text = response.get("response_text", "")
        needs_changes = response.get("needs_code_changes", False)
        change_desc = response.get("code_change_description", "")
        reasoning = response.get("reasoning", "")

        # Build notification body for read-only repo
        comment_author = comment.get("author", "Reviewer")
        comment_body = comment.get("body", "")

        body = f"""**Repository**: {repo} (read-only - manual action required)
**PR**: #{pr_num}
**Comment Author**: {comment_author}

## Original Comment

{comment_body}

## Suggested Response

```
{response_text}
```

## Analysis

**Reasoning**: {reasoning}"""

        if needs_changes:
            body += f"""

## Code Changes Needed

{change_desc}

**Note**: This is a read-only repository. Please make these changes manually or grant jib write access."""

        body += """

## Actions Required

1. Review the suggested response above
2. Post the response to the PR manually, or
3. Grant jib write access to this repository"""

        context = NotificationContext(
            task_id=f"readonly-pr-{repo_name}-{pr_num}",
            source="comment-responder",
            repository=repo,
            pr_number=pr_num,
        )

        self.slack.notify_action_required(
            title=f"PR Comment Response Ready: #{pr_num}",
            body=body,
            context=context,
        )

        print(f"  ✓ Created notification for PR #{pr_num} (read-only repo)")

    def find_repo_dir(self, repo_name: str) -> Path | None:
        """Find the local directory for a repository."""
        # Check common locations
        candidates = [
            self.khan_dir / repo_name,
            self.khan_dir / repo_name.replace("-", "_"),
        ]

        for candidate in candidates:
            if candidate.exists() and (candidate / ".git").exists():
                return candidate

        return None

    def make_code_changes(
        self,
        repo_dir: Path,
        repo: str,
        pr_num: int,
        pr_branch: str,
        base_branch: str,
        change_desc: str,
        context: str,
    ) -> dict | None:
        """Use Claude to make code changes and push to the PR's branch."""
        try:
            # Fetch and checkout the PR's branch
            print(f"  Checking out PR branch: {pr_branch}")
            subprocess.run(
                ["git", "fetch", "origin", pr_branch],
                check=False,
                cwd=repo_dir,
                capture_output=True,
            )
            checkout_result = subprocess.run(
                ["git", "checkout", pr_branch],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
            if checkout_result.returncode != 0:
                # Try to create tracking branch
                subprocess.run(
                    ["git", "checkout", "-b", pr_branch, f"origin/{pr_branch}"],
                    check=False,
                    cwd=repo_dir,
                    capture_output=True,
                )

            # Create prompt for Claude to make changes
            prompt = f"""Make the following code changes in the repository at {repo_dir}:

CHANGE REQUEST:
{change_desc}

CONTEXT:
{context[:1000]}

Instructions:
1. Read the relevant files
2. Make the minimal changes needed
3. The changes should be committed to the current branch: {pr_branch}

After making changes, output a JSON summary:
{{
    "files_changed": ["list", "of", "files"],
    "commit_message": "Brief commit message",
    "success": true/false
}}

Make the changes now using the available tools (Read, Edit, Write, Bash for git commands)."""

            # Use claude with full tool access for making changes
            result = run_agent(prompt, cwd=repo_dir)

            if not result.success:
                print(f"  Code change failed: {result.error}")
                return None

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if not status.stdout.strip():
                print("  No changes made")
                return None

            # Commit any uncommitted changes
            subprocess.run(["git", "add", "-A"], check=False, cwd=repo_dir, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Address PR #{pr_num} feedback\n\n{change_desc[:200]}\n\n—\nAuthored by jib",
                ],
                check=False,
                cwd=repo_dir,
                capture_output=True,
            )

            # Push to the PR's branch
            push_result = subprocess.run(
                ["git", "push", "origin", pr_branch],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if push_result.returncode != 0:
                print(f"  Push failed: {push_result.stderr}")
                return None

            return {"branch": pr_branch}

        except Exception as e:
            print(f"  Error making code changes: {e}")
            return None

    def make_code_changes_new_pr(
        self,
        repo_dir: Path,
        repo: str,
        original_pr_num: int,
        base_branch: str,
        change_desc: str,
        context: str,
    ) -> dict | None:
        """Make code changes and create a new PR (when original PR is closed)."""
        try:
            # Fetch latest base branch
            subprocess.run(
                ["git", "fetch", "origin", base_branch],
                check=False,
                cwd=repo_dir,
                capture_output=True,
            )

            # Create a new branch from base
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            new_branch = f"jib-followup-pr{original_pr_num}-{timestamp}"

            print(f"  Creating new branch: {new_branch}")
            subprocess.run(
                ["git", "checkout", "-b", new_branch, f"origin/{base_branch}"],
                check=False,
                cwd=repo_dir,
                capture_output=True,
            )

            # Create prompt for Claude to make changes
            prompt = f"""Make the following code changes in the repository at {repo_dir}:

CHANGE REQUEST:
{change_desc}

CONTEXT (from PR #{original_pr_num} feedback):
{context[:1000]}

Instructions:
1. Read the relevant files
2. Make the minimal changes needed
3. The changes should be committed to branch: {new_branch}

After making changes, output a JSON summary:
{{
    "files_changed": ["list", "of", "files"],
    "commit_message": "Brief commit message",
    "success": true/false
}}

Make the changes now using the available tools (Read, Edit, Write, Bash for git commands)."""

            # Use claude with full tool access for making changes
            result = run_agent(prompt, cwd=repo_dir)

            if not result.success:
                print(f"  Code change failed: {result.error}")
                return None

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if not status.stdout.strip():
                print("  No changes made")
                return None

            # Commit any uncommitted changes
            subprocess.run(["git", "add", "-A"], check=False, cwd=repo_dir, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Follow-up from PR #{original_pr_num}\n\n{change_desc[:200]}\n\n—\nAuthored by jib",
                ],
                check=False,
                cwd=repo_dir,
                capture_output=True,
            )

            # Push the new branch
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", new_branch],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if push_result.returncode != 0:
                print(f"  Push failed: {push_result.stderr}")
                return None

            # Create the new PR
            pr_title = f"Follow-up: {change_desc[:50]}..."
            pr_body = f"""## Follow-up from PR #{original_pr_num}

This PR addresses feedback from the original PR which has been closed/merged.

### Changes
{change_desc}

—
Authored by jib"""

            pr_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    repo,
                    "--base",
                    base_branch,
                    "--head",
                    new_branch,
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                ],
                check=False,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if pr_result.returncode != 0:
                print(f"  PR creation failed: {pr_result.stderr}")
                return {"branch": new_branch}

            pr_url = pr_result.stdout.strip()
            return {"branch": new_branch, "new_pr_url": pr_url}

        except Exception as e:
            print(f"  Error making code changes for new PR: {e}")
            return None

    def post_github_comment(self, repo: str, pr_num: int, comment_text: str):
        """Post a comment to a GitHub PR."""
        try:
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_num), "--repo", repo, "--body", comment_text],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"  Failed to post comment: {result.stderr}")
        except Exception as e:
            print(f"  Error posting comment: {e}")


def main():
    """Main entry point."""
    logger.info("Comment Responder - Starting")
    print("=" * 60)
    print("Comment Responder - Starting")
    print("=" * 60)

    try:
        responder = CommentResponder()
        responder.watch()
        print("=" * 60)
        print("Comment Responder - Completed successfully")
        print("=" * 60)
    except RuntimeError as e:
        # Expected errors (e.g., missing claude CLI)
        print("=" * 60, file=sys.stderr)
        print(f"ERROR: {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Unexpected errors
        print("=" * 60, file=sys.stderr)
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        import traceback

        traceback.print_exc()
        print("=" * 60, file=sys.stderr)
        print("If this persists, check:", file=sys.stderr)
        print("  1. GitHub authentication: gh auth status", file=sys.stderr)
        print("  2. Context sync directory: ~/context-sync/github/", file=sys.stderr)
        print("  3. Claude CLI: claude --version", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
