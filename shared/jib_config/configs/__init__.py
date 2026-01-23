"""
Service-specific configuration classes.

Each config class implements the BaseConfig interface, providing:
- Validation of configuration values
- Health checks for service connectivity
- Safe serialization with secret masking
- Loading from environment variables and config files

Available configs:
- SlackConfig: Slack bot and app tokens
- GitHubConfig: GitHub authentication tokens
- LLMConfig: LLM provider API keys
- ConfluenceConfig: Confluence API credentials
- JiraConfig: JIRA API credentials
- GatewayConfig: Gateway sidecar settings
"""

from .confluence import ConfluenceConfig
from .gateway import GatewayConfig
from .github import GitHubConfig
from .jira import JiraConfig
from .llm import LLMConfig
from .slack import SlackConfig

__all__ = [
    "ConfluenceConfig",
    "GatewayConfig",
    "GitHubConfig",
    "JiraConfig",
    "LLMConfig",
    "SlackConfig",
]
