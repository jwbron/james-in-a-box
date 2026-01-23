"""Unified configuration for the LLM module."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LLMConfig:
    """Configuration for LLM operations.

    This config is used for both interactive and programmatic (async) modes.

    Attributes:
        cwd: Working directory for the agent
        timeout: Maximum execution time in seconds (default: 2 hours)
    """

    cwd: Path | str | None = None
    timeout: int = 7200  # 2 hours


# Backward compatibility alias
BaseConfig = LLMConfig
