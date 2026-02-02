"""Anthropic credential management for header injection.

This module loads Anthropic API credentials from the jib secrets file and
provides them in a format suitable for HTTP header injection by the ICAP server.

Credentials are stored in ~/.config/jib/secrets.env on the host and mounted
into the gateway container. The gateway injects these credentials into
requests to api.anthropic.com via SSL bump + ICAP header injection.

Supported credential types:
- ANTHROPIC_API_KEY: Standard Anthropic API key (x-api-key header)
- ANTHROPIC_OAUTH_TOKEN: OAuth token from `claude setup-token` (Authorization: Bearer header)
"""

import logging
import os
from pathlib import Path
from typing import NamedTuple, Optional

log = logging.getLogger(__name__)


class AnthropicCredential(NamedTuple):
    """Anthropic API credential for header injection."""

    header_name: str  # "x-api-key" or "Authorization"
    header_value: str  # The actual credential value


# Default secrets path - can be overridden via environment variable
# In the gateway container, this is mounted from ~/.config/jib/secrets.env
SECRETS_PATH = Path(
    os.environ.get("JIB_SECRETS_PATH", "/home/jib/.config/jib/secrets.env")
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dictionary.

    Handles:
    - KEY=value
    - KEY="quoted value"
    - KEY='quoted value'
    - # comments
    - Empty lines

    Args:
        path: Path to the .env file

    Returns:
        Dictionary of environment variables
    """
    result = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=value
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key:
                    result[key] = value
    except OSError as e:
        log.error(f"Failed to read secrets file: {e}")
    return result


def load_anthropic_credential() -> Optional[AnthropicCredential]:
    """Load Anthropic credentials from secrets file.

    Supports both API keys and OAuth tokens:
    - ANTHROPIC_API_KEY: Injected as "x-api-key: <value>"
    - ANTHROPIC_OAUTH_TOKEN: Injected as "Authorization: Bearer <value>"

    OAuth token takes precedence if both are configured.

    Returns:
        AnthropicCredential or None if not configured
    """
    if not SECRETS_PATH.exists():
        log.warning(f"Secrets file not found: {SECRETS_PATH}")
        return None

    secrets = parse_env_file(SECRETS_PATH)

    if not secrets:
        log.warning("Secrets file is empty or could not be parsed")
        return None

    # Check for OAuth token first (takes precedence per design doc)
    oauth_token = secrets.get("ANTHROPIC_OAUTH_TOKEN", "")
    if oauth_token.strip():
        log.info("Loaded Anthropic OAuth token from secrets")
        return AnthropicCredential(
            header_name="Authorization", header_value=f"Bearer {oauth_token.strip()}"
        )

    # Fall back to API key
    api_key = secrets.get("ANTHROPIC_API_KEY", "")
    if api_key.strip():
        log.info("Loaded Anthropic API key from secrets")
        return AnthropicCredential(header_name="x-api-key", header_value=api_key.strip())

    log.warning("No Anthropic credentials found in secrets (ANTHROPIC_API_KEY or ANTHROPIC_OAUTH_TOKEN)")
    return None


def validate_credential_format(credential: AnthropicCredential) -> tuple[bool, str]:
    """Validate credential format.

    Performs basic format validation to catch obvious configuration errors.
    Does NOT validate that the credential actually works (server-side validation).

    Args:
        credential: The credential to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if credential.header_name == "x-api-key":
        # API keys should start with "sk-ant-"
        if not credential.header_value.startswith("sk-ant-"):
            return False, "API key should start with 'sk-ant-'"
        if len(credential.header_value) < 50:
            return False, "API key appears too short (expected 50+ characters)"

    elif credential.header_name == "Authorization":
        if not credential.header_value.startswith("Bearer "):
            return False, "OAuth token must be prefixed with 'Bearer '"
        token = credential.header_value[7:]  # Remove "Bearer " prefix
        if len(token) < 20:
            return False, "OAuth token appears too short (expected 20+ characters)"

    else:
        return False, f"Unknown header type: {credential.header_name}"

    return True, ""


def get_credential_for_injection() -> Optional[AnthropicCredential]:
    """Get validated credential ready for header injection.

    This is the main entry point for the ICAP server. Returns a
    validated credential that can be safely injected into requests.

    Returns:
        AnthropicCredential if valid, None otherwise
    """
    credential = load_anthropic_credential()
    if credential is None:
        return None

    is_valid, error = validate_credential_format(credential)
    if not is_valid:
        log.error(f"Invalid credential format: {error}")
        return None

    return credential


# Cached credential for performance (reloaded on file change)
_cached_credential: Optional[AnthropicCredential] = None
_cached_mtime: float = 0


def get_credential_cached() -> Optional[AnthropicCredential]:
    """Get credential with caching for performance.

    The credential is cached and only reloaded when the secrets file
    changes (based on mtime). This avoids re-parsing the file on every request.

    Returns:
        AnthropicCredential if valid, None otherwise
    """
    global _cached_credential, _cached_mtime

    try:
        current_mtime = SECRETS_PATH.stat().st_mtime
    except OSError:
        # File doesn't exist or can't be accessed
        _cached_credential = None
        _cached_mtime = 0
        return None

    # Reload if file has changed
    if current_mtime != _cached_mtime:
        _cached_credential = get_credential_for_injection()
        _cached_mtime = current_mtime
        if _cached_credential:
            log.debug("Credential cache refreshed")
        else:
            log.warning("Credential cache refresh failed - no valid credentials")

    return _cached_credential
