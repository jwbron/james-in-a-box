"""
Anthropic Credentials Manager for Gateway Sidecar.

Manages Anthropic API credentials (API key or OAuth token) for proxy injection.
Credentials are read from config files mounted in the gateway container.

File locations (matching jib-container conventions):
- API key: ~/.config/jib/anthropic-api-key
- Auth method: ANTHROPIC_AUTH_METHOD env var or config.yaml

OAuth tokens are managed by Claude Code directly and don't flow through this module.
When using OAuth, Claude Code includes the Authorization header which we preserve.
"""

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


logger = get_logger("gateway-sidecar.anthropic-credentials")

# Config directory (matches jib-container layout)
CONFIG_DIR = Path.home() / ".config" / "jib"


@dataclass
class AnthropicCredential:
    """Container for Anthropic API credential."""

    token: str
    token_type: str  # "api_key" or "oauth"

    @property
    def is_api_key(self) -> bool:
        return self.token_type == "api_key"

    @property
    def is_oauth(self) -> bool:
        return self.token_type == "oauth"


class AnthropicCredentialsManager:
    """
    Manages Anthropic credentials for gateway proxy injection.

    Credentials are loaded from config files on first access and cached.
    Thread-safe for concurrent request handling.
    """

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize the credentials manager.

        Args:
            config_dir: Directory containing config files (default: ~/.config/jib)
        """
        self._config_dir = config_dir or CONFIG_DIR
        self._credential: AnthropicCredential | None = None
        self._lock = threading.Lock()
        self._loaded = False

    def get_credential(self) -> AnthropicCredential | None:
        """
        Get the Anthropic credential for API requests.

        Returns:
            AnthropicCredential if available, None if not configured.
        """
        with self._lock:
            if not self._loaded:
                self._load_credential()
                self._loaded = True
            return self._credential

    def _load_credential(self) -> None:
        """Load credential from config files."""
        # Determine auth method
        auth_method = self._get_auth_method()

        if auth_method == "oauth":
            # OAuth mode: Claude Code manages tokens directly
            # We don't store OAuth tokens in the gateway - they flow through
            # the Authorization header from Claude Code
            logger.info("Anthropic auth method: oauth (tokens managed by Claude Code)")
            self._credential = None
            return

        # API key mode: Read from config file
        api_key = self._read_api_key()
        if api_key:
            self._credential = AnthropicCredential(token=api_key, token_type="api_key")
            logger.info(
                "Anthropic API key loaded",
                key_prefix=api_key[:10] + "..." if len(api_key) > 10 else "[short]",
            )
        else:
            logger.warning(
                "Anthropic API key not found",
                config_dir=str(self._config_dir),
            )
            self._credential = None

    def _get_auth_method(self) -> str:
        """Get the configured authentication method."""
        # Check environment variable first
        method = os.environ.get("ANTHROPIC_AUTH_METHOD", "").lower()
        if method in ("api_key", "oauth"):
            return method

        # Check config.yaml
        config_file = self._config_dir / "config.yaml"
        if config_file.exists():
            try:
                import yaml

                with open(config_file) as f:
                    config = yaml.safe_load(f) or {}
                    method = config.get("anthropic_auth_method", "").lower()
                    if method in ("api_key", "oauth"):
                        return method
            except Exception as e:
                logger.warning(
                    "Failed to read config.yaml",
                    error=str(e),
                )

        # Default to api_key
        return "api_key"

    def _read_api_key(self) -> str | None:
        """Read API key from config file."""
        # Check environment variable first
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            return env_key

        # Read from config file
        api_key_file = self._config_dir / "anthropic-api-key"
        if api_key_file.exists():
            try:
                return api_key_file.read_text().strip()
            except Exception as e:
                logger.error(
                    "Failed to read API key file",
                    path=str(api_key_file),
                    error=str(e),
                )

        return None

    def reload(self) -> None:
        """Force reload of credentials (for testing or config updates)."""
        with self._lock:
            self._loaded = False
            self._credential = None


# Global credentials manager instance
_credentials_manager: AnthropicCredentialsManager | None = None


def get_credentials_manager() -> AnthropicCredentialsManager:
    """Get or create the global credentials manager."""
    global _credentials_manager
    if _credentials_manager is None:
        _credentials_manager = AnthropicCredentialsManager()
    return _credentials_manager


def reset_credentials_manager() -> None:
    """Reset the global credentials manager (for testing)."""
    global _credentials_manager
    _credentials_manager = None
