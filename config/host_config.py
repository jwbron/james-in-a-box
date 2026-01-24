#!/usr/bin/env python3
"""
Unified Host Configuration Loader for james-in-a-box (jib)

All host-side configuration is stored under ~/.config/jib/

Configuration Locations:
- ~/.config/jib/config.yaml        - Main settings (non-secret)
- ~/.config/jib/secrets.env        - All secrets (Slack, GitHub, Confluence, JIRA tokens)
- ~/.config/jib/github-token       - GitHub token (dedicated file)
- ~/.config/jib/repositories.yaml  - Repository access configuration

GitHub Token Sources (checked in order):
1. ~/.config/jib/secrets.env       - GITHUB_TOKEN in env file
2. ~/.config/jib/github-token      - Plain text token file
3. ~/.jib-sharing/.github-token    - JSON from github-token-refresher service
4. GITHUB_TOKEN environment var    - Overrides all above

Usage:
    from config.host_config import HostConfig

    config = HostConfig()
    slack_token = config.get_secret('SLACK_TOKEN')
    slack_channel = config.get('slack_channel')
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any


try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


logger = logging.getLogger(__name__)


class HostConfig:
    """Unified configuration loader for jib host services.

    All configuration is stored in ~/.config/jib/.
    """

    # Config location
    JIB_CONFIG_DIR = Path.home() / ".config" / "jib"
    CONFIG_FILE = JIB_CONFIG_DIR / "config.yaml"
    SECRETS_FILE = JIB_CONFIG_DIR / "secrets.env"
    GITHUB_TOKEN_FILE = JIB_CONFIG_DIR / "github-token"
    REPOS_FILE = JIB_CONFIG_DIR / "repositories.yaml"

    # Token refresher location (JSON format from github-token-refresher service)
    JIB_SHARING_DIR = Path.home() / ".jib-sharing"
    REFRESHER_TOKEN_FILE = JIB_SHARING_DIR / ".github-token"

    def __init__(self):
        """Initialize configuration loader.

        Loads config from ~/.config/jib/.
        """
        self._config: dict[str, Any] = {}
        self._secrets: dict[str, str] = {}

        # Ensure config directory exists
        self.JIB_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(self.JIB_CONFIG_DIR, 0o700)

        # Load configuration
        self._load_config()
        self._load_secrets()

    def _write_secrets_file(self, secrets: dict[str, str]):
        """Write secrets to .env file with secure permissions."""
        lines = [
            "# jib Secrets Configuration",
            "# This file contains sensitive credentials - DO NOT COMMIT",
            "",
        ]

        # Group secrets by service
        groups = {
            "Slack": ["SLACK_TOKEN", "SLACK_APP_TOKEN"],
            "GitHub": ["GITHUB_TOKEN", "GITHUB_READONLY_TOKEN"],
            "Confluence": [
                "CONFLUENCE_BASE_URL",
                "CONFLUENCE_USERNAME",
                "CONFLUENCE_API_TOKEN",
                "CONFLUENCE_SPACE_KEYS",
            ],
            "JIRA": ["JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "JIRA_JQL_QUERY"],
        }

        written = set()
        for group_name, keys in groups.items():
            group_secrets = [(k, secrets[k]) for k in keys if k in secrets]
            if group_secrets:
                lines.append(f"# {group_name}")
                for key, value in group_secrets:
                    lines.append(f'{key}="{value}"')
                    written.add(key)
                lines.append("")

        # Write any remaining secrets
        remaining = [(k, v) for k, v in secrets.items() if k not in written]
        if remaining:
            lines.append("# Other")
            for key, value in remaining:
                lines.append(f'{key}="{value}"')

        with open(self.SECRETS_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(self.SECRETS_FILE, 0o600)

    def _write_config_file(self, config: dict[str, Any]):
        """Write non-secret config to YAML file."""
        with open(self.CONFIG_FILE, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    def _load_config(self):
        """Load non-secret configuration from ~/.config/jib/."""
        if self.CONFIG_FILE.exists():
            with open(self.CONFIG_FILE) as f:
                self._config = yaml.safe_load(f) or {}

    def _load_secrets(self):
        """Load secrets from ~/.config/jib/secrets.env and environment."""
        # Load from secrets.env
        if self.SECRETS_FILE.exists():
            with open(self.SECRETS_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if value:
                            self._secrets[key] = value

        # Load GitHub token from dedicated file
        if self.GITHUB_TOKEN_FILE.exists():
            with open(self.GITHUB_TOKEN_FILE) as f:
                token = f.read().strip()
                if token and "GITHUB_TOKEN" not in self._secrets:
                    self._secrets["GITHUB_TOKEN"] = token

        # Load GitHub token from refresher service (JSON format)
        # This is written by github-token-refresher and contains auto-refreshed
        # GitHub App installation tokens
        if "GITHUB_TOKEN" not in self._secrets and self.REFRESHER_TOKEN_FILE.exists():
            try:
                with open(self.REFRESHER_TOKEN_FILE) as f:
                    token_data = json.load(f)
                    token = token_data.get("token")
                    if token:
                        self._secrets["GITHUB_TOKEN"] = token
                        logger.debug("Loaded GITHUB_TOKEN from refresher service")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load token from refresher file: {e}")

        # Environment variables override file settings
        for key in list(self._secrets.keys()):
            env_value = os.environ.get(key)
            if env_value:
                self._secrets[key] = env_value

        # Also check GITHUB_TOKEN env var even if not already in secrets
        if "GITHUB_TOKEN" not in self._secrets:
            env_token = os.environ.get("GITHUB_TOKEN")
            if env_token:
                self._secrets["GITHUB_TOKEN"] = env_token

    def get(self, key: str, default: Any = None) -> Any:
        """Get a non-secret configuration value."""
        return self._config.get(key, default)

    def get_secret(self, key: str, default: str = "") -> str:
        """Get a secret value (from env or secrets file)."""
        return self._secrets.get(key, default)

    def get_all_secrets(self) -> dict[str, str]:
        """Get all secrets (for debugging, use carefully)."""
        return dict(self._secrets)

    def get_all_config(self) -> dict[str, Any]:
        """Get all non-secret config."""
        return dict(self._config)

    # Convenience methods for common values
    @property
    def slack_token(self) -> str:
        return self.get_secret("SLACK_TOKEN")

    @property
    def slack_app_token(self) -> str:
        return self.get_secret("SLACK_APP_TOKEN")

    @property
    def slack_channel(self) -> str:
        return self.get("slack_channel", "")

    @property
    def github_token(self) -> str:
        return self.get_secret("GITHUB_TOKEN")

    @property
    def github_readonly_token(self) -> str:
        """Get the read-only GitHub token for monitoring external repos.

        This token is used for repos in `readable_repos` where jib doesn't
        have write access. Falls back to github_token if not set.
        """
        token = self.get_secret("GITHUB_READONLY_TOKEN")
        if token:
            return token
        # Fall back to main token if readonly not configured
        return self.github_token

    @property
    def confluence_token(self) -> str:
        return self.get_secret("CONFLUENCE_API_TOKEN")

    @property
    def jira_token(self) -> str:
        return self.get_secret("JIRA_API_TOKEN")


def get_config() -> HostConfig:
    """Get a singleton HostConfig instance."""
    if not hasattr(get_config, "_instance"):
        get_config._instance = HostConfig()
    return get_config._instance


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="jib host configuration utility")
    parser.add_argument("--list", action="store_true", help="List all config (no secrets)")
    parser.add_argument(
        "--list-secrets", action="store_true", help="List secret keys (values hidden)"
    )
    parser.add_argument("--get", metavar="KEY", help="Get a config value")
    parser.add_argument("--get-secret", metavar="KEY", help="Get a secret value")

    args = parser.parse_args()

    if args.list:
        config = HostConfig()
        print("Configuration values:")
        for k, v in config.get_all_config().items():
            print(f"  {k}: {v}")
    elif args.list_secrets:
        config = HostConfig()
        print("Secret keys (values hidden):")
        for k in config.get_all_secrets():
            print(f"  {k}: ****")
    elif args.get:
        config = HostConfig()
        print(config.get(args.get, ""))
    elif args.get_secret:
        config = HostConfig()
        print(config.get_secret(args.get_secret, ""))
    else:
        # Show status
        print("jib Host Configuration")
        print("=" * 40)
        print(f"Config directory: {HostConfig.JIB_CONFIG_DIR}")
        print(
            f"Config file: {HostConfig.CONFIG_FILE} {'(exists)' if HostConfig.CONFIG_FILE.exists() else '(not found)'}"
        )
        print(
            f"Secrets file: {HostConfig.SECRETS_FILE} {'(exists)' if HostConfig.SECRETS_FILE.exists() else '(not found)'}"
        )
        print(
            f"Repos file: {HostConfig.REPOS_FILE} {'(exists)' if HostConfig.REPOS_FILE.exists() else '(not found)'}"
        )
        print(
            f"Refresher token: {HostConfig.REFRESHER_TOKEN_FILE} {'(exists)' if HostConfig.REFRESHER_TOKEN_FILE.exists() else '(not found)'}"
        )
        print()

        try:
            config = HostConfig()
            print("Loaded secrets:")
            for k in config.get_all_secrets():
                print(f"  - {k}")
            print()
            print("Loaded config:")
            for k, v in config.get_all_config().items():
                print(f"  - {k}: {v}")
        except Exception as e:
            print(f"Error loading config: {e}")
            print()
            print("To set up configuration, copy templates to ~/.config/jib/")
