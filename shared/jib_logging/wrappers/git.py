"""
Git wrapper for jib_logging.

Wraps git commands to capture repository operations with structured logging.
"""

import re
from typing import Any

from .base import ToolResult, ToolWrapper


class GitWrapper(ToolWrapper):
    """Wrapper for git CLI operations.

    Captures repository operations including:
    - Commits
    - Push/pull
    - Branch operations
    - Status and diff

    Usage:
        from jib_logging.wrappers import git

        # Commit changes
        result = git.commit(message="Add feature X")

        # Push to remote
        result = git.push("origin", "main")

        # Check status
        result = git.status()

        # Generic command
        result = git.run("log", "--oneline", "-5")
    """

    tool_name = "git"

    def status(self, *, cwd: str | None = None) -> ToolResult:
        """Get repository status.

        Args:
            cwd: Working directory (defaults to current)

        Returns:
            ToolResult with status in stdout
        """
        return self.run("status", "--porcelain", cwd=cwd)

    def add(
        self,
        *paths: str,
        all: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Stage files for commit.

        Args:
            *paths: File paths to add
            all: Add all changes (git add -A)
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["add"]

        if all:
            args.append("-A")
        else:
            args.extend(paths)

        return self.run(*args, cwd=cwd)

    def commit(
        self,
        message: str,
        *,
        all: bool = False,
        amend: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Create a commit.

        Args:
            message: Commit message
            all: Commit all tracked changes (git commit -a)
            amend: Amend the previous commit
            cwd: Working directory

        Returns:
            ToolResult with commit SHA in extra["commit_sha"]
        """
        args: list[str] = ["commit"]

        if all:
            args.append("-a")

        if amend:
            args.append("--amend")

        args.extend(["-m", message])

        return self.run(*args, cwd=cwd)

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        *,
        set_upstream: bool = False,
        force: bool = False,
        force_with_lease: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Push commits to remote.

        Args:
            remote: Remote name (default: origin)
            branch: Branch to push (default: current branch)
            set_upstream: Set upstream branch (-u flag)
            force: Force push (dangerous!)
            force_with_lease: Force with lease (safer than force)
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["push"]

        if set_upstream:
            args.append("-u")

        if force_with_lease:
            args.append("--force-with-lease")
        elif force:
            args.append("--force")

        args.append(remote)

        if branch:
            args.append(branch)

        return self.run(*args, cwd=cwd)

    def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
        *,
        rebase: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Pull commits from remote.

        Args:
            remote: Remote name (default: origin)
            branch: Branch to pull (default: current branch)
            rebase: Rebase instead of merge
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["pull"]

        if rebase:
            args.append("--rebase")

        args.append(remote)

        if branch:
            args.append(branch)

        return self.run(*args, cwd=cwd)

    def fetch(
        self,
        remote: str = "origin",
        refspec: str | None = None,
        *,
        all: bool = False,
        prune: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Fetch from remote.

        Args:
            remote: Remote name (default: origin)
            refspec: Specific ref to fetch (e.g., "main")
            all: Fetch all remotes
            prune: Prune deleted remote branches
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["fetch"]

        if all:
            args.append("--all")

        if prune:
            args.append("--prune")

        if not all:
            args.append(remote)

        if refspec:
            args.append(refspec)

        return self.run(*args, cwd=cwd)

    def checkout(
        self,
        ref: str,
        *,
        create: bool = False,
        base: str | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        """Checkout a branch or commit.

        Args:
            ref: Branch name, tag, or commit SHA
            create: Create a new branch (-b flag)
            base: Base ref for new branch (used with create=True)
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["checkout"]

        if create:
            args.append("-b")

        args.append(ref)

        if base:
            args.append(base)

        return self.run(*args, cwd=cwd)

    def branch(
        self,
        name: str | None = None,
        *,
        delete: bool = False,
        force_delete: bool = False,
        list_all: bool = False,
        show_current: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Branch operations.

        Args:
            name: Branch name (for create/delete)
            delete: Delete the branch
            force_delete: Force delete the branch
            list_all: List all branches (including remote)
            show_current: Show current branch name only
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["branch"]

        if show_current:
            args.append("--show-current")
        elif list_all:
            args.append("-a")
        elif force_delete:
            args.extend(["-D", name or ""])
        elif delete:
            args.extend(["-d", name or ""])
        elif name:
            args.append(name)

        return self.run(*args, cwd=cwd)

    def log(
        self,
        *refs: str,
        oneline: bool = False,
        count: int | None = None,
        format: str | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        """View commit history.

        Args:
            *refs: Refs to show (branches, tags, SHAs)
            oneline: One line per commit
            count: Number of commits to show
            format: Custom format string
            cwd: Working directory

        Returns:
            ToolResult with log output
        """
        args: list[str] = ["log"]

        if oneline:
            args.append("--oneline")

        if count:
            args.append(f"-{count}")

        if format:
            args.append(f"--format={format}")

        args.extend(refs)

        return self.run(*args, cwd=cwd)

    def diff(
        self,
        *refs: str,
        cached: bool = False,
        stat: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Show changes.

        Args:
            *refs: Refs to compare
            cached: Show staged changes
            stat: Show diffstat only
            cwd: Working directory

        Returns:
            ToolResult with diff output
        """
        args: list[str] = ["diff"]

        if cached:
            args.append("--cached")

        if stat:
            args.append("--stat")

        args.extend(refs)

        return self.run(*args, cwd=cwd)

    def rev_parse(
        self,
        ref: str = "HEAD",
        *,
        short: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Get the SHA for a ref.

        Args:
            ref: Reference to resolve (default: HEAD)
            short: Return abbreviated SHA
            cwd: Working directory

        Returns:
            ToolResult with SHA in stdout
        """
        args: list[str] = ["rev-parse"]

        if short:
            args.append("--short")

        args.append(ref)

        return self.run(*args, cwd=cwd)

    def merge(
        self,
        branch: str,
        *,
        no_edit: bool = False,
        no_ff: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """Merge a branch.

        Args:
            branch: Branch to merge
            no_edit: Accept auto-generated merge message
            no_ff: Create merge commit even if fast-forward possible
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["merge"]

        if no_edit:
            args.append("--no-edit")

        if no_ff:
            args.append("--no-ff")

        args.append(branch)

        return self.run(*args, cwd=cwd)

    def remote(
        self,
        *,
        verbose: bool = False,
        cwd: str | None = None,
    ) -> ToolResult:
        """List remotes.

        Args:
            verbose: Show URLs
            cwd: Working directory

        Returns:
            ToolResult with remote list
        """
        args: list[str] = ["remote"]

        if verbose:
            args.append("-v")

        return self.run(*args, cwd=cwd)

    def _extract_context(
        self,
        args: tuple[str, ...],
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        """Extract git-specific context from command and output."""
        context: dict[str, Any] = {}

        # Extract subcommand
        if args:
            context["subcommand"] = args[0]

        # Extract commit SHA from commit output
        # Format: "[branch abc1234] Commit message"
        commit_match = re.search(r"\[[\w/-]+ ([a-f0-9]+)\]", stdout)
        if commit_match:
            context["commit_sha"] = commit_match.group(1)

        # Extract branch from checkout/branch operations
        if args and args[0] in ("checkout", "branch"):
            for arg in args[1:]:
                if not arg.startswith("-"):
                    context["branch"] = arg
                    break

        # Extract push/pull info
        if args and args[0] in ("push", "pull"):
            # Find remote (first non-flag arg after command)
            for arg in args[1:]:
                if not arg.startswith("-"):
                    context["remote"] = arg
                    break

        return context
