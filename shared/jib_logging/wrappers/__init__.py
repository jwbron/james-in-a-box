"""
Tool wrappers for jib_logging.

Provides wrapped versions of critical command-line tools that automatically
log invocations, capture output, and record timing information.

Usage:
    from jib_logging.wrappers import bd, claude

    # bd wrapper for beads task tracking
    result = bd.update("bd-abc123", status="done", notes="Completed task")

    # claude wrapper for Claude Code invocations
    result = claude.run("--print", "-p", "Explain this code")

Wrapped tools:
    - bd: Beads task tracking
    - claude: Claude Code invocations

Note: git/gh wrappers were removed as they were never adopted. The gateway
sidecar has purpose-built clients for git/gh with security validation.
See ADR-Standardized-Logging-Interface for details.
"""

from .base import ToolResult, ToolWrapper
from .bd import BdWrapper
from .claude import ClaudeWrapper


# Singleton wrapper instances
bd = BdWrapper()
claude = ClaudeWrapper()

__all__ = [
    "BdWrapper",
    "ClaudeWrapper",
    "ToolResult",
    "ToolWrapper",
    "bd",
    "claude",
]
