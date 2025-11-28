"""
Tool wrappers for jib_logging.

Provides wrapped versions of critical command-line tools that automatically
log invocations, capture output, and record timing information.

Usage:
    from jib_logging.wrappers import bd, git, gh

    # Instead of subprocess.run(["git", "push", "origin", "main"])
    result = git.push("origin", "main")
    # Automatically logs the invocation with timing

    # bd wrapper for beads task tracking
    result = bd.update("bd-abc123", status="done", notes="Completed task")

    # gh wrapper for GitHub CLI
    result = gh.pr_create(title="Fix bug", body="Description")

Wrapped tools:
    - bd: Beads task tracking
    - git: Git operations
    - gh: GitHub CLI
    - claude: Claude Code invocations
"""

from .base import ToolResult, ToolWrapper
from .bd import BdWrapper
from .claude import ClaudeWrapper
from .gh import GhWrapper
from .git import GitWrapper

# Singleton wrapper instances
bd = BdWrapper()
git = GitWrapper()
gh = GhWrapper()
claude = ClaudeWrapper()

__all__ = [
    "BdWrapper",
    "ClaudeWrapper",
    "GhWrapper",
    "GitWrapper",
    "ToolResult",
    "ToolWrapper",
    "bd",
    "claude",
    "gh",
    "git",
]
