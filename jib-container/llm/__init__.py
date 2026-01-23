"""
Unified LLM interface for jib container.

This module provides a single entry point for running LLM agents
using Claude via the Claude Agent SDK.

Usage:
    from llm import run_agent, run_interactive, LLMConfig

    # Programmatic mode
    result = run_agent(
        prompt="Analyze this code",
        cwd="/path/to/repo",
        timeout=300,
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")

    # Interactive mode - launches Claude CLI
    run_interactive()
"""

from llm.config import LLMConfig
from llm.result import AgentResult, ClaudeResult
from llm.runner import run_agent, run_agent_async, run_interactive


__all__ = [
    "AgentResult",
    "ClaudeResult",
    "LLMConfig",
    "run_agent",
    "run_agent_async",
    "run_interactive",
]

# Backward compatibility
BaseConfig = LLMConfig
