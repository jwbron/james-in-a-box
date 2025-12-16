"""Configuration for Gemini CLI runner."""

from dataclasses import dataclass

from llm.config import BaseConfig


@dataclass
class GeminiConfig(BaseConfig):
    """Configuration for Gemini CLI execution.

    Extends BaseConfig with Gemini-specific settings.

    Attributes:
        cwd: Working directory for Gemini CLI (inherited from BaseConfig)
        timeout: Maximum execution time in seconds (inherited from BaseConfig)
        model: Gemini model to use (default: gemini-3-pro-preview)
        sandbox: Sandbox mode (default: False - disabled in container)
    """

    model: str = "gemini-3-pro-preview"  # Default model
    sandbox: bool = False  # Disable sandbox (we're already in container)
