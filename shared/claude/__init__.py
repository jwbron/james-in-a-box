"""
Shared Claude CLI utilities for jib.

Provides a unified interface for running Claude in non-interactive mode.

Usage:
    from shared.claude import run_claude, is_claude_available, ClaudeResult

    # Check if Claude is available
    if not is_claude_available():
        print("Claude CLI not found")
        return

    # Run Claude with a prompt
    result = run_claude(
        prompt="Analyze this code and suggest improvements",
        timeout=300,
        cwd="/path/to/repo",
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")
        print(f"Stderr: {result.stderr}")

Threading/Non-Interactive Mode:
    - All calls use --dangerously-skip-permissions flag
    - Input is passed via stdin (not --print flag which creates restricted session)
    - This allows full access to tools and filesystem
"""

from .runner import (
    ClaudeResult,
    is_claude_available,
    run_claude,
)

__all__ = [
    "ClaudeResult",
    "is_claude_available",
    "run_claude",
]
