"""
Tool wrappers for jib_logging (shared components only).

Provides wrapped versions of command-line tools that automatically
log invocations, capture output, and record timing information.

This module only exports tools that don't call Claude Code.
For git/gh/claude wrappers with humanization, use jib-container/lib/wrappers.

Usage:
    from jib_logging.wrappers import bd

    # bd wrapper for beads task tracking
    result = bd.update("bd-abc123", status="done", notes="Completed task")
    # Automatically logs the invocation with timing

For git/gh/claude wrappers (jib-container only):
    from jib_lib.wrappers import git, gh, claude

    result = git.commit(message="Fix bug")  # Auto-humanized
    result = gh.pr_create(title="Fix", body="Desc")  # Auto-humanized
"""

from .base import ToolResult, ToolWrapper
from .bd import BdWrapper


# Singleton wrapper instances
bd = BdWrapper()

__all__ = [
    "BdWrapper",
    "ToolResult",
    "ToolWrapper",
    "bd",
]
