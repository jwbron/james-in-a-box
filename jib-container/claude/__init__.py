"""
Claude CLI utilities for jib container.

Provides a unified interface for running Claude in non-interactive mode,
with streaming output by default for visibility into long-running tasks.

Note: This module is only available inside the jib container, since Claude
CLI is only installed there. Do not import this from shared/ or host code.

Usage:
    from claude import run_claude, is_claude_available, ClaudeResult

    # Check if Claude is available
    if not is_claude_available():
        print("Claude CLI not found")
        return

    # Run Claude with a prompt (streams to stdout by default)
    result = run_claude(
        prompt="Analyze this code and suggest improvements",
        timeout=300,
        cwd="/path/to/repo",
    )

    if result.success:
        print("Claude completed successfully")
    else:
        print(f"Error: {result.error}")
        print(f"Stderr: {result.stderr}")

    # Run Claude without streaming (silent/buffered mode)
    result = run_claude(
        prompt="Fix the bug in main.py",
        stream=False,  # Buffer output, don't print during execution
    )
    print(result.stdout)  # Access output after completion

    # Run Claude with streaming and a prefix
    result = run_claude(
        prompt="Analyze the codebase",
        stream_prefix="[claude] ",  # Prefix each line
    )

    # Custom callback for each line (e.g., for logging)
    def log_line(line: str):
        logger.info("Claude output", line=line.strip())

    result = run_claude(
        prompt="Run the tests",
        on_output=log_line,
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
)


__all__ = [
    "ClaudeResult",
    "is_claude_available",
    "run_claude",
]
