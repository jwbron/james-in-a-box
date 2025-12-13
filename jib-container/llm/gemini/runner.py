"""
Gemini CLI runner for non-interactive mode.

This module provides functions for running Gemini CLI,
which provides native access to Google's Gemini models.

Supports both synchronous and asynchronous execution with streaming output.
"""

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from llm.gemini.config import GeminiConfig
from llm.result import AgentResult


async def run_agent_async(
    prompt: str,
    *,
    config: GeminiConfig | None = None,
    timeout: int | None = None,
    cwd: Path | str | None = None,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run Gemini CLI with a prompt.

    Args:
        prompt: The prompt to send to Gemini
        config: Agent configuration (uses defaults if None)
        timeout: Override config timeout (seconds)
        cwd: Working directory for the agent
        on_output: Optional callback for streaming output line-by-line

    Returns:
        AgentResult with response and status

    Example:
        result = await run_agent_async(
            prompt="Fix the bug in main.py",
            cwd=Path.home() / "khan" / "my-repo",
        )
        if result.success:
            print("Agent completed successfully")
        else:
            print(f"Error: {result.error}")
    """
    config = config or GeminiConfig()
    timeout = timeout or config.timeout
    cwd = cwd or config.cwd or Path.cwd()

    # Ensure GOOGLE_API_KEY is set
    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        return AgentResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error="GOOGLE_API_KEY or GEMINI_API_KEY not set",
        )

    # Build command - use -p for non-interactive mode, --yolo to skip permissions
    cmd = [
        "gemini",
        "-p",
        prompt,  # Non-interactive mode with prompt
        "--yolo",  # Skip all permission prompts (like Claude's --dangerously-skip-permissions)
    ]

    # Add model if specified
    if config.model:
        cmd.extend(["--model", config.model])

    # Add sandbox setting
    if not config.sandbox:
        cmd.append("--sandbox=false")

    stdout_parts: list[str] = []

    try:
        # Run via subprocess with streaming
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env={**os.environ},
        )

        async def read_stream(stream, parts_list, callback):
            """Read from stream and accumulate output."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                parts_list.append(decoded)
                if callback:
                    callback(decoded)

        stderr_parts: list[str] = []

        # Read stdout and stderr concurrently with timeout
        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(
                    read_stream(process.stdout, stdout_parts, on_output),
                    read_stream(process.stderr, stderr_parts, None),
                )
                await process.wait()
        except TimeoutError:
            process.kill()
            await process.wait()
            return AgentResult(
                success=False,
                stdout="\n".join(stdout_parts),
                stderr="\n".join(stderr_parts),
                returncode=-1,
                error=f"Timed out after {timeout} seconds",
            )

        success = process.returncode == 0
        return AgentResult(
            success=success,
            stdout="\n".join(stdout_parts),
            stderr="\n".join(stderr_parts),
            returncode=process.returncode,
            error=None if success else f"Gemini CLI exited with code {process.returncode}",
        )

    except FileNotFoundError:
        return AgentResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error="Gemini CLI not found. Install with: npm install -g @google/gemini-cli",
        )

    except Exception as e:
        return AgentResult(
            success=False,
            stdout="\n".join(stdout_parts),
            stderr=str(e),
            returncode=-1,
            error=str(e),
        )


def run_agent(
    prompt: str,
    **kwargs,
) -> AgentResult:
    """Synchronous wrapper for run_agent_async.

    See run_agent_async for full documentation.

    Example:
        result = run_agent("Explain the codebase", cwd="/path/to/repo")
        print(result.stdout)
    """
    return asyncio.run(run_agent_async(prompt, **kwargs))
