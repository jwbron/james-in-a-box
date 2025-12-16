"""
Gemini CLI utilities for jib container.

Provides an interface for running Gemini CLI directly,
bypassing claude-code-router for native Google Gemini support.

Note: This module requires the Gemini CLI to be installed.

Usage:
    from llm.gemini import run_agent

    result = run_agent(
        prompt="Analyze this code and suggest improvements",
        timeout=300,
        cwd="/path/to/repo",
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")
"""

from llm.gemini.config import GeminiConfig
from llm.gemini.runner import run_agent, run_agent_async

# Re-export AgentResult from llm.result
from llm.result import AgentResult


__all__ = [
    "AgentResult",
    "GeminiConfig",
    "run_agent",
    "run_agent_async",
]
