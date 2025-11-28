"""
Claude Runner - Shared module for invoking Claude in non-interactive mode.

This module provides a consistent interface for invoking Claude Code CLI
across all jib tasks (both container-side and host-side).

Usage:
    from claude_runner import run_claude, ClaudeResult

    result = run_claude(
        prompt="Your prompt here",
        timeout=300,
        cwd="/path/to/working/dir",
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")
"""

from .runner import (
    ClaudeResult,
    check_claude_cli,
    run_claude,
)

__all__ = [
    "run_claude",
    "check_claude_cli",
    "ClaudeResult",
]
