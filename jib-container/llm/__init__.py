"""
Unified LLM interface for jib container.

This module provides a single entry point for running LLM agents,
automatically selecting the appropriate provider based on configuration.

Usage:
    from llm import run_agent, run_interactive, LLMConfig, Provider

    # Programmatic mode - automatically uses configured provider
    result = run_agent(
        prompt="Analyze this code",
        cwd="/path/to/repo",
        timeout=300,
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")

    # Interactive mode - launches CLI
    run_interactive()

Configuration:
    The LLMConfig class provides unified configuration for both modes:

    config = LLMConfig(
        provider=Provider.GOOGLE,  # or ANTHROPIC, OPENAI
        model="gemini-3-pro-preview",
        cwd="/path/to/repo",
        timeout=3600,
    )

    result = run_agent("Fix the bug", config=config)
    # or
    run_interactive(config=config)

Environment Variables:
    LLM_PROVIDER=anthropic  -> Claude Code (default)
    LLM_PROVIDER=google     -> Gemini CLI
    LLM_PROVIDER=gemini     -> Gemini CLI
    LLM_PROVIDER=openai     -> Claude Code + router
    GEMINI_MODEL            -> Override default Gemini model
"""

from llm.config import LLMConfig, Provider, get_provider
from llm.result import AgentResult, ClaudeResult
from llm.runner import run_agent, run_agent_async, run_interactive


__all__ = [
    "AgentResult",
    "ClaudeResult",
    "LLMConfig",
    "Provider",
    "get_provider",
    "run_agent",
    "run_agent_async",
    "run_interactive",
]

# Backward compatibility
BaseConfig = LLMConfig
