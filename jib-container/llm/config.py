"""Unified configuration for LLM providers."""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Provider(Enum):
    """Available LLM providers."""

    ANTHROPIC = "anthropic"  # Claude Code
    GOOGLE = "google"  # Gemini CLI
    OPENAI = "openai"  # Claude Code + router


@dataclass
class LLMConfig:
    """Unified configuration for all LLM operations.

    This config is used for both interactive and programmatic (async) modes.

    Attributes:
        provider: Which LLM provider to use (default: from LLM_PROVIDER env)
        model: Model to use (provider-specific defaults if not set)
        cwd: Working directory for the agent
        timeout: Maximum execution time in seconds (default: 2 hours)
        sandbox: Whether to enable sandbox mode (Gemini-specific, default: False)

    Environment Variables:
        LLM_PROVIDER: Provider selection (anthropic, google, gemini, openai)
        GEMINI_MODEL: Override default Gemini model
        ANTHROPIC_BASE_URL: Router URL for Claude
        GOOGLE_API_KEY: API key for Gemini
    """

    provider: Provider = field(default_factory=lambda: _get_default_provider())
    model: str | None = None  # None = use provider default
    cwd: Path | str | None = None
    timeout: int = 7200  # 2 hours
    sandbox: bool = False  # Gemini sandbox mode (disabled in container)

    def get_model(self) -> str:
        """Get the model to use, with provider-specific defaults."""
        if self.model:
            return self.model

        # Check environment override
        env_model = os.environ.get("GEMINI_MODEL") if self.provider == Provider.GOOGLE else None
        if env_model:
            return env_model

        # Provider defaults
        if self.provider == Provider.GOOGLE:
            return "gemini-3-pro-preview"
        else:
            # Claude uses its own default (claude-sonnet-4-20250514)
            return ""


def _get_default_provider() -> Provider:
    """Get default provider from environment."""
    provider_str = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider_str in ("google", "gemini"):
        return Provider.GOOGLE
    elif provider_str == "openai":
        return Provider.OPENAI
    else:
        return Provider.ANTHROPIC


def get_provider() -> Provider:
    """Get current LLM provider from environment.

    Returns:
        Provider enum value
    """
    return _get_default_provider()


# Backward compatibility alias
BaseConfig = LLMConfig
