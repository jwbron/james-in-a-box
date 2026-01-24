"""
Natural language quality improvement for LLM output.

This module provides humanization of text to remove recognizable AI prose patterns
and improve readability. Uses the blader/humanizer Claude Code skill.

IMPORTANT: This module calls Claude Code and must only be used from jib-container,
not from host-services or shared code.

Usage:
    from jib_lib.humanizer import humanize_text, HumanizeResult

    # Humanize text (returns original on failure)
    result = humanize_text("Additionally, this is a crucial feature.")
    print(result)  # "Also, this is an important feature." (example)

    # With full result details
    from jib_lib.humanizer import humanize
    result = humanize("Text to improve")
    if result.success:
        print(result.text)
    else:
        print(f"Failed: {result.error}, using original: {result.original}")

Configuration:
    Humanization is configured via environment variables:

    JIB_HUMANIZE_ENABLED: true/false (default: true)
    JIB_HUMANIZE_MODEL: model name (default: sonnet)
    JIB_HUMANIZE_MIN_LENGTH: minimum text length (default: 50)
    JIB_HUMANIZE_FAIL_OPEN: true/false (default: true)
    JIB_HUMANIZE_TIMEOUT: timeout in seconds (default: 120)
    JIB_HUMANIZE_MAX_RETRIES: max retry attempts on timeout (default: 2)
    JIB_HUMANIZE_RETRY_DELAY: initial retry delay in seconds (default: 2.0)
"""

from .humanizer import (
    HumanizationError,
    HumanizeConfig,
    HumanizeResult,
    get_config,
    humanize,
    humanize_and_log,
    humanize_text,
)


__all__ = [
    "HumanizationError",
    "HumanizeConfig",
    "HumanizeResult",
    "get_config",
    "humanize",
    "humanize_and_log",
    "humanize_text",
]
