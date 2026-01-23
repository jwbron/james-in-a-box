"""
Claude Agent SDK runner for non-interactive mode.

This module provides functions for running Claude via the Agent SDK,
which provides full access to tools and filesystem.

Supports both synchronous and asynchronous execution with streaming output.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from llm.claude.config import ClaudeConfig
from llm.result import AgentResult


logger = logging.getLogger(__name__)

# Default model for jib-container agents
# Using the alias 'opus' which maps to the latest Opus model (claude-opus-4-5-*)
# Note: Claude may self-report a different model ID, but the API metadata shows
# the actual model being used. Check the 'model' field in AssistantMessage.
DEFAULT_MODEL = "opus"


async def run_agent_async(
    prompt: str,
    *,
    config: ClaudeConfig | None = None,
    timeout: int | None = None,
    cwd: Path | str | None = None,
    on_output: Callable[[str], None] | None = None,
    model: str | None = None,
) -> AgentResult:
    """Run agent via Claude Agent SDK.

    Args:
        prompt: The prompt to send to Claude
        config: Agent configuration (uses defaults if None)
        timeout: Override config timeout (seconds)
        cwd: Working directory for the agent
        on_output: Optional callback for streaming output line-by-line
        model: Model to use (default: opus). Can be an alias ('opus', 'sonnet')
               or full model ID ('claude-opus-4-5-20251101')

    Returns:
        AgentResult with response and status. The result includes metadata
        about the actual model used via the 'model' key in metadata.

    Example:
        result = await run_agent_async(
            prompt="Fix the bug in main.py",
            cwd=Path.home() / "repos" / "my-repo",
        )
        if result.success:
            print("Agent completed successfully")
        else:
            print(f"Error: {result.error}")
    """
    config = config or ClaudeConfig()
    timeout = timeout or config.timeout
    cwd = cwd or config.cwd
    model = model or DEFAULT_MODEL

    try:
        import claude_agent_sdk as sdk
    except ImportError:
        return AgentResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error="Claude Agent SDK not installed. Run: pip install claude-agent-sdk",
        )

    # Build SDK options
    # IMPORTANT: setting_sources=[] prevents loading user settings from
    # ~/.claude/settings.json which might override the model selection
    options_kwargs = {
        "cwd": str(cwd) if cwd else None,
        "permission_mode": "bypassPermissions",
        "model": model,
        "setting_sources": [],  # Don't load user settings - use our explicit config
    }

    # Only set allowed_tools if explicitly configured
    if config.allowed_tools:
        options_kwargs["allowed_tools"] = config.allowed_tools

    options = sdk.ClaudeAgentOptions(**options_kwargs)
    logger.debug(f"SDK options: model={options.model}, setting_sources={options.setting_sources}")

    stdout_parts: list[str] = []
    actual_model: str | None = None  # Track the model reported by the API

    try:
        async with asyncio.timeout(timeout):
            async for message in sdk.query(prompt=prompt, options=options):
                # Extract actual model from init message or assistant messages
                actual_model = _extract_model_info(message, actual_model)

                text = _extract_text(message)
                if text:
                    stdout_parts.append(text)
                    if on_output:
                        on_output(text)

        if actual_model:
            logger.info(f"Agent completed using model: {actual_model}")

        return AgentResult(
            success=True,
            stdout="\n".join(stdout_parts),
            stderr="",
            returncode=0,
            metadata={"model": actual_model} if actual_model else None,
        )

    except TimeoutError:
        return AgentResult(
            success=False,
            stdout="\n".join(stdout_parts),
            stderr="",
            returncode=-1,
            error=f"Timed out after {timeout} seconds",
            metadata={"model": actual_model} if actual_model else None,
        )

    except Exception as e:
        return AgentResult(
            success=False,
            stdout="\n".join(stdout_parts),
            stderr=str(e),
            returncode=-1,
            error=str(e),
            metadata={"model": actual_model} if actual_model else None,
        )


def run_agent(
    prompt: str,
    *,
    model: str | None = None,
    **kwargs,
) -> AgentResult:
    """Synchronous wrapper for run_agent_async.

    See run_agent_async for full documentation.

    Args:
        prompt: The prompt to send to Claude
        model: Model to use (default: opus)
        **kwargs: Additional arguments passed to run_agent_async

    Example:
        result = run_agent("Explain the codebase", cwd="/path/to/repo")
        print(result.stdout)

        # Check what model was actually used:
        if result.metadata:
            print(f"Model used: {result.metadata.get('model')}")
    """
    return asyncio.run(run_agent_async(prompt, model=model, **kwargs))


def _extract_model_info(message, current_model: str | None) -> str | None:
    """Extract model information from SDK messages.

    The actual model used can be found in:
    - SystemMessage (subtype='init'): data['model'] contains the resolved model ID
    - AssistantMessage: model attribute contains the model ID

    Args:
        message: SDK message
        current_model: Previously extracted model (returned if no new info)

    Returns:
        Model ID string or None
    """
    msg_class = type(message).__name__

    # SystemMessage init contains the resolved model ID
    if msg_class == "SystemMessage" and hasattr(message, "data") and isinstance(message.data, dict):
        model = message.data.get("model")
        if model:
            logger.debug(f"Model from init message: {model}")
            return model

    # AssistantMessage has model attribute
    if msg_class == "AssistantMessage" and hasattr(message, "model"):
        model = message.model
        if model and model != current_model:
            logger.debug(f"Model from assistant message: {model}")
            return model

    return current_model


def _extract_text(message) -> str | None:
    """Extract text content from SDK message.

    The SDK returns various message types:
    - SystemMessage: init info (subtype='init')
    - AssistantMessage: content is a list of blocks (TextBlock, ThinkingBlock, etc.)
    - ResultMessage: has 'result' attribute
    """
    msg_class = type(message).__name__

    # AssistantMessage: content is a list of content blocks
    if msg_class == "AssistantMessage" and hasattr(message, "content"):
        texts = []
        for block in message.content:
            block_class = type(block).__name__
            # TextBlock has 'text' attribute
            if block_class == "TextBlock" and hasattr(block, "text"):
                texts.append(block.text)
            # ThinkingBlock has 'thinking' attribute (usually "(no content)" or thought process)
            # Skip "(no content)" thinking blocks
            elif (
                block_class == "ThinkingBlock"
                and hasattr(block, "thinking")
                and block.thinking
                and block.thinking != "(no content)"
            ):
                texts.append(f"[Thinking: {block.thinking}]")
        if texts:
            return "\n".join(texts)

    # ResultMessage: has 'result' attribute
    if msg_class == "ResultMessage" and hasattr(message, "result") and message.result:
        return message.result

    # SystemMessage: skip (init info)
    if msg_class == "SystemMessage":
        return None

    # Fallback for other message types with 'type' attribute
    if hasattr(message, "type"):
        msg_type = message.type
        if msg_type == "text" and hasattr(message, "text"):
            return message.text

    return None
