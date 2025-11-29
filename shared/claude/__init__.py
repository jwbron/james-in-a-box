"""
Shared Claude CLI utilities for jib.

Provides a unified interface for running Claude in non-interactive mode,
with support for both buffered and streaming output.

Usage:
    from shared.claude import run_claude, is_claude_available, ClaudeResult

    # Check if Claude is available
    if not is_claude_available():
        print("Claude CLI not found")
        return

    # Run Claude with a prompt (buffered output)
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

    # Run Claude with streaming output (see output in real-time)
    result = run_claude(
        prompt="Fix the bug in main.py",
        stream=True,  # Stream to stdout as it arrives
    )

    # Run Claude with streaming and a prefix
    result = run_claude(
        prompt="Analyze the codebase",
        stream=True,
        stream_prefix="[claude] ",  # Prefix each line
    )

    # Run Claude with jib_logging integration
    from shared.claude import run_claude_with_logging

    result = run_claude_with_logging(
        prompt="Run the tests",
        logger_name="my-service",
    )

Threading/Non-Interactive Mode:
    - All calls use --dangerously-skip-permissions flag
    - Input is passed via stdin (not --print flag which creates restricted session)
    - This allows full access to tools and filesystem
"""

from .runner import (
    ClaudeResult,
    is_claude_available,
    run_claude,
    run_claude_with_logging,
)


__all__ = [
    "ClaudeResult",
    "is_claude_available",
    "run_claude",
    "run_claude_with_logging",
]
