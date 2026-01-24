"""
Natural language quality improvement using the humanizer skill.

This module rewrites LLM-generated text to remove recognizable AI prose patterns
and improve natural readability. Uses the blader/humanizer Claude Code skill.

The goal is better writing quality, not deception. A PR from james-in-a-box[bot]
should still be clearly bot-authored - it should just be well-written.
"""

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass


logger = logging.getLogger(__name__)

# Patterns that indicate the model didn't understand the request
# and is asking for clarification instead of humanizing
INVALID_RESPONSE_PATTERNS = [
    r"I need to see",
    r"Could you provide",
    r"Can you (please )?provide",
    r"I don't see",
    r"You've only shown",
    r"Please (provide|share)",
    r"What text would you like",
    r"I can help.*but",
]


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
        max_retries: Maximum number of retry attempts on timeout
        retry_delay: Initial delay between retries in seconds (doubles each retry)
    """

    enabled: bool = True
    model: str = "sonnet"
    min_length: int = 50
    fail_open: bool = True
    timeout: int = 120  # Increased from 60s for subprocess cold starts
    max_retries: int = 2
    retry_delay: float = 2.0


def get_config() -> HumanizeConfig:
    """Get humanization configuration.

    Reads from environment variables with JIB_HUMANIZE_ prefix:
    - JIB_HUMANIZE_ENABLED: "true" or "false" (default: true)
    - JIB_HUMANIZE_MODEL: model name (default: sonnet)
    - JIB_HUMANIZE_MIN_LENGTH: minimum text length (default: 50)
    - JIB_HUMANIZE_FAIL_OPEN: "true" or "false" (default: true)
    - JIB_HUMANIZE_TIMEOUT: timeout in seconds (default: 120)
    - JIB_HUMANIZE_MAX_RETRIES: max retry attempts on timeout (default: 2)
    - JIB_HUMANIZE_RETRY_DELAY: initial retry delay in seconds (default: 2.0)

    Returns:
        HumanizeConfig with current settings
    """
    return HumanizeConfig(
        enabled=os.environ.get("JIB_HUMANIZE_ENABLED", "true").lower() == "true",
        model=os.environ.get("JIB_HUMANIZE_MODEL", "sonnet"),
        min_length=int(os.environ.get("JIB_HUMANIZE_MIN_LENGTH", "50")),
        fail_open=os.environ.get("JIB_HUMANIZE_FAIL_OPEN", "true").lower() == "true",
        timeout=int(os.environ.get("JIB_HUMANIZE_TIMEOUT", "120")),
        max_retries=int(os.environ.get("JIB_HUMANIZE_MAX_RETRIES", "2")),
        retry_delay=float(os.environ.get("JIB_HUMANIZE_RETRY_DELAY", "2.0")),
    )


def _is_invalid_response(response: str) -> bool:
    """Check if the response indicates the model didn't understand the request.

    Some responses indicate the model is asking for clarification instead of
    humanizing the text. This happens especially with short text like titles.

    Args:
        response: The model's response text

    Returns:
        True if the response appears to be a clarification request, not humanized text
    """
    return any(
        re.search(pattern, response, re.IGNORECASE)
        for pattern in INVALID_RESPONSE_PATTERNS
    )


def _build_prompt(text: str) -> str:
    """Build the humanization prompt with context-aware instructions.

    For short text (like titles), we provide more explicit instructions to
    prevent the model from asking for more context.

    Args:
        text: The text to humanize

    Returns:
        The prompt string to send to Claude Code
    """
    # For short text, add explicit instructions
    if len(text) < 200:
        return f'''/humanizer

Rewrite this text to remove AI patterns. This may be a title, commit message, or short description - that's fine, just rewrite it.

IMPORTANT: Output ONLY the rewritten text. No explanations, no questions, no "here is" prefix. If you can't improve it, output the original text unchanged.

Text to rewrite:
{text}'''
    else:
        return f'''/humanizer

Rewrite this text to remove AI patterns. Output ONLY the rewritten text, nothing else - no explanations, no markdown formatting, no "here is" prefix:

{text}'''


def _invoke_claude(prompt: str, config: HumanizeConfig) -> str:
    """Invoke Claude Code with the humanizer skill.

    Args:
        prompt: The prompt to send
        config: Humanization configuration

    Returns:
        The humanized text

    Raises:
        HumanizationError: If invocation fails
        subprocess.TimeoutExpired: If timeout is exceeded
    """
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
        check=False,  # We handle errors ourselves
    )

    if result.returncode != 0:
        error_msg = f"Claude Code failed with exit code {result.returncode}: {result.stderr}"
        raise HumanizationError(error_msg)

    humanized = result.stdout.strip()

    # Sanity check: don't return empty text
    if not humanized:
        raise HumanizationError("Claude Code returned empty response")

    # Check for invalid responses (model asking for clarification)
    if _is_invalid_response(humanized):
        raise HumanizationError(f"Model asked for clarification instead of humanizing: {humanized[:100]}...")

    return humanized


def humanize(text: str, fail_open: bool | None = None) -> HumanizeResult:
    """Humanize text with configurable failure mode.

    Invokes Claude Code with the /humanizer skill to rewrite text for natural
    readability. The humanizer skill is installed at ~/.claude/skills/humanizer
    and removes AI prose patterns while preserving meaning.

    Includes retry logic with exponential backoff for timeout errors, which
    can occur when Claude Code needs to initialize a new session.

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

    prompt = _build_prompt(text)
    last_error: Exception | None = None

    # Retry loop with exponential backoff
    for attempt in range(config.max_retries + 1):
        try:
            humanized = _invoke_claude(prompt, config)
            return HumanizeResult(success=True, text=humanized, original=text)

        except subprocess.TimeoutExpired as e:
            last_error = e
            if attempt < config.max_retries:
                delay = config.retry_delay * (2 ** attempt)
                logger.warning(
                    f"Humanization timed out (attempt {attempt + 1}/{config.max_retries + 1}), "
                    f"retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                error_msg = f"Humanization timed out after {config.max_retries + 1} attempts"
                logger.error(error_msg)
                if fail_open:
                    return HumanizeResult(success=False, text=text, original=text, error=error_msg)
                raise HumanizationError(error_msg) from e

        except HumanizationError as e:
            # Don't retry on non-timeout errors
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

    # Should not reach here, but handle gracefully
    error_msg = f"Humanization failed after retries: {last_error}"
    if fail_open:
        return HumanizeResult(success=False, text=text, original=text, error=error_msg)
    raise HumanizationError(error_msg)


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
