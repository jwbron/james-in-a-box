"""
Tool wrappers for jib-container.

Provides wrapped versions of git, gh, and claude commands with automatic
humanization of content for natural readability.

IMPORTANT: These wrappers call Claude Code and must only be used from
jib-container, not from host-services or shared code.

Usage:
    from jib_lib.wrappers import git, gh, claude

    # Create a PR with humanized title/body
    result = gh.pr_create(title="Add feature", body="Description")

    # Commit with humanized message
    result = git.commit(message="Fix bug in login")

    # Run claude with a prompt
    result = claude.prompt("Explain this code")
"""

from .claude import ClaudeWrapper
from .gh import GhWrapper
from .git import GitWrapper

# Singleton wrapper instances
git = GitWrapper()
gh = GhWrapper()
claude = ClaudeWrapper()

__all__ = [
    "ClaudeWrapper",
    "GhWrapper",
    "GitWrapper",
    "claude",
    "gh",
    "git",
]
