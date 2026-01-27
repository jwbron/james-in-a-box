"""Authentication and API key management for jib.

This module handles Anthropic API keys, GitHub tokens,
and related authentication utilities.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .output import warn


def get_anthropic_api_key() -> str | None:
    """
    Get Anthropic API key from environment or config file.

    Returns:
        API key string if found, None otherwise.
    """
    # Check environment variable first
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]

    # Check config file
    api_key_file = Config.USER_CONFIG_DIR / "anthropic-api-key"
    if api_key_file.exists():
        return api_key_file.read_text().strip()

    return None


def get_anthropic_auth_method() -> str:
    """
    Get the Anthropic authentication method from environment or config file.

    Returns:
        Auth method: 'api_key' (default) or 'oauth'
    """
    import yaml

    # Check environment variable first
    method = os.environ.get("ANTHROPIC_AUTH_METHOD", "").lower()
    if method in ("api_key", "oauth"):
        return method

    # Check config.yaml
    config_file = Config.USER_CONFIG_DIR / "config.yaml"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
                method = config.get("anthropic_auth_method", "").lower()
                if method in ("api_key", "oauth"):
                    return method
        except Exception:
            pass

    # Default to api_key
    return "api_key"


def get_github_token() -> str | None:
    """Get GitHub PAT using the unified HostConfig system.

    Uses HostConfig to load the token from (in order of precedence):
    - Environment variable GITHUB_TOKEN (highest priority)
    - ~/.config/jib/secrets.env (GITHUB_TOKEN=...)
    - ~/.config/jib/github-token (dedicated file)

    This follows the same configuration pattern as other jib secrets
    (Slack tokens, Confluence tokens, etc.) via config/host_config.py.

    Returns:
        Token string if found and valid, None otherwise
    """
    try:
        # Import HostConfig from project root
        script_dir = Path(__file__).resolve().parent.parent
        project_root = script_dir.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from config.host_config import HostConfig

        config = HostConfig()
        token = config.github_token

        if token and token.startswith(("ghp_", "github_pat_")):
            return token
    except ImportError as e:
        warn(f"Could not import HostConfig: {e}")
    except Exception as e:
        warn(f"Error loading GitHub token from config: {e}")
    return None


def get_github_readonly_token() -> str | None:
    """Get read-only GitHub token for external repositories.

    This token is used for repos outside the primary GitHub App's scope,
    such as Khan/webapp when the App is only installed on jwbron/james-in-a-box.

    Returns:
        Token string if found, None otherwise
    """
    try:
        script_dir = Path(__file__).resolve().parent.parent
        project_root = script_dir.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from config.host_config import HostConfig

        config = HostConfig()
        # Note: github_readonly_token falls back to github_token if not set
        token = config.get_secret("GITHUB_READONLY_TOKEN")
        if token:
            return token
    except ImportError:
        pass
    except Exception:
        pass
    return None


def get_github_app_token() -> str | None:
    """Generate GitHub App installation token for container use.

    Uses the github-app-token.py script to generate a fresh installation token
    from App credentials (App ID, Installation ID, private key).

    Returns:
        Installation token string if successful, None otherwise
    """
    # Check if App credentials exist
    app_id_file = Config.USER_CONFIG_DIR / "github-app-id"
    installation_id_file = Config.USER_CONFIG_DIR / "github-app-installation-id"
    private_key_file = Config.USER_CONFIG_DIR / "github-app.pem"

    if not all(f.exists() for f in [app_id_file, installation_id_file, private_key_file]):
        return None  # App not configured, fall back to PAT

    # Find the token generation script
    script_dir = Path(__file__).resolve().parent.parent
    token_script = script_dir / "jib-tools" / "github-app-token.py"

    if not token_script.exists():
        warn(f"GitHub App token script not found: {token_script}")
        return None

    # Use the host-services venv Python which has cryptography installed
    # Fall back to system python3 if venv doesn't exist
    jib_root = script_dir.parent
    venv_python = jib_root / "host-services" / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python3"

    try:
        result = subprocess.run(
            [python_cmd, str(token_script), "--config-dir", str(Config.USER_CONFIG_DIR)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode == 0:
            token = result.stdout.strip()
            if token and token.startswith("ghs_"):  # Installation tokens start with ghs_
                return token
            elif token:
                # Token format might vary, accept if non-empty
                return token

        # Log error but don't fail - we can fall back to PAT
        if result.stderr:
            warn(f"GitHub App token generation failed: {result.stderr.strip()}")

    except subprocess.TimeoutExpired:
        warn("GitHub App token generation timed out")
    except Exception as e:
        warn(f"GitHub App token generation error: {e}")

    return None


def write_github_token_file(token: str) -> bool:
    """Write GitHub token to the shared file for container consumption.

    The token file is written to ~/.jib-sharing/.github-token and contains
    JSON with the token and metadata. This allows long-running containers
    to read fresh tokens even after the initial env var becomes stale.

    The github-token-refresher service will continuously update this file,
    but we write an initial version here so containers have a valid token
    immediately at startup.

    Args:
        token: The GitHub token to write

    Returns:
        True if successful, False otherwise
    """
    import json

    token_file = Config.SHARING_DIR / ".github-token"
    validity_seconds = 60 * 60  # 1 hour

    # Ensure sharing directory exists
    Config.SHARING_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    expires_at = now.timestamp() + validity_seconds

    data = {
        "token": token,
        "generated_at": now.isoformat(),
        "expires_at_unix": expires_at,
        "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat(),
        "generated_by": "jib-launcher",
        "validity_seconds": validity_seconds,
    }

    try:
        # Write atomically using temp file
        temp_file = token_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2) + "\n")
        temp_file.chmod(0o600)  # Restrict permissions
        temp_file.rename(token_file)
        return True
    except Exception as e:
        warn(f"Failed to write token file: {e}")
        return False
