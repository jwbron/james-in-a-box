"""
Unified LLM runner for both interactive and programmatic modes.

This module provides a single interface for running LLM agents,
automatically selecting the appropriate provider based on configuration.

Usage:
    from llm import run_agent, run_interactive, LLMConfig

    # Programmatic mode (async under the hood)
    result = run_agent("Analyze this code", cwd="/path/to/repo")

    # Interactive mode (replaces current process)
    run_interactive()  # Uses config from environment
"""

import os
from collections.abc import Callable
from pathlib import Path

from llm.config import LLMConfig, Provider
from llm.result import AgentResult


# =============================================================================
# Interactive Mode
# =============================================================================


def run_interactive(config: LLMConfig | None = None) -> None:
    """Launch the appropriate LLM CLI in interactive mode.

    This function does not return - it replaces the current process
    with the LLM CLI (claude or gemini).

    Args:
        config: LLM configuration. If None, uses defaults from environment.

    Example:
        from llm import run_interactive, LLMConfig, Provider

        # Use environment defaults
        run_interactive()

        # Force Gemini with specific model
        run_interactive(LLMConfig(provider=Provider.GOOGLE, model="gemini-2.5-pro"))
    """
    config = config or LLMConfig()

    if config.provider == Provider.GOOGLE:
        _launch_gemini_interactive(config)
    else:
        _launch_claude_interactive(config)


def _launch_claude_interactive(config: LLMConfig) -> None:
    """Launch Claude Code CLI in interactive mode."""
    cmd = ["claude", "--dangerously-skip-permissions", "--model", "opus"]

    # Set up environment for Claude
    env = os.environ.copy()

    # Ensure router environment is set if using router
    if os.environ.get("ANTHROPIC_BASE_URL"):
        env["ANTHROPIC_BASE_URL"] = os.environ["ANTHROPIC_BASE_URL"]
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        env["ANTHROPIC_AUTH_TOKEN"] = os.environ["ANTHROPIC_AUTH_TOKEN"]

    env.setdefault("DISABLE_TELEMETRY", "1")
    env.setdefault("DISABLE_COST_WARNINGS", "1")
    env.setdefault("NO_PROXY", "127.0.0.1")

    print("[llm] Launching Claude Code with Opus 4.5...")
    os.execvpe(cmd[0], cmd, env)


def _launch_gemini_interactive(config: LLMConfig) -> None:
    """Launch Gemini CLI in interactive mode."""
    model = config.get_model()

    cmd = ["gemini"]

    # Add model flag
    if model:
        cmd.extend(["--model", model])

    # Add sandbox flag (we're already in a container)
    if not config.sandbox:
        cmd.append("--sandbox=false")

    # Auto-accept all tool calls (like Claude's --dangerously-skip-permissions)
    cmd.append("--yolo")

    # Set up environment for Gemini
    env = os.environ.copy()

    # Ensure API key is set - Gemini CLI will auto-use GEMINI_API_KEY
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    if google_key:
        env["GOOGLE_API_KEY"] = google_key
        env["GEMINI_API_KEY"] = google_key

    # Disable telemetry in container
    env["GEMINI_DISABLE_TELEMETRY"] = "1"

    print(f"[llm] Launching Gemini CLI with model: {model}...")
    print("[llm] Note: If prompted for auth, select 'Use Gemini API Key'")
    os.execvpe(cmd[0], cmd, env)


# =============================================================================
# Programmatic Mode (Async)
# =============================================================================


async def run_agent_async(
    prompt: str,
    *,
    config: LLMConfig | None = None,
    cwd: Path | str | None = None,
    timeout: int | None = None,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run agent with the configured LLM provider.

    Automatically selects Claude or Gemini based on config.provider.

    Args:
        prompt: The prompt to send to the agent
        config: LLM configuration. If None, uses defaults from environment.
        cwd: Working directory (overrides config.cwd)
        timeout: Maximum execution time in seconds (overrides config.timeout)
        on_output: Optional callback for streaming output

    Returns:
        AgentResult with response and status

    Example:
        result = await run_agent_async("Fix the bug in main.py", cwd="/path/to/repo")
        if result.success:
            print(result.stdout)
    """
    config = config or LLMConfig()

    # Allow overrides
    if cwd is not None:
        config.cwd = cwd
    if timeout is not None:
        config.timeout = timeout

    if config.provider == Provider.GOOGLE:
        return await _run_gemini_async(prompt, config, on_output)
    else:
        return await _run_claude_async(prompt, config, on_output)


async def _run_claude_async(
    prompt: str,
    config: LLMConfig,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run Claude Code via the Claude Agent SDK."""
    # Convert to Claude-specific config
    from llm.claude.config import ClaudeConfig
    from llm.claude.runner import run_agent_async as claude_run

    claude_config = ClaudeConfig(
        cwd=config.cwd,
        timeout=config.timeout,
    )

    return await claude_run(prompt, config=claude_config, on_output=on_output)


async def _run_gemini_async(
    prompt: str,
    config: LLMConfig,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run Gemini CLI via subprocess."""
    # Convert to Gemini-specific config
    from llm.gemini.config import GeminiConfig
    from llm.gemini.runner import run_agent_async as gemini_run

    gemini_config = GeminiConfig(
        cwd=config.cwd,
        timeout=config.timeout,
        model=config.get_model(),
        sandbox=config.sandbox,
    )

    return await gemini_run(prompt, config=gemini_config, on_output=on_output)


def run_agent(
    prompt: str,
    *,
    config: LLMConfig | None = None,
    cwd: Path | str | None = None,
    timeout: int | None = None,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Synchronous wrapper for run_agent_async.

    See run_agent_async for full documentation.
    """
    import asyncio

    return asyncio.run(
        run_agent_async(prompt, config=config, cwd=cwd, timeout=timeout, on_output=on_output)
    )
