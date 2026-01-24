"""
Natural language quality improvement for LLM output.

This module provides humanization of text to remove recognizable AI prose patterns
and improve readability. Uses the blader/humanizer Claude Code skill.

Usage:
    from jib_humanizer import humanize_text, HumanizeResult

    # Humanize text (returns original on failure)
    result = humanize_text("Additionally, this is a crucial feature.")
    print(result)  # "Also, this is an important feature." (example)

    # With full result details
    from jib_humanizer import humanize
    result = humanize("Text to improve")
    if result.success:
        print(result.text)
    else:
        print(f"Failed: {result.error}, using original: {result.original}")

Configuration:
    Humanization is configured in repositories.yaml:

    humanize:
      enabled: true         # Default: true
      model: sonnet         # Model for rewriting
      min_length: 50        # Skip for very short text
      fail_open: true       # Allow original on failure
"""

from .humanizer import (
    HumanizationError,
    HumanizeResult,
    get_config,
    humanize,
    humanize_and_log,
    humanize_text,
)

__all__ = [
    "HumanizationError",
    "HumanizeResult",
    "get_config",
    "humanize",
    "humanize_and_log",
    "humanize_text",
]
