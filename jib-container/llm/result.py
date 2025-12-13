"""Shared result type for all LLM providers."""

from dataclasses import dataclass


@dataclass
class AgentResult:
    """Result of an agent invocation.

    This is the common return type for all LLM providers (Claude, Gemini, etc.)

    Attributes:
        success: True if agent completed successfully
        stdout: Standard output / response text
        stderr: Error output (if any)
        returncode: Exit code (0 = success)
        error: Human-readable error message if something went wrong
    """

    success: bool
    stdout: str
    stderr: str
    returncode: int
    error: str | None = None


# Backward compatibility alias
ClaudeResult = AgentResult
