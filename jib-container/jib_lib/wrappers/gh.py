"""
GitHub CLI (gh) wrapper.

Wraps gh commands to capture GitHub API interactions with structured logging.

Note: Humanization is handled by the shell wrapper (scripts/gh), not here.
This allows the wrapper to be used without triggering LLM calls.
"""

import json
import re
from typing import Any

from .base import ToolResult, ToolWrapper


class GhWrapper(ToolWrapper):
    """Wrapper for the GitHub CLI (gh).

    Captures GitHub API interactions including:
    - Pull request operations
    - Issue operations
    - Repository operations

    Usage:
        from jib_logging.wrappers import gh

        # Create a PR
        result = gh.pr_create(title="Add feature", body="Description")

        # List PRs
        result = gh.pr_list(state="open")

        # View a PR
        result = gh.pr_view(123)

        # Generic command
        result = gh.run("api", "/repos/owner/repo/issues")
    """

    tool_name = "gh"

    # --- Pull Request Operations ---

    def pr_create(
        self,
        *,
        title: str,
        body: str,
        base: str | None = None,
        head: str | None = None,
        draft: bool = False,
        repo: str | None = None,
    ) -> ToolResult:
        """Create a pull request.

        Args:
            title: PR title
            body: PR body/description
            base: Base branch (default: repo default)
            head: Head branch (default: current branch)
            draft: Create as draft PR
            repo: Repository (owner/name) if not in repo dir

        Returns:
            ToolResult with PR URL in extra["pr_url"]
        """
        args: list[str] = ["pr", "create", "--title", title, "--body", body]

        if base:
            args.extend(["--base", base])

        if head:
            args.extend(["--head", head])

        if draft:
            args.append("--draft")

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_view(
        self,
        pr_number: int | str | None = None,
        *,
        json_fields: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """View a pull request.

        Args:
            pr_number: PR number (default: current branch's PR)
            json_fields: Fields to return as JSON
            repo: Repository (owner/name)

        Returns:
            ToolResult with PR details
        """
        args: list[str] = ["pr", "view"]

        if pr_number is not None:
            args.append(str(pr_number))

        if json_fields:
            args.extend(["--json", ",".join(json_fields)])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_list(
        self,
        *,
        state: str | None = None,
        base: str | None = None,
        head: str | None = None,
        author: str | None = None,
        label: str | None = None,
        limit: int | None = None,
        json_fields: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """List pull requests.

        Args:
            state: Filter by state (open, closed, merged, all)
            base: Filter by base branch
            head: Filter by head branch
            author: Filter by author
            label: Filter by label
            limit: Max number to return
            json_fields: Fields to return as JSON
            repo: Repository (owner/name)

        Returns:
            ToolResult with PR list
        """
        args: list[str] = ["pr", "list"]

        if state:
            args.extend(["--state", state])

        if base:
            args.extend(["--base", base])

        if head:
            args.extend(["--head", head])

        if author:
            args.extend(["--author", author])

        if label:
            args.extend(["--label", label])

        if limit:
            args.extend(["--limit", str(limit)])

        if json_fields:
            args.extend(["--json", ",".join(json_fields)])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_checkout(
        self,
        pr_number: int | str,
        *,
        repo: str | None = None,
    ) -> ToolResult:
        """Check out a pull request locally.

        Args:
            pr_number: PR number to checkout
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "checkout", str(pr_number)]

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_merge(
        self,
        pr_number: int | str | None = None,
        *,
        squash: bool = False,
        rebase: bool = False,
        delete_branch: bool = False,
        repo: str | None = None,
    ) -> ToolResult:
        """Merge a pull request.

        Args:
            pr_number: PR number (default: current branch's PR)
            squash: Squash commits
            rebase: Rebase commits
            delete_branch: Delete branch after merge
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "merge"]

        if pr_number is not None:
            args.append(str(pr_number))

        if squash:
            args.append("--squash")
        elif rebase:
            args.append("--rebase")

        if delete_branch:
            args.append("--delete-branch")

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_close(
        self,
        pr_number: int | str,
        *,
        comment: str | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """Close a pull request.

        Args:
            pr_number: PR number to close
            comment: Comment to leave when closing
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "close", str(pr_number)]

        if comment:
            args.extend(["--comment", comment])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_edit(
        self,
        pr_number: int | str | None = None,
        *,
        title: str | None = None,
        body: str | None = None,
        add_label: list[str] | None = None,
        remove_label: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """Edit a pull request.

        Args:
            pr_number: PR number (default: current branch's PR)
            title: New PR title
            body: New PR body
            add_label: Labels to add
            remove_label: Labels to remove
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "edit"]

        if pr_number is not None:
            args.append(str(pr_number))

        if title:
            args.extend(["--title", title])

        if body:
            args.extend(["--body", body])

        if add_label:
            for label in add_label:
                args.extend(["--add-label", label])

        if remove_label:
            for label in remove_label:
                args.extend(["--remove-label", label])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_comment(
        self,
        pr_number: int | str | None = None,
        *,
        body: str,
        repo: str | None = None,
    ) -> ToolResult:
        """Add a comment to a pull request.

        Args:
            pr_number: PR number (default: current branch's PR)
            body: Comment body
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "comment"]

        if pr_number is not None:
            args.append(str(pr_number))

        args.extend(["--body", body])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def pr_review(
        self,
        pr_number: int | str | None = None,
        *,
        body: str | None = None,
        approve: bool = False,
        request_changes: bool = False,
        comment: bool = False,
        repo: str | None = None,
    ) -> ToolResult:
        """Review a pull request.

        Args:
            pr_number: PR number (default: current branch's PR)
            body: Review body
            approve: Approve the PR
            request_changes: Request changes
            comment: Leave a comment review (not approval or request changes)
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["pr", "review"]

        if pr_number is not None:
            args.append(str(pr_number))

        if body:
            args.extend(["--body", body])

        if approve:
            args.append("--approve")
        elif request_changes:
            args.append("--request-changes")
        elif comment:
            args.append("--comment")

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    # --- Issue Operations ---

    def issue_create(
        self,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """Create an issue.

        Args:
            title: Issue title
            body: Issue body
            labels: Labels to apply
            assignees: Users to assign
            repo: Repository (owner/name)

        Returns:
            ToolResult with issue URL in extra["issue_url"]
        """
        args: list[str] = ["issue", "create", "--title", title, "--body", body]

        if labels:
            for label in labels:
                args.extend(["--label", label])

        if assignees:
            for assignee in assignees:
                args.extend(["--assignee", assignee])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def issue_view(
        self,
        issue_number: int | str,
        *,
        json_fields: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """View an issue.

        Args:
            issue_number: Issue number
            json_fields: Fields to return as JSON
            repo: Repository (owner/name)

        Returns:
            ToolResult with issue details
        """
        args: list[str] = ["issue", "view", str(issue_number)]

        if json_fields:
            args.extend(["--json", ",".join(json_fields)])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def issue_list(
        self,
        *,
        state: str | None = None,
        label: str | None = None,
        author: str | None = None,
        assignee: str | None = None,
        limit: int | None = None,
        json_fields: list[str] | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """List issues.

        Args:
            state: Filter by state (open, closed, all)
            label: Filter by label
            author: Filter by author
            assignee: Filter by assignee
            limit: Max number to return
            json_fields: Fields to return as JSON
            repo: Repository (owner/name)

        Returns:
            ToolResult with issue list
        """
        args: list[str] = ["issue", "list"]

        if state:
            args.extend(["--state", state])

        if label:
            args.extend(["--label", label])

        if author:
            args.extend(["--author", author])

        if assignee:
            args.extend(["--assignee", assignee])

        if limit:
            args.extend(["--limit", str(limit)])

        if json_fields:
            args.extend(["--json", ",".join(json_fields)])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def issue_close(
        self,
        issue_number: int | str,
        *,
        comment: str | None = None,
        reason: str | None = None,
        repo: str | None = None,
    ) -> ToolResult:
        """Close an issue.

        Args:
            issue_number: Issue number
            comment: Comment to leave when closing
            reason: Reason for closing (completed, not_planned)
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["issue", "close", str(issue_number)]

        if comment:
            args.extend(["--comment", comment])

        if reason:
            args.extend(["--reason", reason])

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    def issue_comment(
        self,
        issue_number: int | str,
        *,
        body: str,
        repo: str | None = None,
    ) -> ToolResult:
        """Add a comment to an issue.

        Args:
            issue_number: Issue number
            body: Comment body
            repo: Repository (owner/name)

        Returns:
            ToolResult
        """
        args: list[str] = ["issue", "comment", str(issue_number), "--body", body]

        if repo:
            args.extend(["--repo", repo])

        return self.run(*args)

    # --- Repository Operations ---

    def repo_view(
        self,
        repo: str | None = None,
        *,
        json_fields: list[str] | None = None,
    ) -> ToolResult:
        """View repository details.

        Args:
            repo: Repository (owner/name) or current repo if None
            json_fields: Fields to return as JSON

        Returns:
            ToolResult with repo details
        """
        args: list[str] = ["repo", "view"]

        if repo:
            args.append(repo)

        if json_fields:
            args.extend(["--json", ",".join(json_fields)])

        return self.run(*args)

    def repo_clone(
        self,
        repo: str,
        *,
        directory: str | None = None,
    ) -> ToolResult:
        """Clone a repository.

        Args:
            repo: Repository (owner/name) or URL
            directory: Target directory

        Returns:
            ToolResult
        """
        args: list[str] = ["repo", "clone", repo]

        if directory:
            args.append(directory)

        return self.run(*args)

    # --- API Operations ---

    def api(
        self,
        endpoint: str,
        *,
        method: str | None = None,
        field: dict[str, str] | None = None,
        raw_field: dict[str, str] | None = None,
        jq: str | None = None,
    ) -> ToolResult:
        """Make a GitHub API request.

        Args:
            endpoint: API endpoint (e.g., "/repos/owner/repo/issues")
            method: HTTP method (GET, POST, etc.)
            field: Form fields (strings)
            raw_field: Raw fields (JSON values)
            jq: JQ filter for output

        Returns:
            ToolResult with API response
        """
        args: list[str] = ["api", endpoint]

        if method:
            args.extend(["--method", method])

        if field:
            for key, value in field.items():
                args.extend(["-f", f"{key}={value}"])

        if raw_field:
            for key, value in raw_field.items():
                args.extend(["-F", f"{key}={value}"])

        if jq:
            args.extend(["--jq", jq])

        return self.run(*args)

    def _extract_context(
        self,
        args: tuple[str, ...],
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        """Extract gh-specific context from command and output."""
        context: dict[str, Any] = {}

        # Extract resource type and subcommand
        if len(args) >= 2:
            context["resource"] = args[0]  # pr, issue, repo, api
            context["subcommand"] = args[1]  # create, view, list, etc.

        # Extract PR/issue number from args
        for arg in args:
            if arg.isdigit():
                if "pr" in args:
                    context["pr_number"] = int(arg)
                elif "issue" in args:
                    context["issue_number"] = int(arg)
                break

        # Extract repository from --repo flag
        if "--repo" in args:
            try:
                repo_idx = args.index("--repo")
                if repo_idx + 1 < len(args):
                    context["repository"] = args[repo_idx + 1]
            except (ValueError, IndexError):
                pass

        # Parse URL from output (for create operations)
        url_match = re.search(r"https://github\.com/[^\s]+", stdout)
        if url_match:
            url = url_match.group(0)
            context["url"] = url

            # Extract PR/issue number from URL
            pr_match = re.search(r"/pull/(\d+)", url)
            if pr_match:
                context["pr_number"] = int(pr_match.group(1))
                context["pr_url"] = url

            issue_match = re.search(r"/issues/(\d+)", url)
            if issue_match:
                context["issue_number"] = int(issue_match.group(1))
                context["issue_url"] = url

        # Try to parse JSON output for more context
        if stdout.strip().startswith("{") or stdout.strip().startswith("["):
            try:
                data = json.loads(stdout)
                if isinstance(data, dict):
                    if "number" in data:
                        context["number"] = data["number"]
                    if "state" in data:
                        context["state"] = data["state"]
                    if "title" in data:
                        context["title"] = data["title"][:100]
            except json.JSONDecodeError:
                pass

        return context
