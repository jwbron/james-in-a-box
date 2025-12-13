"""
Configuration for the Claude agent runner.

The jib container can use claude-code-router to enable routing to
alternative providers (OpenAI, Gemini, DeepSeek, etc.)

Configure the router at ~/.claude-code-router/config.json
See: https://github.com/musistudio/claude-code-router
"""

from dataclasses import dataclass, field
from enum import Enum

from llm.config import BaseConfig


class Provider(Enum):
    """Available LLM providers for Claude."""

    ANTHROPIC = "anthropic"  # Direct to Anthropic API via Claude Agent SDK
    ROUTER = "router"  # Via claude-code-router (any provider)


@dataclass
class ClaudeConfig(BaseConfig):
    """Configuration for Claude agent execution.

    Extends BaseConfig with Claude-specific settings.

    Attributes:
        provider: Which provider to use (ANTHROPIC or ROUTER)
        cwd: Working directory for the agent (inherited from BaseConfig)
        timeout: Maximum execution time in seconds (inherited from BaseConfig)
        allowed_tools: List of allowed tool names. Empty = all tools allowed.
            Available: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Task
        router_port: Port for claude-code-router (default: 3456)
        router_base_url: Override router URL (default: localhost:{router_port})
    """

    provider: Provider = Provider.ANTHROPIC

    # Tools: empty list = all tools allowed (with dangerouslySkipPermissions)
    # Available: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Task
    allowed_tools: list[str] = field(default_factory=list)

    # Router-specific settings
    router_port: int = 3456
    router_base_url: str | None = None  # Auto-set to localhost:{router_port}


# Backward compatibility alias
AgentConfig = ClaudeConfig
