"""
Claude Agent SDK runner for non-interactive mode.

This module provides functions for running Claude via the Agent SDK,
which provides full access to tools and filesystem.

Supports both synchronous and asynchronous execution with streaming output.
"""

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from llm.claude.config import ClaudeConfig
from llm.result import AgentResult


async def run_agent_async(
    prompt: str,
    *,
    config: ClaudeConfig | None = None,
    timeout: int | None = None,
    cwd: Path | str | None = None,
    on_output: Callable[[str], None] | None = None,
) -> AgentResult:
    """Run agent via Claude Agent SDK.

    Args:
        prompt: The prompt to send to Claude
        config: Agent configuration (uses defaults if None)
        timeout: Override config timeout (seconds)
        cwd: Working directory for the agent
        on_output: Optional callback for streaming output line-by-line

    Returns:
        AgentResult with response and status

    Example:
        result = await run_agent_async(
            prompt="Fix the bug in main.py",
            cwd=Path.home() / "khan" / "my-repo",
        )
        if result.success:
            print("Agent completed successfully")
        else:
            print(f"Error: {result.error}")
    """
    config = config or ClaudeConfig()
    timeout = timeout or config.timeout
    cwd = cwd or config.cwd

    # Set up environment for router if needed
    _setup_environment(config)

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
    options_kwargs = {
        "cwd": str(cwd) if cwd else None,
        "permission_mode": "bypassPermissions",
        "model": "claude-opus-4-5",
    }

    # Only set allowed_tools if explicitly configured
    if config.allowed_tools:
        options_kwargs["allowed_tools"] = config.allowed_tools

    options = sdk.ClaudeAgentOptions(**options_kwargs)

    stdout_parts: list[str] = []

    try:
        async with asyncio.timeout(timeout):
            async for message in sdk.query(prompt=prompt, options=options):
                text = _extract_text(message)
                if text:
                    stdout_parts.append(text)
                    if on_output:
                        on_output(text)

        return AgentResult(
            success=True,
            stdout="\n".join(stdout_parts),
            stderr="",
            returncode=0,
        )

    except TimeoutError:
        return AgentResult(
            success=False,
            stdout="\n".join(stdout_parts),
            stderr="",
            returncode=-1,
            error=f"Timed out after {timeout} seconds",
        )

    except Exception as e:
        return AgentResult(
            success=False,
            stdout="\n".join(stdout_parts),
            stderr=str(e),
            returncode=-1,
            error=str(e),
        )


def run_agent(
    prompt: str,
    **kwargs,
) -> AgentResult:
    """Synchronous wrapper for run_agent_async.

    See run_agent_async for full documentation.

    Example:
        result = run_agent("Explain the codebase", cwd="/path/to/repo")
        print(result.stdout)
    """
    return asyncio.run(run_agent_async(prompt, **kwargs))


def _setup_environment(config: ClaudeConfig) -> None:
    """Set up environment variables for the SDK.

    For Anthropic provider: Use ANTHROPIC_API_KEY directly (no router needed).
    For other providers: Use claude-code-router to translate requests.
    """
    # Check if we should use the router
    # Router is only needed for non-Anthropic providers (OpenAI, Gemini via router)
    llm_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if llm_provider == "anthropic" and has_api_key:
        # Direct Anthropic access - no router needed
        # Don't set ANTHROPIC_BASE_URL so SDK uses default Anthropic API
        return

    # Non-Anthropic provider or no API key - use router
    base_url = config.router_base_url or f"http://localhost:{config.router_port}"

    if not os.environ.get("ANTHROPIC_BASE_URL"):
        os.environ["ANTHROPIC_BASE_URL"] = base_url

    # SDK validates API key exists, but router handles actual auth
    if not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = "placeholder-for-router"


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
