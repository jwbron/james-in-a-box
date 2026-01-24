"""
Natural language quality improvement using the humanizer skill.

This module rewrites LLM-generated text to remove recognizable AI prose patterns
and improve natural readability. Uses the blader/humanizer Claude Code skill.

The goal is better writing quality, not deception. A PR from james-in-a-box[bot]
should still be clearly bot-authored - it should just be well-written.
"""

import logging
import os
import subprocess
from dataclasses import dataclass


logger = logging.getLogger(__name__)


class HumanizationError(Exception):
    """Raised when humanization fails."""


@dataclass
class HumanizeResult:
    """Result from humanization attempt.

    Attributes:
        success: Whether humanization succeeded
        text: The humanized text (or original if failed and fail_open=True)
        original: The original input text
        error: Error message if humanization failed
    """

    success: bool
    text: str
    original: str
    error: str | None = None


@dataclass
class HumanizeConfig:
    """Configuration for humanization.

    Attributes:
        enabled: Whether humanization is enabled
        model: Model to use for rewriting (default: sonnet)
        min_length: Skip humanization for text shorter than this
        fail_open: If True, return original text on failure
        timeout: Timeout in seconds for Claude Code invocation
    """

    enabled: bool = True
    model: str = "sonnet"
    min_length: int = 50
    fail_open: bool = True
    timeout: int = 60


def get_config() -> HumanizeConfig:
    """Get humanization configuration.

    Reads from environment variables with JIB_HUMANIZE_ prefix:
    - JIB_HUMANIZE_ENABLED: "true" or "false" (default: true)
    - JIB_HUMANIZE_MODEL: model name (default: sonnet)
    - JIB_HUMANIZE_MIN_LENGTH: minimum text length (default: 50)
    - JIB_HUMANIZE_FAIL_OPEN: "true" or "false" (default: true)
    - JIB_HUMANIZE_TIMEOUT: timeout in seconds (default: 60)

    Returns:
        HumanizeConfig with current settings
    """
    return HumanizeConfig(
        enabled=os.environ.get("JIB_HUMANIZE_ENABLED", "true").lower() == "true",
        model=os.environ.get("JIB_HUMANIZE_MODEL", "sonnet"),
        min_length=int(os.environ.get("JIB_HUMANIZE_MIN_LENGTH", "50")),
        fail_open=os.environ.get("JIB_HUMANIZE_FAIL_OPEN", "true").lower() == "true",
        timeout=int(os.environ.get("JIB_HUMANIZE_TIMEOUT", "60")),
    )


def humanize(text: str, fail_open: bool | None = None) -> HumanizeResult:
    """Humanize text with configurable failure mode.

    Invokes Claude Code with the /humanizer skill to rewrite text for natural
    readability. The humanizer skill is installed at ~/.claude/skills/humanizer
    and removes AI prose patterns while preserving meaning.

    Args:
        text: Text to humanize
        fail_open: If True, return original text on failure (default from config).
                   If False, raise HumanizationError on failure.

    Returns:
        HumanizeResult with success status and text

    Raises:
        HumanizationError: If fail_open=False and humanization fails
    """
    config = get_config()

    # Use config default if not specified
    if fail_open is None:
        fail_open = config.fail_open

    # Skip if disabled
    if not config.enabled:
        return HumanizeResult(success=True, text=text, original=text)

    # Skip short text
    if len(text) < config.min_length:
        logger.debug(
            "Skipping humanization for short text",
            extra={"text_length": len(text), "min_length": config.min_length},
        )
        return HumanizeResult(success=True, text=text, original=text)

    try:
        # Invoke Claude Code with the humanizer skill
        # The skill is installed at ~/.claude/skills/humanizer
        # Request only the rewritten text, no explanations
        prompt = f'/humanizer\n\nRewrite this text to remove AI patterns. Output ONLY the rewritten text, nothing else - no explanations, no markdown formatting, no "here is" prefix:\n\n{text}'

        result = subprocess.run(
            [
                "claude",
                "--print",  # Output response only
                "--model",
                config.model,
                "--max-turns",
                "5",  # Skill needs multiple turns to process
                "-p",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )

        if result.returncode != 0:
            error_msg = f"Claude Code failed with exit code {result.returncode}: {result.stderr}"
            raise HumanizationError(error_msg)

        humanized = result.stdout.strip()

        # Sanity check: don't return empty text
        if not humanized:
            error_msg = "Claude Code returned empty response"
            raise HumanizationError(error_msg)

        return HumanizeResult(success=True, text=humanized, original=text)

    except subprocess.TimeoutExpired as e:
        error_msg = f"Humanization timed out after {config.timeout}s"
        logger.error(error_msg)
        if fail_open:
            return HumanizeResult(success=False, text=text, original=text, error=error_msg)
        raise HumanizationError(error_msg) from e

    except HumanizationError as e:
        if fail_open:
            return HumanizeResult(
                success=False,
                text=text,
                original=text,
                error=str(e),
            )
        raise

    except Exception as e:
        error_msg = f"Humanization failed: {e}"
        logger.error(error_msg, exc_info=True)
        if fail_open:
            return HumanizeResult(success=False, text=text, original=text, error=error_msg)
        raise HumanizationError(error_msg) from e


def humanize_text(text: str) -> str:
    """Humanize text, returning the result or original on failure.

    This is a convenience function that always fails open - if humanization
    fails for any reason, the original text is returned.

    Args:
        text: Text to humanize

    Returns:
        Humanized text, or original if humanization failed
    """
    result = humanize(text, fail_open=True)
    return result.text


def humanize_and_log(text: str, context: str) -> str:
    """Humanize text and log the result.

    Logs humanization success/failure and diffs for debugging.

    Args:
        text: Text to humanize
        context: Context string for logging (e.g., "PR title", "commit message")

    Returns:
        Humanized text, or original if humanization failed
    """
    result = humanize(text, fail_open=True)

    if result.success and result.text != result.original:
        logger.info(
            f"Humanized {context}",
            extra={
                "context": context,
                "original_length": len(result.original),
                "humanized_length": len(result.text),
            },
        )
        logger.debug(
            "Humanization diff",
            extra={
                "context": context,
                "original": result.original,
                "humanized": result.text,
            },
        )
    elif not result.success:
        logger.warning(
            f"Humanization failed for {context}",
            extra={
                "context": context,
                "error": result.error,
            },
        )

    return result.text
